from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from .config import ApiConfig
from .models import ApiAnswer, JsonDict


class ApiClientError(RuntimeError):
    pass


class AnswerApiClient:
    def __init__(self, config: ApiConfig) -> None:
        self.config = config
        self.last_raw_response: JsonDict | None = None

    def ask(self, payload: JsonDict) -> ApiAnswer:
        try:
            import httpx
        except ModuleNotFoundError as exc:
            raise ApiClientError("httpx is required for API calls") from exc

        headers: dict[str, str] = {}
        if self.config.api_key:
            prefix = self.config.api_key_prefix if self.config.api_key_header else ""
            headers[self.config.api_key_header] = f"{prefix}{self.config.api_key}"

        request_body = self._build_request_body(payload)
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.post(self.config.url, json=request_body, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise ApiClientError(f"Answer API request failed: {exc}") from exc

        if not isinstance(data, dict):
            raise ApiClientError("Answer API response must be a JSON object")
        self.last_raw_response = data
        try:
            return parse_answer_response(data)
        except Exception as exc:
            raise ApiClientError(f"Answer API response is invalid: {exc}") from exc

    def _build_request_body(self, payload: JsonDict) -> JsonDict:
        if "/chat/completions" not in self.config.url:
            return payload

        question_text = str(payload.get("question_text_ocr") or "").strip()
        question_type = str(payload.get("question_type") or "").strip()
        attempt_index = payload.get("attempt_index")
        options = payload.get("options_ocr") or []
        option_lines = []
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                label = option.get("label")
                text = option.get("text")
                bbox = option.get("bbox")
                option_lines.append(f"{label}. {text} bbox={bbox}")

        user_text = "\n".join(
            [
                "Question OCR:",
                question_text,
                "",
                f"Question type: {question_type}",
                f"Attempt index: {attempt_index}",
                "",
                "Options OCR:",
                "\n".join(option_lines),
                "",
                "Choose exactly one option from the OCR options.",
                "For click_point, return the center of the selected option bbox in absolute screen coordinates.",
                "Return only a compact JSON object with these keys:",
                '{"answer_label":"A","answer_text":"...","click_point":[x,y],"confidence":0.0,"reason":"optional"}',
            ]
        )
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an answer selection engine for authorized practice "
                        "questions. Return only valid JSON. Do not include markdown."
                    ),
                },
                {"role": "user", "content": user_text},
            ],
            "temperature": self.config.temperature,
        }


def parse_answer_response(data: JsonDict) -> ApiAnswer:
    if _has_answer_fields(data):
        return ApiAnswer.from_mapping(_normalize_answer_mapping(data))

    content = _extract_chat_content(data)
    if content is None:
        raise ValueError(
            "response did not include answer_label/answer_text/click_point or "
            "choices[0].message.content"
        )
    return parse_answer_content(content)


def parse_answer_content(content: str) -> ApiAnswer:
    text = str(content).strip()
    if not text:
        raise ValueError("chat completion content is empty")

    json_text = _extract_json_object(text)
    if json_text:
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return ApiAnswer.from_mapping(_normalize_answer_mapping(parsed))

    label = _extract_label(text)
    if label:
        return ApiAnswer(answer_label=label, answer_text=text, confidence=0.8)

    return ApiAnswer(answer_text=text, confidence=0.5)


def _has_answer_fields(data: JsonDict) -> bool:
    return any(
        key in data
        for key in (
            "answer_label",
            "answer_text",
            "click_point",
            "label",
            "answer",
            "option",
            "choice",
            "text",
            "point",
            "clickPoint",
        )
    )


def _normalize_answer_mapping(data: JsonDict) -> JsonDict:
    normalized = dict(data)
    if not normalized.get("answer_label"):
        normalized["answer_label"] = _first_present(
            data, "label", "answer", "option", "choice", "answerLabel"
        )
    if not normalized.get("answer_text"):
        normalized["answer_text"] = _first_present(
            data, "text", "answerText", "answer_text", "content"
        )
    if not normalized.get("click_point"):
        normalized["click_point"] = _first_present(
            data, "point", "clickPoint", "click_point", "coordinate", "coordinates"
        )
    return normalized


def _first_present(data: JsonDict, *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_chat_content(data: JsonDict) -> str | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts) if parts else None
        if content is not None:
            return str(content)
    delta = first.get("delta")
    if isinstance(delta, dict) and delta.get("content") is not None:
        return str(delta["content"])
    if first.get("text") is not None:
        return str(first["text"])
    return None


def _extract_json_object(text: str) -> str | None:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.S)
    if fence:
        return fence.group(1)
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    return match.group(0) if match else None


def _extract_label(text: str) -> str | None:
    stripped = text.strip()
    if re.fullmatch(r"[A-Ha-h]", stripped):
        return stripped.upper()
    match = re.search(
        r"(?:answer_label|answer|option|choice|label|答案|选项)\s*[:：=]?\s*([A-Ha-h])\b",
        stripped,
    )
    if match:
        return match.group(1).upper()
    return None


def image_to_base64_png(image: Any) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
