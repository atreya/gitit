import unittest
from pathlib import Path

from gitit.context import RepositoryContext
from gitit.model import Risk
from gitit.resolver import resolve


CTX = RepositoryContext(Path("/repo"), "feature", ("feature", "main", "branch-a"), ("origin",))


def commands(prompt: str) -> list[str]:
    result = resolve(prompt, CTX)
    if result is None:
        raise AssertionError(f"prompt did not resolve: {prompt}")
    return [candidate.command for candidate in result.candidates]


class ResolverTests(unittest.TestCase):
    def test_switch_to_main_branch(self):
        self.assertEqual(commands("switch to main branch"), ["git switch main"])

    def test_rebase_current_branch_defaults_to_main(self):
        self.assertEqual(commands("rebase current branch"), ["git rebase main"])

    def test_pull_from_main_remote_offers_safe_choices(self):
        self.assertEqual(commands("pull from main remote"), [
            "git pull --ff-only origin main",
            "git pull --rebase origin main",
        ])

    def test_diff_between_branches_offers_semantic_choices(self):
        self.assertEqual(commands("show me diff b/w branch-a and main"), [
            "git diff branch-a...main",
            "git diff branch-a main",
        ])

    def test_create_pull_request(self):
        self.assertEqual(commands("create a pull request"), [
            "gh pr create --fill",
            "gh pr create --web",
        ])

    def test_undo_commit_preserves_changes_and_rewrites_history(self):
        result = resolve("undo my last commit but keep all my changes", CTX)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([candidate.command for candidate in result.candidates], [
            "git reset --soft 'HEAD~1'",
            "git reset --mixed 'HEAD~1'",
        ])
        self.assertTrue(all(candidate.risk == Risk.HISTORY_REWRITE for candidate in result.candidates))

    def test_unknown_intent_returns_none(self):
        self.assertIsNone(resolve("make everything better", CTX))


if __name__ == "__main__":
    unittest.main()
