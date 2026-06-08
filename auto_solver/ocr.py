from __future__ import annotations

import re
from typing import Any, Iterable

from .models import OcrLine, OptionOcr, Region


OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
OPTION_RE = re.compile(r"^\s*([A-Ha-h])[\.\)、\):：]?\s*(.*)$")


class OcrError(RuntimeError):
    pass


class BaseOcrEngine:
    def recognize(self, image: Any, offset: tuple[int, int] = (0, 0)) -> list[OcrLine]:
        raise NotImplementedError


class NullOcrEngine(BaseOcrEngine):
    def recognize(self, image: Any, offset: tuple[int, int] = (0, 0)) -> list[OcrLine]:
        return []


class RapidOcrEngine(BaseOcrEngine):
    def __init__(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ModuleNotFoundError as exc:
            raise OcrError(
                "rapidocr_onnxruntime is not installed. Install with: "
                'pip install -e ".[ocr]"'
            ) from exc
        self._engine = RapidOCR()

    def recognize(self, image: Any, offset: tuple[int, int] = (0, 0)) -> list[OcrLine]:
        raw = self._engine(_to_ocr_image(image))
        if isinstance(raw, tuple):
            raw = raw[0]
        lines: list[OcrLine] = []
        for item in raw or []:
            parsed = _parse_rapidocr_item(item)
            if not parsed:
                continue
            text, bbox, confidence = parsed
            line = OcrLine(text=text, bbox=bbox, confidence=confidence)
            lines.append(line.with_offset(*offset))
        return sort_lines(lines)


def create_ocr_engine(name: str) -> BaseOcrEngine:
    normalized = name.strip().lower()
    if normalized in ("rapidocr", "rapidocr_onnxruntime"):
        return RapidOcrEngine()
    if normalized in ("none", "null", "off"):
        return NullOcrEngine()
    raise OcrError(f"Unsupported OCR engine: {name}")


def extract_question_text(lines: Iterable[OcrLine]) -> str:
    return "\n".join(line.text.strip() for line in sort_lines(lines) if line.text.strip())


def extract_options(lines: Iterable[OcrLine], options_region: Region) -> list[OptionOcr]:
    sorted_lines = [line for line in sort_lines(lines) if line.text.strip()]
    options: list[OptionOcr] = []
    used_labels: set[str] = set()

    for index, line in enumerate(sorted_lines):
        label, text = _split_option_line(line.text)
        if not label:
            label = _infer_label_from_order(index, used_labels)
            text = line.text.strip()
        used_labels.add(label)
        options.append(
            OptionOcr(
                label=label,
                text=text or line.text.strip(),
                bbox=_line_bbox_or_region_slice(line, options_region, index, len(sorted_lines)),
                confidence=line.confidence,
            )
        )

    return _merge_duplicate_labels(options)


def infer_question_type(options: list[OptionOcr]) -> str:
    if len(options) == 2:
        values = {_truthish(option.text) for option in options}
        if values == {"true", "false"}:
            return "true_false"
    return "single_choice"


def sort_lines(lines: Iterable[OcrLine]) -> list[OcrLine]:
    return sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))


def _split_option_line(text: str) -> tuple[str | None, str]:
    match = OPTION_RE.match(text)
    if not match:
        return None, text.strip()
    label = match.group(1).upper()
    rest = match.group(2).strip()
    return label, rest


def _infer_label_from_order(index: int, used_labels: set[str]) -> str:
    for label in OPTION_LABELS[index:] + OPTION_LABELS[:index]:
        if label not in used_labels:
            return label
    return f"OPT{index + 1}"


def _merge_duplicate_labels(options: list[OptionOcr]) -> list[OptionOcr]:
    merged: dict[str, OptionOcr] = {}
    for option in options:
        existing = merged.get(option.label)
        if not existing:
            merged[option.label] = option
            continue
        x1 = min(existing.bbox[0], option.bbox[0])
        y1 = min(existing.bbox[1], option.bbox[1])
        x2 = max(existing.bbox[0] + existing.bbox[2], option.bbox[0] + option.bbox[2])
        y2 = max(existing.bbox[1] + existing.bbox[3], option.bbox[1] + option.bbox[3])
        merged[option.label] = OptionOcr(
            label=option.label,
            text=f"{existing.text} {option.text}".strip(),
            bbox=(x1, y1, x2 - x1, y2 - y1),
            confidence=max(existing.confidence, option.confidence),
        )
    return list(merged.values())


def _line_bbox_or_region_slice(
    line: OcrLine,
    region: Region,
    index: int,
    total: int,
) -> tuple[int, int, int, int]:
    x, y, width, height = line.bbox
    if width > 0 and height > 0:
        return (x, y, width, height)
    slice_height = max(1, region.height // max(1, total))
    return (region.x, region.y + index * slice_height, region.width, slice_height)


def _truthish(text: str) -> str:
    compact = re.sub(r"[\s\W_]+", "", text.lower(), flags=re.UNICODE)
    if compact in {"true", "yes", "right", "correct", "对", "是", "正确", "真"}:
        return "true"
    if compact in {"false", "no", "wrong", "incorrect", "错", "否", "错误", "假"}:
        return "false"
    return compact


def _to_ocr_image(image: Any) -> Any:
    try:
        import numpy as np
    except ModuleNotFoundError:
        return image
    return np.array(image)


def _parse_rapidocr_item(item: Any) -> tuple[str, tuple[int, int, int, int], float] | None:
    if isinstance(item, dict):
        text = str(item.get("text") or item.get("rec_text") or "").strip()
        box = item.get("box") or item.get("dt_boxes") or item.get("bbox")
        confidence = float(item.get("score") or item.get("confidence") or 0.0)
    elif isinstance(item, (list, tuple)) and len(item) >= 3:
        box, text, confidence = item[0], str(item[1]).strip(), float(item[2] or 0.0)
    else:
        return None

    if not text:
        return None
    return text, _polygon_to_bbox(box), confidence


def _polygon_to_bbox(box: Any) -> tuple[int, int, int, int]:
    if not box:
        return (0, 0, 0, 0)
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(
        isinstance(value, (int, float)) for value in box
    ):
        x, y, width, height = box
        return (int(x), int(y), int(width), int(height))

    points = list(box)
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))
