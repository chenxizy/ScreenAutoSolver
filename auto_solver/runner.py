from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import ImageChops, ImageStat

from .api import AnswerApiClient, image_to_base64_png
from .config import SolverConfig
from .decision import DecisionError, ResolveSettings, resolve_answer
from .run_logging import RunLogger
from .models import ApiAnswer, Decision, JsonDict, OcrLine, OptionOcr, Region
from .ocr import create_ocr_engine, extract_options, extract_question_text, infer_question_type
from .screen import ScreenController


class SolverStop(RuntimeError):
    pass


@dataclass(frozen=True)
class NextButtonState:
    status: str
    text: str
    lines: list[OcrLine]

    @property
    def available(self) -> bool:
        return self.status == "available"


@dataclass(frozen=True)
class AttemptCapture:
    question_image: Any
    options_image: Any
    next_image: Any
    question_lines: list[OcrLine]
    option_lines: list[OcrLine]
    next_lines: list[OcrLine]
    options: list[OptionOcr]
    question_text: str
    question_type: str


class ScreenOnlySolver:
    def __init__(
        self,
        config: SolverConfig,
        screen: ScreenController | None = None,
        api_client: AnswerApiClient | None = None,
        ocr_engine: Any | None = None,
        logger: RunLogger | None = None,
    ) -> None:
        self.config = config
        self.screen = screen or ScreenController(config.runtime.click_delay_seconds)
        self.api_client = api_client or AnswerApiClient(config.api)
        self.ocr = ocr_engine or create_ocr_engine(config.ocr.engine)
        self.logger = logger or RunLogger(config.runtime.log_dir)
        self._cached_next_button_state: NextButtonState | None = None

    def run(self, once: bool = False) -> None:
        max_questions = 1 if once else self.config.runtime.max_questions
        for attempt_index in range(1, max_questions + 1):
            print(f"[auto-solver] attempt {attempt_index}: capture")
            result = self.solve_once(attempt_index)
            if result == "stop":
                print("[auto-solver] stop condition reached")
                return
            if once:
                return
        print(f"[auto-solver] max_questions reached: {max_questions}")

    def solve_once(self, attempt_index: int) -> str:
        capture = self.capture(attempt_index)
        payload = self.build_payload(capture, attempt_index)
        self.logger.save_json(attempt_index, "payload.json", _without_large_image(payload))

        if not capture.options:
            return self._pause_or_stop(
                attempt_index,
                "OCR did not find any options. Check options region or OCR engine.",
            )

        answer = self.api_client.ask(payload)
        raw_response = getattr(self.api_client, "last_raw_response", None)
        if raw_response is not None:
            self.logger.save_json(attempt_index, "raw_response.json", raw_response)
        self.logger.save_json(attempt_index, "response.json", answer.to_dict())

        try:
            decision = self.resolve(answer, capture.options)
        except DecisionError as exc:
            self.logger.save_text(attempt_index, "mismatch.txt", str(exc))
            manual_decision = self._manual_mismatch(attempt_index, capture.options, str(exc))
            if isinstance(manual_decision, str):
                return manual_decision
            decision = manual_decision

        self.logger.save_json(attempt_index, "decision.json", decision.to_dict())
        if self.config.runtime.require_manual_confirm:
            decision = self._manual_confirm(attempt_index, capture.options, decision)

        if self.config.runtime.dry_run:
            print(
                "[auto-solver] dry-run: would click "
                f"{decision.option.label} at {decision.click_point}"
            )
            return "continue"

        before_options = capture.options_image
        self.screen.click(*decision.click_point)
        after_options = self.screen.screenshot(self.config.regions.options)
        self.logger.save_image(attempt_index, "after_options.png", after_options)

        diff = selected_option_diff(
            before_options,
            after_options,
            decision.option,
            self.config.regions.options,
        )
        self.logger.save_json(attempt_index, "selection_check.json", {"diff": diff})
        if diff < self.config.runtime.selection_diff_threshold:
            status = self._pause_or_continue(
                f"Selection visual diff is low ({diff:.2f}). Press Enter to continue, "
                "type 's' to stop: "
            )
            if status == "stop":
                return "stop"

        next_state = self.next_button_state_for_click(attempt_index)
        if next_state.status == "stop":
            self.logger.save_json(
                attempt_index,
                "next_button_state.json",
                {"status": next_state.status, "text": next_state.text},
            )
            return "stop"
        if next_state.status == "unknown":
            self.logger.save_json(
                attempt_index,
                "next_button_state.json",
                {"status": next_state.status, "text": next_state.text},
            )
            status = self._pause_or_continue(
                "Next button OCR did not confirm a next action. "
                "Press Enter/Yes to click the configured next-button region anyway, "
                "or type 's'/No to stop: "
            )
            if status == "stop":
                return "stop"
        else:
            self.logger.save_json(
                attempt_index,
                "next_button_state.json",
                {"status": next_state.status, "text": next_state.text},
            )

        before_question = capture.question_image
        next_x, next_y = self.config.regions.next_button.center()
        self.screen.click(next_x, next_y)
        self.screen.sleep(self.config.runtime.next_delay_seconds)

        if self.config.runtime.stop_if_question_unchanged:
            after_question = self.screen.screenshot(self.config.regions.question)
            self.logger.save_image(attempt_index, "after_next_question.png", after_question)
            qdiff = image_mean_abs_diff(before_question, after_question)
            self.logger.save_json(attempt_index, "next_check.json", {"diff": qdiff})
            if qdiff < self.config.runtime.unchanged_question_threshold:
                return "stop"

        return "continue"

    def capture(self, attempt_index: int) -> AttemptCapture:
        regions = self.config.regions
        question_image = self.screen.screenshot(regions.question)
        options_image = self.screen.screenshot(regions.options)

        self.logger.save_image(attempt_index, "question.png", question_image)
        self.logger.save_image(attempt_index, "options.png", options_image)

        question_lines = self._ocr_region(question_image, regions.question)
        option_lines = self._ocr_region(options_image, regions.options)
        if (
            self.config.runtime.cache_next_button_after_first_detection
            and self._cached_next_button_state
        ):
            next_image = None
            next_lines = self._cached_next_button_state.lines
            self.logger.save_json(
                attempt_index,
                "next_button_cached_state_before_answer.json",
                {
                    "status": self._cached_next_button_state.status,
                    "text": self._cached_next_button_state.text,
                    "source": "cached",
                },
            )
        else:
            next_image = self.screen.screenshot(regions.next_button)
            self.logger.save_image(attempt_index, "next_button.png", next_image)
            next_lines = self._ocr_region(next_image, regions.next_button)
            self._maybe_cache_next_button_state(self.next_button_state(next_lines))
        question_text = extract_question_text(question_lines)
        options = extract_options(option_lines, regions.options)
        question_type = infer_question_type(options)

        self.logger.save_json(
            attempt_index,
            "ocr.json",
            {
                "question_lines": [line.to_dict() for line in question_lines],
                "option_lines": [line.to_dict() for line in option_lines],
                "next_lines": [line.to_dict() for line in next_lines],
                "question_text": question_text,
                "options": [option.to_dict() for option in options],
                "question_type": question_type,
            },
        )

        return AttemptCapture(
            question_image=question_image,
            options_image=options_image,
            next_image=next_image,
            question_lines=question_lines,
            option_lines=option_lines,
            next_lines=next_lines,
            options=options,
            question_text=question_text,
            question_type=question_type,
        )

    def build_payload(self, capture: AttemptCapture, attempt_index: int) -> JsonDict:
        return {
            "question_text_ocr": capture.question_text,
            "options_ocr": [option.to_payload() for option in capture.options],
            "screenshot_base64": image_to_base64_png(capture.question_image),
            "question_type": capture.question_type,
            "attempt_index": attempt_index,
        }

    def resolve(self, answer: ApiAnswer, options: list[OptionOcr]) -> Decision:
        settings = ResolveSettings(
            text_match_threshold=self.config.ocr.text_match_threshold,
            strict_triple_check=self.config.runtime.strict_triple_check,
            non_strict_use_confidence_margin=(
                self.config.runtime.non_strict_use_confidence_margin
            ),
            non_strict_confidence_margin=(
                self.config.runtime.non_strict_confidence_margin
            ),
            click_point_space=self.config.api.click_point_space,
            question_region=self.config.regions.question,
            options_region=self.config.regions.options,
        )
        return resolve_answer(answer, options, settings)

    def next_button_available(self, lines: list[OcrLine]) -> bool:
        return self.next_button_state(lines).available

    def next_button_state(self, lines: list[OcrLine]) -> NextButtonState:
        text = extract_question_text(lines)
        if not text:
            return NextButtonState(status="unknown", text=text, lines=lines)
        if any(keyword in text for keyword in self.config.runtime.stop_keywords):
            return NextButtonState(status="stop", text=text, lines=lines)
        if any(keyword in text for keyword in self.config.runtime.next_keywords):
            return NextButtonState(status="available", text=text, lines=lines)
        return NextButtonState(status="unknown", text=text, lines=lines)

    def capture_next_button_state(
        self,
        attempt_index: int,
        suffix: str = "current",
    ) -> NextButtonState:
        image = self.screen.screenshot(self.config.regions.next_button)
        self.logger.save_image(attempt_index, f"next_button_{suffix}.png", image)
        lines = self._ocr_region(image, self.config.regions.next_button)
        self.logger.save_json(
            attempt_index,
            f"next_button_{suffix}_ocr.json",
            {
                "lines": [line.to_dict() for line in lines],
                "text": extract_question_text(lines),
            },
        )
        state = self.next_button_state(lines)
        self._maybe_cache_next_button_state(state)
        return state

    def next_button_state_for_click(self, attempt_index: int) -> NextButtonState:
        if (
            self.config.runtime.cache_next_button_after_first_detection
            and self._cached_next_button_state
        ):
            state = self._cached_next_button_state
            self.logger.save_json(
                attempt_index,
                "next_button_cached_state.json",
                {"status": state.status, "text": state.text, "source": "cached"},
            )
            return state
        return self.capture_next_button_state(attempt_index, suffix="after_answer")

    def _maybe_cache_next_button_state(self, state: NextButtonState) -> None:
        if (
            self.config.runtime.cache_next_button_after_first_detection
            and self._cached_next_button_state is None
            and state.status == "available"
        ):
            self._cached_next_button_state = state

    def _ocr_region(self, image: Any, region: Region) -> list[OcrLine]:
        lines = self.ocr.recognize(image, offset=(region.x, region.y))
        return [
            line
            for line in lines
            if line.confidence >= self.config.ocr.min_line_confidence
        ]

    def _manual_mismatch(
        self,
        attempt_index: int,
        options: list[OptionOcr],
        message: str,
    ) -> Decision | str:
        print(f"[auto-solver] answer mismatch: {message}")
        print("[auto-solver] options:")
        for option in options:
            print(f"  {option.label}: {option.text}")
        choice = input(
            "Type an option label to click manually, press Enter to pause only, "
            "or type 's' to stop: "
        ).strip()
        if choice.lower() == "s":
            return "stop"
        if not choice:
            return self._pause_or_stop(attempt_index, "Paused after mismatch.")
        selected = next((opt for opt in options if opt.label.upper() == choice.upper()), None)
        if not selected:
            print(f"[auto-solver] unknown label: {choice}")
            return "stop"
        return Decision(
            option=selected,
            evidence={"manual_mismatch": selected.label},
            confidence=0.0,
            click_point=selected.center(),
            reason=f"Manual mismatch override: {message}",
        )

    def _manual_confirm(
        self,
        attempt_index: int,
        options: list[OptionOcr],
        decision: Decision,
    ) -> Decision:
        print(
            "[auto-solver] resolved "
            f"{decision.option.label}: {decision.option.text} at {decision.click_point}"
        )
        choice = input(
            "Press Enter to accept, type another label to override, or type 's' to stop: "
        ).strip()
        if choice.lower() == "s":
            raise SolverStop("Stopped by user")
        if not choice:
            return decision
        selected = next((opt for opt in options if opt.label.upper() == choice.upper()), None)
        if not selected:
            raise SolverStop(f"Unknown manual label: {choice}")
        return Decision(
            option=selected,
            evidence={"manual": selected.label},
            confidence=decision.confidence,
            click_point=selected.center(),
            reason="Manual override",
        )

    def _pause_or_stop(self, attempt_index: int, reason: str) -> str:
        self.logger.save_text(attempt_index, "pause.txt", reason)
        print(f"[auto-solver] {reason}")
        status = self._pause_or_continue("Press Enter to continue, type 's' to stop: ")
        return "stop" if status == "stop" else "continue"

    @staticmethod
    def _pause_or_continue(prompt: str) -> str:
        answer = input(prompt).strip().lower()
        return "stop" if answer == "s" else "continue"


def selected_option_diff(
    before_options: Any,
    after_options: Any,
    option: OptionOcr,
    options_region: Region,
) -> float:
    x, y, width, height = option.bbox
    left = max(0, x - options_region.x)
    top = max(0, y - options_region.y)
    right = max(left + 1, left + width)
    bottom = max(top + 1, top + height)
    before_crop = before_options.crop((left, top, right, bottom)).convert("RGB")
    after_crop = after_options.crop((left, top, right, bottom)).convert("RGB")
    return image_mean_abs_diff(before_crop, after_crop)


def image_mean_abs_diff(before: Any, after: Any) -> float:
    diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
    stat = ImageStat.Stat(diff)
    return float(sum(stat.mean) / len(stat.mean))


def _without_large_image(payload: JsonDict) -> JsonDict:
    clean = dict(payload)
    image = clean.get("screenshot_base64")
    if isinstance(image, str):
        clean["screenshot_base64"] = f"<base64 png: {len(image)} chars>"
    return clean
