from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .models import ApiAnswer, Decision, OptionOcr, Region


class DecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceCandidate:
    method: str
    option: OptionOcr
    score: float
    detail: str


@dataclass(frozen=True)
class ResolveSettings:
    text_match_threshold: float = 0.62
    strict_triple_check: bool = True
    non_strict_use_confidence_margin: bool = False
    non_strict_confidence_margin: float = 0.15
    click_point_space: str = "auto"
    question_region: Region | None = None
    options_region: Region | None = None
    point_padding: int = 8


def resolve_answer(
    answer: ApiAnswer,
    options: list[OptionOcr],
    settings: ResolveSettings | None = None,
) -> Decision:
    settings = settings or ResolveSettings()
    if not options:
        raise DecisionError("No OCR options are available for answer resolution")
    if answer.confidence < 0:
        raise DecisionError("API confidence cannot be negative")

    evidence: dict[str, OptionOcr] = {}
    evidence_meta: dict[str, str] = {}
    candidates: list[EvidenceCandidate] = []

    if answer.answer_label:
        option = match_by_label(answer.answer_label, options)
        if not option:
            message = f"answer_label did not match any option: {answer.answer_label}"
            if settings.strict_triple_check:
                raise DecisionError(message)
            evidence_meta["label_unmatched"] = str(answer.answer_label)
        else:
            evidence["label"] = option
            evidence_meta["label"] = option.label
            candidates.append(
                EvidenceCandidate(
                    method="label",
                    option=option,
                    score=0.98,
                    detail=f"answer_label={answer.answer_label}",
                )
            )

    if answer.answer_text:
        text_match = match_by_text_with_score(
            answer.answer_text,
            options,
            threshold=settings.text_match_threshold,
        )
        if not text_match:
            message = f"answer_text did not match any option: {answer.answer_text}"
            if settings.strict_triple_check:
                raise DecisionError(message)
            evidence_meta["text_unmatched"] = str(answer.answer_text)
        else:
            option, score = text_match
            evidence["text"] = option
            evidence_meta["text"] = option.label
            candidates.append(
                EvidenceCandidate(
                    method="text",
                    option=option,
                    score=score,
                    detail=f"answer_text={answer.answer_text}",
                )
            )

    if answer.click_point:
        point_match = match_by_point_with_score(
            answer.click_point,
            options,
            settings=settings,
        )
        option = point_match[0] if point_match else None
        if not option:
            message = f"click_point did not fall inside any option: {answer.click_point}"
            if settings.strict_triple_check:
                raise DecisionError(message)
            evidence_meta["point_unmatched"] = str(answer.click_point)
        else:
            option, source, score = point_match
            evidence["point"] = option
            evidence_meta["point"] = f"{option.label} ({source})"
            candidates.append(
                EvidenceCandidate(
                    method="point",
                    option=option,
                    score=score,
                    detail=f"click_point={answer.click_point} source={source}",
                )
            )

    if settings.strict_triple_check:
        missing = [name for name in ("label", "text", "point") if name not in evidence]
        if missing:
            raise DecisionError(f"Strict triple check requires missing evidence: {missing}")

    if not evidence:
        raise DecisionError(
            "API response did not include any usable answer evidence: "
            f"{evidence_meta}"
        )

    labels = {option.label for option in evidence.values()}
    if len(labels) != 1:
        if settings.strict_triple_check:
            raise DecisionError(f"Answer evidence disagrees: {evidence_meta}")
        return _resolve_non_strict(answer, candidates, settings, evidence_meta)
    if not settings.strict_triple_check:
        return _resolve_non_strict(answer, candidates, settings, evidence_meta)

    selected = next(iter(evidence.values()))
    click_point = selected.center()
    return Decision(
        option=selected,
        evidence=evidence_meta,
        confidence=answer.confidence,
        click_point=click_point,
        reason=answer.reason or "API evidence resolved to one option",
    )


def _resolve_non_strict(
    answer: ApiAnswer,
    candidates: list[EvidenceCandidate],
    settings: ResolveSettings,
    evidence_meta: dict[str, str],
) -> Decision:
    if not candidates:
        raise DecisionError("No usable non-strict evidence candidates are available")

    ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
    best = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else 0.0
    margin = best.score - second_score

    if settings.non_strict_use_confidence_margin:
        required = settings.non_strict_confidence_margin
        if margin < required:
            raise DecisionError(
                "Non-strict evidence margin is too small: "
                f"best={best.method}:{best.option.label}:{best.score:.3f}, "
                f"second={second_score:.3f}, required={required:.3f}, "
                f"evidence={evidence_meta}"
            )

    candidate_scores = {
        candidate.method: f"{candidate.option.label}:{candidate.score:.3f}"
        for candidate in ranked
    }
    return Decision(
        option=best.option,
        evidence={**evidence_meta, **candidate_scores, "selected_by": best.method},
        confidence=max(answer.confidence, best.score),
        click_point=best.option.center(),
        reason=(
            answer.reason
            or "Non-strict mode selected the highest-confidence evidence candidate"
        ),
    )


