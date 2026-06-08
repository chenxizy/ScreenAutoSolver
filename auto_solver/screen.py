from __future__ import annotations

import time
from typing import Any

from .models import Region


class ScreenError(RuntimeError):
    pass


class ScreenController:
    def __init__(self, click_delay_seconds: float = 0.2) -> None:
        self.click_delay_seconds = click_delay_seconds

    def screenshot(self, region: Region | None = None) -> Any:
        try:
            return self._mss_screenshot(region)
        except ModuleNotFoundError:
            return self._pyautogui_screenshot(region)

    def click(self, x: int, y: int) -> None:
        pyautogui = self._require_pyautogui()
        pyautogui.moveTo(x, y, duration=0.08)
        pyautogui.click()
        time.sleep(self.click_delay_seconds)

    def position(self) -> tuple[int, int]:
        pyautogui = self._require_pyautogui()
        pos = pyautogui.position()
        return int(pos.x), int(pos.y)

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)

    @staticmethod
    def _mss_screenshot(region: Region | None) -> Any:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            monitor = (
                {
                    "left": region.x,
                    "top": region.y,
                    "width": region.width,
                    "height": region.height,
                }
                if region
                else sct.monitors[0]
            )
            raw = sct.grab(monitor)
            return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    @staticmethod
    def _pyautogui_screenshot(region: Region | None) -> Any:
        pyautogui = ScreenController._require_pyautogui()
        if region:
            return pyautogui.screenshot(
                region=(region.x, region.y, region.width, region.height)
            )
        return pyautogui.screenshot()

    @staticmethod
    def _require_pyautogui() -> Any:
        try:
            import pyautogui
        except ModuleNotFoundError as exc:
            raise ScreenError(
                "pyautogui is not installed. Install screen dependencies with: "
                'pip install -e ".[screen]"'
            ) from exc
        return pyautogui
