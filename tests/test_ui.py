import io
import unittest

from gitit.model import Candidate, Resolution, Risk
from gitit.ui import TerminalUI


RESOLUTION = Resolution(
    "undo_commit",
    (
        Candidate(
            ("git", "reset", "--soft", "HEAD~1"),
            "Removes the last commit while keeping all changes staged.",
            Risk.HISTORY_REWRITE,
        ),
    ),
    source="test-model",
    elapsed_ms=84,
)


class TerminalUITests(unittest.TestCase):
    def test_colored_resolution_contains_ansi_and_status_dot(self):
        stream = io.StringIO()
        ui = TerminalUI(stream, color=True)
        ui.resolution(RESOLUTION)
        output = stream.getvalue()
        self.assertIn("\x1b[", output)
        self.assertIn("●", output)
        self.assertIn("git reset --soft", output)
        self.assertIn("test-model · 84 ms", output)

    def test_plain_resolution_has_no_ansi(self):
        stream = io.StringIO()
        ui = TerminalUI(stream, color=False)
        ui.resolution(RESOLUTION)
        output = stream.getvalue()
        self.assertNotIn("\x1b[", output)
        self.assertIn("● Command ready test-model · 84 ms", output)
        self.assertIn("rewrites local history", output)


if __name__ == "__main__":
    unittest.main()
