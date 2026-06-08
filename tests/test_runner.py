import unittest

from auto_solver.config import default_config
from auto_solver.models import OcrLine
from auto_solver.runner import ScreenOnlySolver


class RunnerNextButtonTests(unittest.TestCase):
    def setUp(self):
        self.solver = ScreenOnlySolver.__new__(ScreenOnlySolver)
        self.solver.config = default_config()

    def test_next_button_available_status(self):
        state = self.solver.next_button_state([OcrLine("下一题", (0, 0, 80, 30), 0.9)])
        self.assertEqual(state.status, "available")
        self.assertTrue(state.available)

    def test_next_button_stop_status(self):
        state = self.solver.next_button_state([OcrLine("完成", (0, 0, 80, 30), 0.9)])
        self.assertEqual(state.status, "stop")
        self.assertFalse(state.available)

    def test_next_button_unknown_status(self):
        state = self.solver.next_button_state([OcrLine("继续", (0, 0, 80, 30), 0.9)])
        self.assertEqual(state.status, "unknown")
        self.assertFalse(state.available)


if __name__ == "__main__":
    unittest.main()
