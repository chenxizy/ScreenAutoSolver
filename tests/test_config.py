import unittest
from pathlib import Path

from auto_solver.config import load_config


class ConfigTests(unittest.TestCase):
    def test_loads_minimal_yaml_config(self):
        yaml_text = """
api:
  url: "https://example.com/answer"
regions:
  question: {x: 1, y: 2, width: 3, height: 4}
  options: {x: 5, y: 6, width: 7, height: 8}
  next_button: {x: 9, y: 10, width: 11, height: 12}
"""
        tmp = Path("test_tmp")
        tmp.mkdir(exist_ok=True)
        path = tmp / "config.yaml"
        try:
            path.write_text(yaml_text, encoding="utf-8")
            config = load_config(path)
        finally:
            if path.exists():
                path.unlink()
            if tmp.exists():
                tmp.rmdir()

        self.assertEqual(config.api.url, "https://example.com/answer")
        self.assertEqual(config.api.model, "glm-5.1")
        self.assertEqual(config.regions.options.width, 7)
        self.assertTrue(config.runtime.strict_triple_check)

    def test_loads_new_runtime_options(self):
        yaml_text = """
api:
  url: "https://example.com/answer"
  model: "glm-5.1"
  temperature: 0.2
regions:
  question: {x: 1, y: 2, width: 3, height: 4}
  options: {x: 5, y: 6, width: 7, height: 8}
  next_button: {x: 9, y: 10, width: 11, height: 12}
runtime:
  strict_triple_check: false
  non_strict_use_confidence_margin: true
  non_strict_confidence_margin: 0.2
  cache_next_button_after_first_detection: true
  auto_minimize_on_run: false
"""
        tmp = Path("test_tmp")
        tmp.mkdir(exist_ok=True)
        path = tmp / "config.yaml"
        try:
            path.write_text(yaml_text, encoding="utf-8")
            config = load_config(path)
        finally:
            if path.exists():
                path.unlink()
            if tmp.exists():
                tmp.rmdir()

        self.assertFalse(config.runtime.strict_triple_check)
        self.assertTrue(config.runtime.non_strict_use_confidence_margin)
        self.assertEqual(config.runtime.non_strict_confidence_margin, 0.2)
        self.assertTrue(config.runtime.cache_next_button_after_first_detection)
        self.assertFalse(config.runtime.auto_minimize_on_run)
        self.assertEqual(config.api.model, "glm-5.1")
        self.assertEqual(config.api.temperature, 0.2)

    def test_string_booleans_are_parsed_as_booleans(self):
        yaml_text = """
api:
  url: "https://example.com/answer"
regions:
  question: {x: 1, y: 2, width: 3, height: 4}
  options: {x: 5, y: 6, width: 7, height: 8}
  next_button: {x: 9, y: 10, width: 11, height: 12}
runtime:
  strict_triple_check: "false"
  non_strict_use_confidence_margin: "off"
  require_manual_confirm: "0"
  auto_minimize_on_run: "no"
"""
        tmp = Path("test_tmp")
        tmp.mkdir(exist_ok=True)
        path = tmp / "config.yaml"
        try:
            path.write_text(yaml_text, encoding="utf-8")
            config = load_config(path)
        finally:
            if path.exists():
                path.unlink()
            if tmp.exists():
                tmp.rmdir()

        self.assertFalse(config.runtime.strict_triple_check)
        self.assertFalse(config.runtime.non_strict_use_confidence_margin)
        self.assertFalse(config.runtime.require_manual_confirm)
        self.assertFalse(config.runtime.auto_minimize_on_run)


if __name__ == "__main__":
    unittest.main()
