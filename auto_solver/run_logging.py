from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, root: str | Path) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.root = Path(root) / timestamp
        self.root.mkdir(parents=True, exist_ok=True)

    def attempt_dir(self, attempt_index: int) -> Path:
        path = self.root / f"attempt_{attempt_index:04d}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, attempt_index: int, name: str, data: Any) -> Path:
        path = self.attempt_dir(attempt_index) / name
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return path

    def save_image(self, attempt_index: int, name: str, image: Any) -> Path:
        path = self.attempt_dir(attempt_index) / name
        image.save(path)
        return path

    def save_text(self, attempt_index: int, name: str, text: str) -> Path:
        path = self.attempt_dir(attempt_index) / name
        path.write_text(text, encoding="utf-8")
        return path
