from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import JsonDict, Region


@dataclass(frozen=True)
class ApiConfig:
    url: str
    api_key: str = ""
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    model: str = "glm-5.1"
    temperature: float = 0.1
    timeout_seconds: float = 30.0
    click_point_space: str = "auto"

    @classmethod
    def from_mapping(cls, data: JsonDict) -> "ApiConfig":
        return cls(
            url=str(data["url"]),
            api_key=str(data.get("api_key") or ""),
            api_key_header=str(data.get("api_key_header") or "Authorization"),
            api_key_prefix=str(data.get("api_key_prefix") or "Bearer "),
            model=str(data.get("model") or "glm-5.1"),
            temperature=float(data.get("temperature") or 0.1),
            timeout_seconds=float(data.get("timeout_seconds") or 30.0),
            click_point_space=str(data.get("click_point_space") or "auto"),
        )

    def to_dict(self) -> JsonDict:
        return {
            "url": self.url,
            "api_key": self.api_key,
            "api_key_header": self.api_key_header,
            "api_key_prefix": self.api_key_prefix,
            "model": self.model,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "click_point_space": self.click_point_space,
        }


@dataclass(frozen=True)
class RegionConfig:
    question: Region
    options: Region
    next_button: Region

    @classmethod
    def from_mapping(cls, data: JsonDict) -> "RegionConfig":
        return cls(
            question=Region.from_mapping(data["question"], name="question"),
            options=Region.from_mapping(data["options"], name="options"),
            next_button=Region.from_mapping(data["next_button"], name="next_button"),
        )

    def to_dict(self) -> JsonDict:
        return {
            "question": self.question.to_dict(),
            "options": self.options.to_dict(),
            "next_button": self.next_button.to_dict(),
        }


@dataclass(frozen=True)
class OcrConfig:
    engine: str = "rapidocr"
    text_match_threshold: float = 0.62
    min_line_confidence: float = 0.0

    @classmethod
    def from_mapping(cls, data: JsonDict | None) -> "OcrConfig":
        data = data or {}
        return cls(
            engine=str(data.get("engine") or "rapidocr"),
            text_match_threshold=float(data.get("text_match_threshold") or 0.62),
            min_line_confidence=float(data.get("min_line_confidence") or 0.0),
        )

    def to_dict(self) -> JsonDict:
        return {
            "engine": self.engine,
            "text_match_threshold": self.text_match_threshold,
            "min_line_confidence": self.min_line_confidence,
        }


@dataclass(frozen=True)
class RuntimeConfig:
    log_dir: str = "runs"
    max_questions: int = 100
    click_delay_seconds: float = 0.8
    next_delay_seconds: float = 1.2
    require_manual_confirm: bool = False
    dry_run: bool = False
    strict_triple_check: bool = True
    non_strict_use_confidence_margin: bool = False
    non_strict_confidence_margin: float = 0.15
    cache_next_button_after_first_detection: bool = False
    auto_minimize_on_run: bool = True
    selection_diff_threshold: float = 3.0
    unchanged_question_threshold: float = 2.0
    stop_if_question_unchanged: bool = True
    next_keywords: list[str] = field(
        default_factory=lambda: ["下一题", "下一步", "Next", "next"]
    )
    stop_keywords: list[str] = field(
        default_factory=lambda: ["完成", "提交", "结束", "Finish", "Submit"]
    )

    @classmethod
    def from_mapping(cls, data: JsonDict | None) -> "RuntimeConfig":
        data = data or {}
        return cls(
            log_dir=str(data.get("log_dir") or "runs"),
            max_questions=int(data.get("max_questions") or 100),
            click_delay_seconds=float(data.get("click_delay_seconds") or 0.8),
            next_delay_seconds=float(data.get("next_delay_seconds") or 1.2),
            require_manual_confirm=_as_bool(
                data.get("require_manual_confirm"), False
            ),
            dry_run=_as_bool(data.get("dry_run"), False),
            strict_triple_check=_as_bool(data.get("strict_triple_check"), True),
            non_strict_use_confidence_margin=_as_bool(
                data.get("non_strict_use_confidence_margin"), False
            ),
            non_strict_confidence_margin=float(
                data.get("non_strict_confidence_margin") or 0.15
            ),
            cache_next_button_after_first_detection=_as_bool(
                data.get("cache_next_button_after_first_detection"), False
            ),
            auto_minimize_on_run=_as_bool(data.get("auto_minimize_on_run"), True),
            selection_diff_threshold=float(data.get("selection_diff_threshold") or 3.0),
            unchanged_question_threshold=float(
                data.get("unchanged_question_threshold") or 2.0
            ),
            stop_if_question_unchanged=_as_bool(
                data.get("stop_if_question_unchanged"), True
            ),
            next_keywords=list(data.get("next_keywords") or cls().next_keywords),
            stop_keywords=list(data.get("stop_keywords") or cls().stop_keywords),
        )

    def to_dict(self) -> JsonDict:
        return {
            "log_dir": self.log_dir,
            "max_questions": self.max_questions,
            "click_delay_seconds": self.click_delay_seconds,
            "next_delay_seconds": self.next_delay_seconds,
            "require_manual_confirm": self.require_manual_confirm,
            "dry_run": self.dry_run,
            "strict_triple_check": self.strict_triple_check,
            "non_strict_use_confidence_margin": self.non_strict_use_confidence_margin,
            "non_strict_confidence_margin": self.non_strict_confidence_margin,
            "cache_next_button_after_first_detection": (
                self.cache_next_button_after_first_detection
            ),
            "auto_minimize_on_run": self.auto_minimize_on_run,
            "selection_diff_threshold": self.selection_diff_threshold,
            "unchanged_question_threshold": self.unchanged_question_threshold,
            "stop_if_question_unchanged": self.stop_if_question_unchanged,
            "next_keywords": self.next_keywords,
            "stop_keywords": self.stop_keywords,
        }


