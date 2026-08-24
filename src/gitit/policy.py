from __future__ import annotations

from .model import Candidate, Resolution, Risk


class PolicyError(ValueError):
    """Raised when a model-generated command crosses gitit's execution boundary."""


ALLOWED_GIT_COMMANDS = {
    "add", "am", "apply", "bisect", "blame", "branch", "checkout", "cherry-pick",
    "clean", "clone", "commit", "describe", "diff", "difftool", "fetch", "format-patch", "grep",
    "init", "log", "merge", "merge-base", "mv", "pull", "push", "rebase", "reflog",
    "remote", "reset", "restore", "revert", "rm", "show", "show-branch", "stash",
    "status", "submodule", "switch", "tag", "worktree",
}
READ_ONLY_GIT_COMMANDS = {
    "blame", "describe", "diff", "difftool", "grep", "log", "merge-base", "reflog", "show",
    "show-branch", "status",
}


def _risk(argv: tuple[str, ...]) -> Risk:
    executable, *args = argv
    if executable == "gh":
        if len(args) >= 2 and args[:2] == ["pr", "view"]:
            return Risk.READ_ONLY
        return Risk.MUTATING

    subcommand = args[0]
    flags = set(args[1:])
    if subcommand in READ_ONLY_GIT_COMMANDS:
        return Risk.READ_ONLY
    if subcommand == "branch" and not ({"-d", "-D", "-m", "-M"} & flags):
        return Risk.READ_ONLY
    if subcommand == "remote" and (len(args) == 1 or args[1] in {"-v", "show", "get-url"}):
        return Risk.READ_ONLY
    if subcommand == "tag" and len(args) == 1:
        return Risk.READ_ONLY
    if subcommand == "clean" or "--hard" in flags or "-D" in flags:
        return Risk.DESTRUCTIVE
    if subcommand == "push" and any(flag in flags for flag in {"--force", "-f", "--force-with-lease"}):
        return Risk.DESTRUCTIVE
    if subcommand == "restore" and "--staged" not in flags:
        return Risk.DESTRUCTIVE
    if subcommand in {"rebase", "reset"} or (subcommand == "commit" and "--amend" in flags):
        return Risk.HISTORY_REWRITE
    return Risk.MUTATING


def validate_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    if not 2 <= len(argv) <= 40:
        raise PolicyError("command must contain an executable, subcommand, and no more than 40 arguments")
    if argv[0] not in {"git", "gh"}:
        raise PolicyError("only git and GitHub CLI commands are supported")
    if any(not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg or "\r" in arg for arg in argv):
        raise PolicyError("command contains an invalid argument")
    if argv[0] == "git":
        if argv[1].startswith("-") or argv[1] not in ALLOWED_GIT_COMMANDS:
            raise PolicyError(f"unsupported Git subcommand: {argv[1]}")
    elif argv[1] != "pr":
        raise PolicyError("only GitHub pull-request operations are currently supported")
    return argv


def validate_resolution(resolution: Resolution) -> Resolution:
    if not 1 <= len(resolution.candidates) <= 3:
        raise PolicyError("the model must return between one and three candidates")
    clean: list[Candidate] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in resolution.candidates:
        argv = validate_argv(candidate.argv)
        if argv in seen:
            continue
        seen.add(argv)
        explanation = " ".join(candidate.explanation.split())
        if not 10 <= len(explanation) <= 240:
            raise PolicyError("candidate explanation must be a concise sentence")
        clean.append(Candidate(argv, explanation, _risk(argv), candidate.confidence))
    if not clean:
        raise PolicyError("the model returned no distinct candidates")
    return Resolution(
        resolution.intent,
        tuple(clean),
        resolution.clarification,
        resolution.source,
        resolution.elapsed_ms,
    )
