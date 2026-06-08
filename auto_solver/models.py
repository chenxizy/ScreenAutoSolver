from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int
    name: str = ""

    @classmethod
    def from_mapping(cls, data: JsonDict, name: str = "") -> "Region":
        return cls(
            x=int(data["x"]),
            y=int(data["y"]),
            width=int(data["width"]),
            height=int(data["height"]),
            name=name,
        )

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains_point(self, point: tuple[float, float], padding: int = 0) -> bool:
        px, py = point
        return (
            self.x - padding <= px <= self.right + padding
            and self.y - padding <= py <= self.bottom + padding
        )

    def to_dict(self) -> JsonDict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float = 0.0

    def with_offset(self, dx: int, dy: int) -> "OcrLine":
        x, y, w, h = self.bbox
        return OcrLine(self.text, (x + dx, y + dy, w, h), self.confidence)

    def to_dict(self) -> JsonDict:
        return {
            "text": self.text,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class OptionOcr:
    label: str
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float = 0.0

    @property
    def region(self) -> Region:
        x, y, width, height = self.bbox
        return Region(x=x, y=y, width=width, height=height, name=self.label)

    def center(self) -> tuple[int, int]:
        return self.region.center()

    def contains_point(self, point: tuple[float, float], padding: int = 8) -> bool:
        return self.region.contains_point(point, padding=padding)

    def to_payload(self) -> JsonDict:
        return {
            "label": self.label,
            "text": self.text,
            "bbox": list(self.bbox),
        }

    def to_dict(self) -> JsonDict:
        data = self.to_payload()
        data["confidence"] = self.confidence
        return data


@dataclass(frozen=True)
class ApiAnswer:
    answer_label: str | None = None
    answer_text: str | None = None
    click_point: tuple[float, float] | None = None
    confidence: float = 0.0
    reason: str | None = None

    @classmethod
    def from_mapping(cls, data: JsonDict) -> "ApiAnswer":
        point = data.get("click_point")
        click_point: tuple[float, float] | None
        if point is None:
            click_point = None
        elif isinstance(point, (list, tuple)) and len(point) == 2:
            click_point = (float(point[0]), float(point[1]))
        else:
            raise ValueError("click_point must be [x, y] when provided")

        return cls(
            answer_label=_empty_to_none(data.get("answer_label")),
            answer_text=_empty_to_none(data.get("answer_text")),
            click_point=click_point,
            confidence=float(data.get("confidence") or 0.0),
            reason=_empty_to_none(data.get("reason")),
        )

    def to_dict(self) -> JsonDict:
        return {
            "answer_label": self.answer_label,
            "answer_text": self.answer_text,
            "click_point": list(self.click_point) if self.click_point else None,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Decision:
    option: OptionOcr
    evidence: dict[str, str]
    confidence: float
    click_point: tuple[int, int]
    reason: str

    def to_dict(self) -> JsonDict:
        return {
            "selected_option": self.option.to_dict(),
            "evidence": self.evidence,
            "confidence": self.confidence,
            "click_point": list(self.click_point),
            "reason": self.reason,
        }


def _empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
