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
from .ui import TerminalUI


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gitit", description="Turn natural language into reviewable Git commands.")
    parser.add_argument("prompt", nargs="*", help="what you want Git to do")
    parser.add_argument("--no-execute", action="store_true", help="show suggestions without offering to run them")
    parser.add_argument("--offline", action="store_true", help="use the limited local resolver instead of an LLM")
    parser.add_argument("--model", default=None, help=f"OpenAI model (default: GITIT_MODEL or {DEFAULT_MODEL})")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="repository to inspect and operate on")
    return parser


def _execute(candidate: Candidate, ctx: RepositoryContext, cwd: Path) -> int:
    if shutil.which(candidate.argv[0]) is None:
        print(f"gitit: '{candidate.argv[0]}' is not installed or not on PATH.", file=sys.stderr)
        return 127
    workdir = ctx.root or cwd.resolve()
    result = subprocess.run(candidate.argv, cwd=workdir, check=False)
    return result.returncode


def _handle(prompt: str, cwd: Path, no_execute: bool, offline: bool, model: str | None) -> int:
    ui = TerminalUI()
    ctx = inspect_repository(cwd)
    ui.waiting()
    try:
        resolution = resolve_offline(prompt, ctx) if offline else resolve_with_openai(prompt, ctx, model=model)
    except ModelError as error:
        ui.clear_previous_line()
        TerminalUI(sys.stderr).error(str(error))
        return 2
    ui.clear_previous_line()
    if resolution is None:
        TerminalUI(sys.stderr).error("The limited offline resolver could not understand that request.")
        return 2
    if no_execute or not sys.stdin.isatty():
        ui.resolution(resolution)
        return 0
    candidate = ui.select_candidate(resolution)
    if candidate is None:
        ui.cancelled()
        return 0
    return _execute(candidate, ctx, cwd)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.prompt:
        return _handle(" ".join(args.prompt), args.cwd, args.no_execute, args.offline, args.model)
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        return _handle(prompt, args.cwd, True, args.offline, args.model) if prompt else 2

    ui = TerminalUI()
    ui.welcome()
    while True:
        try:
            prompt = ui.prompt("gitit").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt.lower() in {"q", "quit", "exit"}:
            return 0
        if prompt:
            _handle(prompt, args.cwd, args.no_execute, args.offline, args.model)
