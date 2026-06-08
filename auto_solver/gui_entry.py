from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auto_solver.config import load_config
from auto_solver.gui import AutoSolverApp, main
from auto_solver.run_logging import RunLogger
from auto_solver.models import Region
from auto_solver.ocr import create_ocr_engine
from auto_solver.screen import ScreenController


def _smoke_test(argv: list[str]) -> int:
    smoke_dir = _arg_value(argv, "--smoke-dir") or "exe_smoke"
    out_dir = Path(smoke_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "smoke_result.json"
    result: dict[str, object] = {
        "gui_opened": False,
        "config_loaded": False,
        "screenshot_saved": False,
        "ocr_initialized": False,
        "log_saved": False,
        "errors": [],
    }

    try:
        app = AutoSolverApp()
        app.update()
        result["gui_opened"] = True
        app.destroy()

        config_path = _resource_path("config.example.yaml")
        config = load_config(config_path)
        result["config_loaded"] = True
        result["config_api_url"] = config.api.url

        screen = ScreenController()
        image = screen.screenshot(Region(x=0, y=0, width=64, height=64, name="smoke"))
        image_path = out_dir / "smoke_screenshot.png"
        image.save(image_path)
        result["screenshot_saved"] = image_path.exists()

        create_ocr_engine("rapidocr")
        result["ocr_initialized"] = True

        logger = RunLogger(out_dir / "runs")
        logger.save_json(1, "smoke_log.json", {"status": "ok"})
        result["log_saved"] = True
        result["status"] = "ok"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        errors = result.setdefault("errors", [])
        if isinstance(errors, list):
            errors.append(f"{type(exc).__name__}: {exc}")
        result["status"] = "failed"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1


def _arg_value(argv: list[str], name: str) -> str | None:
    if name not in argv:
        return None
    index = argv.index(name)
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def _resource_path(name: str) -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidate = Path(bundle_dir) / name
        if candidate.exists():
            return candidate
    return Path(name)


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(_smoke_test(sys.argv))
    main()
