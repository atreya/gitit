from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from .context import RepositoryContext, inspect_repository
from .model import Candidate, Resolution, Risk
from .openai_resolver import DEFAULT_MODEL, ModelError, resolve_with_openai
from .resolver import resolve as resolve_offline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gitit", description="Turn natural language into reviewable Git commands.")
    parser.add_argument("prompt", nargs="*", help="what you want Git to do")
    parser.add_argument("--no-execute", action="store_true", help="show suggestions without offering to run them")
    parser.add_argument("--offline", action="store_true", help="use the limited local resolver instead of an LLM")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: GITIT_MODEL or {DEFAULT_MODEL})")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="repository to inspect and operate on")
    return parser


def _show(resolution: Resolution) -> None:
    timing = f" in {resolution.elapsed_ms} ms" if resolution.elapsed_ms is not None else ""
    print(f"\n  Resolved by {resolution.source}{timing}")
    if resolution.clarification:
        print(f"\n  {resolution.clarification}\n")
    for index, candidate in enumerate(resolution.candidates, 1):
        prefix = f"{index}." if len(resolution.candidates) > 1 else " "
        print(f"  {prefix} {candidate.command}")
        print(f"     {candidate.explanation}")
        print(f"     Risk: {candidate.risk.label}\n")


def _choose(resolution: Resolution) -> Candidate | None:
    if len(resolution.candidates) == 1:
        return resolution.candidates[0]
    while True:
        answer = input(f"Choose [1-{len(resolution.candidates)}] or [q] cancel: ").strip().lower()
        if answer in {"q", "quit", "cancel", ""}:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(resolution.candidates):
            return resolution.candidates[int(answer) - 1]
        print("Please choose one of the numbered suggestions.")


def _execute(candidate: Candidate, ctx: RepositoryContext, cwd: Path) -> int:
    if shutil.which(candidate.argv[0]) is None:
        print(f"gitit: '{candidate.argv[0]}' is not installed or not on PATH.", file=sys.stderr)
        return 127
    workdir = ctx.root or cwd.resolve()
    result = subprocess.run(candidate.argv, cwd=workdir, check=False)
    return result.returncode


def _handle(prompt: str, cwd: Path, no_execute: bool, offline: bool, model: str | None) -> int:
    ctx = inspect_repository(cwd)
    try:
        resolution = resolve_offline(prompt, ctx) if offline else resolve_with_openai(prompt, ctx, model=model)
    except ModelError as error:
        print(f"gitit: {error}", file=sys.stderr)
        return 2
    if resolution is None:
        print("gitit couldn't resolve that with the limited offline resolver.", file=sys.stderr)
        return 2
    _show(resolution)
    if no_execute or not sys.stdin.isatty():
        return 0
    candidate = _choose(resolution)
    if candidate is None:
        print("Cancelled.")
        return 0
    verb = "Run" if candidate.risk == Risk.READ_ONLY else "Confirm and run"
    answer = input(f"{verb} `{candidate.command}`? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Cancelled.")
        return 0
    return _execute(candidate, ctx, cwd)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.prompt:
        return _handle(" ".join(args.prompt), args.cwd, args.no_execute, args.offline, args.model)
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        return _handle(prompt, args.cwd, True, args.offline, args.model) if prompt else 2

    print("gitit interactive mode - describe what you want Git to do; 'q' exits.")
    while True:
        try:
            prompt = input("gitit> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt.lower() in {"q", "quit", "exit"}:
            return 0
        if prompt:
            _handle(prompt, args.cwd, args.no_execute, args.offline, args.model)
