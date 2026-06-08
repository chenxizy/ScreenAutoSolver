import unittest

from auto_solver.ocr import extract_options, infer_question_type
from auto_solver.models import OcrLine, Region


class OcrParsingTests(unittest.TestCase):
    def test_extracts_labeled_options(self):
        lines = [
            OcrLine("A. Apple", (10, 10, 100, 20), 0.8),
            OcrLine("B、Banana", (10, 40, 120, 20), 0.8),
        ]
        options = extract_options(lines, Region(0, 0, 300, 100))
        self.assertEqual([option.label for option in options], ["A", "B"])
        self.assertEqual(options[1].text, "Banana")

    def test_infers_true_false_type(self):
        lines = [
            OcrLine("正确", (10, 10, 100, 20), 0.8),
            OcrLine("错误", (10, 40, 120, 20), 0.8),
        ]
        options = extract_options(lines, Region(0, 0, 300, 100))
        self.assertEqual(infer_question_type(options), "true_false")


if __name__ == "__main__":
    unittest.main()
