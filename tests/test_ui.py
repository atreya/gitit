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
    def test_colored_resolution_contains_ansi_and_command_box(self):
        stream = io.StringIO()
        ui = TerminalUI(stream, color=True)
        ui.resolution(RESOLUTION)
        output = stream.getvalue()
        self.assertIn("\x1b[", output)
        self.assertIn("·", output)
        self.assertIn("╭─", output)
        self.assertIn("╰", output)
        self.assertIn("git reset --soft", output)
        self.assertIn("test-model · 84 ms", output)
        self.assertNotIn("38;5;255", output)
        self.assertIn("\x1b[1mgit reset --soft", output)

    def test_plain_resolution_has_no_ansi(self):
        stream = io.StringIO()
        ui = TerminalUI(stream, color=False)
        ui.resolution(RESOLUTION)
        output = stream.getvalue()
        self.assertNotIn("\x1b[", output)
        self.assertIn("· Command ready test-model · 84 ms", output)
        self.assertIn("╭─ command", output)
        self.assertIn("rewrites local history", output)

    def test_horizontal_candidate_selector_moves_and_confirms(self):
        stream = io.StringIO()
        resolution = Resolution(
            "undo_commit",
            (
                RESOLUTION.candidates[0],
                Candidate(
                    ("git", "reset", "--mixed", "HEAD~1"),
                    "Removes the commit and keeps the changes unstaged.",
                    Risk.HISTORY_REWRITE,
                ),
            ),
            source="test-model",
        )
        keys = iter(["left", "enter"])
        selected = TerminalUI(stream, color=True).select_candidate(resolution, lambda: next(keys))
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIn("--mixed", selected.command)
        self.assertIn("Action", stream.getvalue())
        self.assertIn("Action", stream.getvalue())
        self.assertIn("\r\x1b[2K", stream.getvalue())
        self.assertNotIn("\x1b[u", stream.getvalue())
        self.assertNotIn("\x1b[J", stream.getvalue())

    def test_mutating_selector_defaults_to_cancel(self):
        stream = io.StringIO()
        keys = iter(["enter"])
        selected = TerminalUI(stream, color=True).select_candidate(RESOLUTION, lambda: next(keys))
        self.assertIsNone(selected)

    def test_read_only_selector_defaults_to_run(self):
        stream = io.StringIO()
        keys = iter(["enter"])
        candidate = Candidate(("git", "status"), "Shows repository status safely.", Risk.READ_ONLY)
        resolution = Resolution("status", (candidate,), source="test-model")
        selected = TerminalUI(stream, color=True).select_candidate(resolution, lambda: next(keys))
        self.assertEqual(candidate, selected)


if __name__ == "__main__":
    unittest.main()