def match_by_label(label: str, options: list[OptionOcr]) -> OptionOcr | None:
    normalized = normalize_label(label)
    for option in options:
        if normalize_label(option.label) == normalized:
            return option

    truth = normalize_truth_value(label)
    if truth is not None:
        for option in options:
            if normalize_truth_value(option.text) == truth:
                return option
    return None


def match_by_text(
    answer_text: str,
    options: list[OptionOcr],
    threshold: float,
) -> OptionOcr | None:
    match = match_by_text_with_score(answer_text, options, threshold)
    return match[0] if match else None


def match_by_text_with_score(
    answer_text: str,
    options: list[OptionOcr],
    threshold: float,
) -> tuple[OptionOcr, float] | None:
    answer_truth = normalize_truth_value(answer_text)
    if answer_truth is not None:
        for option in options:
            if normalize_truth_value(option.text) == answer_truth:
                return option, 1.0

    answer_norm = normalize_text(answer_text)
    if not answer_norm:
        return None

    best: tuple[float, OptionOcr] | None = None
    for option in options:
        option_norm = normalize_text(option.text)
        if not option_norm:
            continue
        if answer_norm in option_norm or option_norm in answer_norm:
            score = 1.0
        else:
            score = SequenceMatcher(None, answer_norm, option_norm).ratio()
        if best is None or score > best[0]:
            best = (score, option)

    if best and best[0] >= threshold:
        return best[1], best[0]
    return None


def match_by_point(
    point: tuple[float, float],
    options: list[OptionOcr],
    settings: ResolveSettings,
) -> tuple[OptionOcr | None, str]:
    match = match_by_point_with_score(point, options, settings)
    if not match:
        return None, "none"
    option, source, _score = match
    return option, source


def match_by_point_with_score(
    point: tuple[float, float],
    options: list[OptionOcr],
    settings: ResolveSettings,
) -> tuple[OptionOcr, str, float] | None:
    candidate_points = _candidate_points(point, settings)
    for source, candidate in candidate_points:
        for option in options:
            if option.contains_point(candidate, padding=settings.point_padding):
                return option, source, _point_confidence(candidate, option)
    return None


def _point_confidence(point: tuple[float, float], option: OptionOcr) -> float:
    x, y = point
    cx, cy = option.center()
    width = max(1, option.bbox[2])
    height = max(1, option.bbox[3])
    normalized_distance = min(
        1.0,
        (((x - cx) / width) ** 2 + ((y - cy) / height) ** 2) ** 0.5,
    )
    return 0.70 + 0.30 * (1.0 - normalized_distance)


def normalize_label(label: str) -> str:
    text = str(label).strip().upper()
    text = re.sub(r"^[\s\[\(（]+|[\s\]\)）.。:：、]+$", "", text)
    return text


def normalize_text(text: str) -> str:
    lowered = str(text).lower()
    lowered = re.sub(r"^[a-h][\.\)、\):：]\s*", "", lowered, flags=re.IGNORECASE)
    return re.sub(r"[\s\W_]+", "", lowered, flags=re.UNICODE)


def normalize_truth_value(text: str) -> bool | None:
    normalized = normalize_text(text)
    true_values = {"true", "yes", "right", "correct", "对", "是", "正确", "真"}
    false_values = {"false", "no", "wrong", "incorrect", "错", "否", "错误", "假"}
    if normalized in true_values:
        return True
    if normalized in false_values:
        return False
    return None


def _candidate_points(
    point: tuple[float, float],
    settings: ResolveSettings,
) -> list[tuple[str, tuple[float, float]]]:
    x, y = point
    space = settings.click_point_space
    candidates: list[tuple[str, tuple[float, float]]] = []

    if space in ("screen", "auto"):
        candidates.append(("screen", (x, y)))
    if space in ("question_region", "auto") and settings.question_region:
        candidates.append(
            (
                "question_region",
                (x + settings.question_region.x, y + settings.question_region.y),
            )
        )
    if space in ("options_region", "auto") and settings.options_region:
        candidates.append(
            (
                "options_region",
                (x + settings.options_region.x, y + settings.options_region.y),
            )
        )
    return candidates
