import unittest

from auto_solver.decision import DecisionError, ResolveSettings, resolve_answer
from auto_solver.models import ApiAnswer, OptionOcr, Region


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.options = [
            OptionOcr("A", "正确", (100, 100, 180, 40), 0.9),
            OptionOcr("B", "错误", (100, 160, 180, 40), 0.9),
        ]

    def test_resolves_when_label_text_and_point_agree(self):
        answer = ApiAnswer(
            answer_label="A",
            answer_text="正确",
            click_point=(120, 120),
            confidence=0.91,
        )
        decision = resolve_answer(answer, self.options)
        self.assertEqual(decision.option.label, "A")
        self.assertEqual(decision.click_point, self.options[0].center())

    def test_rejects_disagreeing_evidence(self):
        answer = ApiAnswer(
            answer_label="A",
            answer_text="错误",
            click_point=(120, 120),
            confidence=0.91,
        )
        with self.assertRaises(DecisionError):
            resolve_answer(answer, self.options)

    def test_supports_question_relative_click_point_in_auto_mode(self):
        answer = ApiAnswer(
            answer_label="B",
            answer_text="错误",
            click_point=(20, 60),
            confidence=0.91,
        )
        settings = ResolveSettings(
            question_region=Region(100, 100, 300, 240),
            options_region=Region(100, 100, 300, 240),
        )
        decision = resolve_answer(answer, self.options, settings)
        self.assertEqual(decision.option.label, "B")

    def test_strict_mode_requires_all_three_evidence_types(self):
        answer = ApiAnswer(answer_label="A", answer_text="正确", confidence=0.91)
        with self.assertRaises(DecisionError):
            resolve_answer(answer, self.options)

    def test_non_strict_mode_selects_highest_scored_candidate(self):
        answer = ApiAnswer(
            answer_label="A",
            answer_text="错误",
            click_point=self.options[1].center(),
            confidence=0.4,
        )
        decision = resolve_answer(
            answer,
            self.options,
            ResolveSettings(strict_triple_check=False),
        )
        self.assertEqual(decision.option.label, "B")
        self.assertEqual(decision.evidence["selected_by"], "text")

    def test_non_strict_margin_can_reject_close_scores(self):
        answer = ApiAnswer(
            answer_label="A",
            click_point=self.options[1].center(),
            confidence=0.4,
        )
        with self.assertRaises(DecisionError):
            resolve_answer(
                answer,
                self.options,
                ResolveSettings(
                    strict_triple_check=False,
                    non_strict_use_confidence_margin=True,
                    non_strict_confidence_margin=0.05,
                ),
            )

    def test_non_strict_mode_ignores_unmatched_point(self):
        options = [
            OptionOcr("A", "Alpha", (100, 100, 180, 40), 0.9),
            OptionOcr("B", "Beta", (100, 160, 180, 40), 0.9),
        ]
        answer = ApiAnswer(
            answer_label="A",
            answer_text="Alpha",
            click_point=(9999, 9999),
            confidence=0.6,
        )
        decision = resolve_answer(
            answer,
            options,
            ResolveSettings(strict_triple_check=False),
        )
        self.assertEqual(decision.option.label, "A")
        self.assertIn("point_unmatched", decision.evidence)

    def test_non_strict_mode_ignores_unmatched_text(self):
        options = [
            OptionOcr("A", "Alpha", (100, 100, 180, 40), 0.9),
            OptionOcr("B", "Beta", (100, 160, 180, 40), 0.9),
        ]
        answer = ApiAnswer(
            answer_label="B",
            answer_text="No OCR option resembles this answer",
            click_point=options[1].center(),
            confidence=0.6,
        )
        decision = resolve_answer(
            answer,
            options,
            ResolveSettings(strict_triple_check=False),
        )
        self.assertEqual(decision.option.label, "B")
        self.assertIn("text_unmatched", decision.evidence)


if __name__ == "__main__":
    unittest.main()