@dataclass(frozen=True)
class SolverConfig:
    api: ApiConfig
    regions: RegionConfig
    ocr: OcrConfig = field(default_factory=OcrConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    @classmethod
    def from_mapping(cls, data: JsonDict) -> "SolverConfig":
        return cls(
            api=ApiConfig.from_mapping(data["api"]),
            regions=RegionConfig.from_mapping(data["regions"]),
            ocr=OcrConfig.from_mapping(data.get("ocr")),
            runtime=RuntimeConfig.from_mapping(data.get("runtime")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "api": self.api.to_dict(),
            "regions": self.regions.to_dict(),
            "ocr": self.ocr.to_dict(),
            "runtime": self.runtime.to_dict(),
        }

    def with_overrides(
        self,
        dry_run: bool | None = None,
        max_questions: int | None = None,
    ) -> "SolverConfig":
        runtime = RuntimeConfig(
            log_dir=self.runtime.log_dir,
            max_questions=max_questions
            if max_questions is not None
            else self.runtime.max_questions,
            click_delay_seconds=self.runtime.click_delay_seconds,
            next_delay_seconds=self.runtime.next_delay_seconds,
            require_manual_confirm=self.runtime.require_manual_confirm,
            dry_run=dry_run if dry_run is not None else self.runtime.dry_run,
            strict_triple_check=self.runtime.strict_triple_check,
            non_strict_use_confidence_margin=(
                self.runtime.non_strict_use_confidence_margin
            ),
            non_strict_confidence_margin=self.runtime.non_strict_confidence_margin,
            cache_next_button_after_first_detection=(
                self.runtime.cache_next_button_after_first_detection
            ),
            auto_minimize_on_run=self.runtime.auto_minimize_on_run,
            selection_diff_threshold=self.runtime.selection_diff_threshold,
            unchanged_question_threshold=self.runtime.unchanged_question_threshold,
            stop_if_question_unchanged=self.runtime.stop_if_question_unchanged,
            next_keywords=self.runtime.next_keywords,
            stop_keywords=self.runtime.stop_keywords,
        )
        return SolverConfig(
            api=self.api,
            regions=self.regions,
            ocr=self.ocr,
            runtime=runtime,
        )


def load_config(path: str | Path) -> SolverConfig:
    yaml = _require_yaml()
    with Path(path).open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return SolverConfig.from_mapping(data)


def save_config(config: SolverConfig, path: str | Path) -> None:
    yaml = _require_yaml()
    with Path(path).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config.to_dict(), fh, allow_unicode=True, sort_keys=False)


def default_config() -> SolverConfig:
    return SolverConfig(
        api=ApiConfig(url="https://example.com/answer"),
        regions=RegionConfig(
            question=Region(x=100, y=100, width=900, height=420, name="question"),
            options=Region(x=120, y=320, width=860, height=260, name="options"),
            next_button=Region(x=820, y=700, width=160, height=60, name="next_button"),
        ),
        ocr=OcrConfig(),
        runtime=RuntimeConfig(),
    )


def _require_yaml() -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required to read or write config.yaml") from exc
    return yaml


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default
