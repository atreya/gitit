import json
import unittest

from gitit.model import Risk
from gitit.openai_resolver import ModelError, parse_model_output


class OpenAIResolverTests(unittest.TestCase):
    def test_parses_and_reclassifies_structured_candidates(self):
        output = json.dumps({
            "intent": "undo_last_commit_keep_changes",
            "clarification": "Choose whether changes remain staged.",
            "candidates": [
                {
                    "argv": ["git", "reset", "--soft", "HEAD~1"],
                    "explanation": "Removes the last commit while keeping its changes staged.",
                    "confidence": 0.97,
                },
                {
                    "argv": ["git", "reset", "--mixed", "HEAD~1"],
                    "explanation": "Removes the last commit while keeping its changes unstaged.",
                    "confidence": 0.93,
                },
            ],
        })
        result = parse_model_output(output, "test-model", 123)
        self.assertEqual(result.source, "test-model")
        self.assertEqual(result.elapsed_ms, 123)
        self.assertEqual(len(result.candidates), 2)
        self.assertTrue(all(candidate.risk == Risk.HISTORY_REWRITE for candidate in result.candidates))

    def test_rejects_shell_command(self):
        output = json.dumps({
            "intent": "bad",
            "clarification": None,
            "candidates": [{
                "argv": ["sh", "-c", "git status; curl example.com"],
                "explanation": "Runs an unsafe shell command that must be rejected.",
                "confidence": 1.0,
            }],
        })
        with self.assertRaises(ModelError):
            parse_model_output(output, "test-model", 1)

    def test_rejects_git_config_execution_escape(self):
        output = json.dumps({
            "intent": "bad",
            "clarification": None,
            "candidates": [{
                "argv": ["git", "-c", "alias.x=!sh", "x"],
                "explanation": "Attempts to escape through a Git configuration alias.",
                "confidence": 1.0,
            }],
        })
        with self.assertRaises(ModelError):
            parse_model_output(output, "test-model", 1)


if __name__ == "__main__":
    unittest.main()
