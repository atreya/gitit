from __future__ import annotations

import re

from .context import RepositoryContext
from .model import Candidate, Resolution, Risk


FILLER = {"the", "branch", "named", "called", "please", "for", "me"}


def _clean_entity(value: str) -> str:
    words = [word.strip(" ,.!?\t") for word in value.split()]
    return " ".join(word for word in words if word.lower() not in FILLER).strip()


def _default_main(ctx: RepositoryContext) -> str:
    for name in ("main", "master", "trunk"):
        if name in ctx.branches:
            return name
    return "main"


def _switch(text: str) -> Resolution | None:
    match = re.search(r"(?:switch|checkout|go)(?:\s+to)?\s+(.+?)(?:\s+branch)?$", text)
    if not match:
        return None
    branch = _clean_entity(match.group(1))
    if not branch:
        return None
    return Resolution("switch_branch", (Candidate(("git", "switch", branch), f"Switches your working tree to the local branch '{branch}'.", Risk.MUTATING),))


def _rebase(text: str, ctx: RepositoryContext) -> Resolution | None:
    if "rebase" not in text:
        return None
    match = re.search(r"rebase(?:\s+(?:the\s+)?current\s+branch)?(?:\s+onto|\s+on)?\s+(.+)$", text)
    target = _clean_entity(match.group(1)) if match else ""
    if target in {"current", "current onto", "current on"}:
        target = ""
    target = target or _default_main(ctx)
    return Resolution("rebase", (Candidate(("git", "rebase", target), f"Replays the current branch's commits on top of '{target}'.", Risk.HISTORY_REWRITE),))


def _pull(text: str, ctx: RepositoryContext) -> Resolution | None:
    if not re.search(r"\bpull\b", text):
        return None
    remotes = set(ctx.remotes)
    words = re.findall(r"[\w./-]+", text)
    named_remote = next((word for word in words if word in remotes), None)
    remote = named_remote or ("origin" if "origin" in remotes or not remotes else ctx.remotes[0])
    match = re.search(r"pull(?:\s+from)?\s+([\w./-]+)", text)
    branch = match.group(1) if match and match.group(1) not in {"the", "remote", remote} else _default_main(ctx)
    if "main remote" in text:
        branch = _default_main(ctx)
    return Resolution("pull", (
        Candidate(("git", "pull", "--ff-only", remote, branch), f"Fetches '{branch}' from '{remote}' and fast-forwards your current branch only if no merge is needed.", Risk.MUTATING),
        Candidate(("git", "pull", "--rebase", remote, branch), f"Fetches '{branch}' from '{remote}', then rebases your local commits on top of it.", Risk.HISTORY_REWRITE),
    ), "Choose whether pulling should allow only a fast-forward or rebase local commits.")


def _diff(text: str) -> Resolution | None:
    if not re.search(r"\bdiff\b|difference", text):
        return None
    normalized = re.sub(r"\bb/?w\b", "between", text)
    match = re.search(r"between\s+(?:branch\s+)?([\w./-]+)\s+and\s+(?:branch\s+)?([\w./-]+)", normalized)
    if not match:
        match = re.search(r"diff\s+(?:branch\s+)?([\w./-]+)\s+(?:and|to|vs\.?|versus)\s+(?:branch\s+)?([\w./-]+)", normalized)
    if not match:
        return None
    left, right = match.groups()
    return Resolution("compare_branches", (
        Candidate(("git", "diff", f"{left}...{right}"), f"Shows changes introduced on '{right}' since it diverged from '{left}'.", Risk.READ_ONLY),
        Candidate(("git", "diff", left, right), f"Shows the direct snapshot difference between '{left}' and '{right}'.", Risk.READ_ONLY),
    ), "Choose a merge-base comparison or a direct snapshot comparison.")


def _pull_request(text: str) -> Resolution | None:
    if not ("pull request" in text or re.search(r"\bpr\b", text)):
        return None
    return Resolution("create_pull_request", (
        Candidate(("gh", "pr", "create", "--fill"), "Creates a pull request for the current branch using commit information for its title and body.", Risk.MUTATING),
        Candidate(("gh", "pr", "create", "--web"), "Opens the browser to create and review the pull request on GitHub.", Risk.MUTATING),
    ), "Choose a terminal-generated draft or review the pull request in your browser.")


def _undo_last_commit(text: str) -> Resolution | None:
    if not (re.search(r"\b(undo|remove|uncommit)\b", text) and re.search(r"last\s+commit", text)):
        return None
    if not re.search(r"keep|preserve|save", text):
        return None
    return Resolution("undo_last_commit_keep_changes", (
        Candidate(("git", "reset", "--soft", "HEAD~1"), "Removes the last commit while keeping all of its changes staged.", Risk.HISTORY_REWRITE),
        Candidate(("git", "reset", "--mixed", "HEAD~1"), "Removes the last commit while keeping all of its changes unstaged.", Risk.HISTORY_REWRITE),
    ), "Choose whether the preserved changes should remain staged.")


def resolve(prompt: str, ctx: RepositoryContext) -> Resolution | None:
    text = " ".join(prompt.lower().split())
    if not text:
        return None

    for handler in (_undo_last_commit, _pull_request, _diff):
        result = handler(text)
        if result:
            return result
    for handler in (_rebase, _pull):
        result = handler(text, ctx)
        if result:
            return result
    switched = _switch(text)
    if switched:
        return switched
    if re.search(r"\b(status|what changed|changes)\b", text):
        return Resolution("status", (Candidate(("git", "status", "--short", "--branch"), "Shows the current branch and a compact summary of working-tree changes.", Risk.READ_ONLY),))
    if re.search(r"\b(log|history|recent commits?)\b", text):
        return Resolution("history", (Candidate(("git", "log", "--oneline", "--decorate", "-10"), "Shows the ten most recent commits in a compact form.", Risk.READ_ONLY),))
    return None
