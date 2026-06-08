import unittest

from auto_solver.api import parse_answer_content, parse_answer_response


class ApiParsingTests(unittest.TestCase):
    def test_parses_direct_answer_response(self):
        answer = parse_answer_response(
            {
                "answer_label": "A",
                "answer_text": "Alpha",
                "click_point": [12, 34],
                "confidence": 0.9,
            }
        )
        self.assertEqual(answer.answer_label, "A")
        self.assertEqual(answer.answer_text, "Alpha")
        self.assertEqual(answer.click_point, (12.0, 34.0))

    def test_parses_chat_completion_json_content(self):
        answer = parse_answer_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"answer_label":"B","answer_text":"Beta",'
                                '"click_point":[50,60],"confidence":0.88}'
                            )
                        }
                    }
                ]
            }
        )
        self.assertEqual(answer.answer_label, "B")
        self.assertEqual(answer.answer_text, "Beta")
        self.assertEqual(answer.click_point, (50.0, 60.0))

    def test_parses_chat_completion_plain_label(self):
        answer = parse_answer_content("答案：C")
        self.assertEqual(answer.answer_label, "C")

    def test_parses_alias_fields(self):
        answer = parse_answer_content('{"choice":"D","text":"Delta","point":[1,2]}')
        self.assertEqual(answer.answer_label, "D")
        self.assertEqual(answer.answer_text, "Delta")
        self.assertEqual(answer.click_point, (1.0, 2.0))


if __name__ == "__main__":
    unittest.main()
