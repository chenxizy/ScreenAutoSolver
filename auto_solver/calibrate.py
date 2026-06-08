from __future__ import annotations

from pathlib import Path

from .config import ApiConfig, OcrConfig, RegionConfig, RuntimeConfig, SolverConfig, save_config
from .models import Region
from .screen import ScreenController


def run_calibration(config_path: str | Path) -> None:
    screen = ScreenController()
    print("Calibration uses only mouse coordinates.")
    print("For each region, move the cursor to the requested corner and press Enter.")

    question = _capture_region(screen, "question area")
    options = _capture_region(screen, "options area")
    next_button = _capture_region(screen, "next button area")
    api_url = input("Answer API URL: ").strip() or "https://example.com/answer"
    api_key = input("Answer API key (optional): ").strip()

    config = SolverConfig(
        api=ApiConfig(url=api_url, api_key=api_key),
        regions=RegionConfig(
            question=question,
            options=options,
            next_button=next_button,
        ),
        ocr=OcrConfig(),
        runtime=RuntimeConfig(),
    )
    save_config(config, config_path)
    print(f"Saved config to {config_path}")


def _capture_region(screen: ScreenController, label: str) -> Region:
    input(f"Move cursor to TOP-LEFT of {label}, then press Enter.")
    x1, y1 = screen.position()
    input(f"Move cursor to BOTTOM-RIGHT of {label}, then press Enter.")
    x2, y2 = screen.position()
    x = min(x1, x2)
    y = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid region for {label}: width and height must be positive")
    region = Region(x=x, y=y, width=width, height=height, name=label)
    print(f"{label}: {region.to_dict()}")
    return region
