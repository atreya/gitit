from __future__ import annotations

import os
import shutil
import sys
import textwrap
from dataclasses import dataclass
from typing import TextIO

from .model import Candidate, Resolution, Risk


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"

# Standard ANSI colors inherit the user's terminal palette. Commands deliberately
# use the terminal's default foreground so they remain legible on light and dark themes.
ACCENT = "\x1b[35m"              # theme-defined magenta
MUTED = DIM                       # dimmed default foreground
DOT = DIM                         # intentionally quiet status marker
SUCCESS = "\x1b[32m"             # theme-defined green
WARNING = "\x1b[33m"             # theme-defined yellow
DANGER = "\x1b[31m"              # theme-defined red


def supports_color(stream: TextIO) -> bool:
    return (
        "NO_COLOR" not in os.environ
        and os.environ.get("TERM") != "dumb"
        and hasattr(stream, "isatty")
        and stream.isatty()
    )


@dataclass
class TerminalUI:
    stream: TextIO = sys.stdout
    color: bool | None = None

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = supports_color(self.stream)

    def paint(self, value: str, *styles: str) -> str:
        if not self.color or not styles:
            return value
        return f"{''.join(styles)}{value}{RESET}"

    def line(self, value: str = "") -> None:
        print(value, file=self.stream)

    def mark(self, label: str, *, tone: str = DOT, detail: str | None = None) -> None:
        dot = self.paint("·", tone, BOLD)
        primary = self.paint(label, BOLD)
        suffix = f" {self.paint(detail, MUTED)}" if detail else ""
        self.line(f"{dot} {primary}{suffix}")

    def waiting(self, label: str = "Understanding your request…") -> None:
        if self.color:
            self.line(f"{self.paint('·', DOT, BOLD)} {self.paint(label, MUTED)}")

    def clear_previous_line(self) -> None:
        if self.color:
            self.stream.write("\x1b[1A\x1b[2K\r")
            self.stream.flush()

    def resolution(self, resolution: Resolution) -> None:
        timing = f"{resolution.elapsed_ms} ms" if resolution.elapsed_ms is not None else None
        self.line()
        self.mark("Command ready", detail=" · ".join(x for x in (resolution.source, timing) if x))
        if resolution.clarification:
            self.line(f"  {self.paint(resolution.clarification, MUTED)}")
        self.line()
        for index, candidate in enumerate(resolution.candidates, 1):
            label = f"option {index}" if len(resolution.candidates) > 1 else "command"
            self.command_box(candidate.command, label)
            self.line(f"     {self.paint(candidate.explanation, MUTED)}")
            risk_color = {
                Risk.READ_ONLY: SUCCESS,
                Risk.MUTATING: WARNING,
                Risk.HISTORY_REWRITE: WARNING,
                Risk.DESTRUCTIVE: DANGER,
            }[candidate.risk]
            self.line(
                f"     {self.paint('●', risk_color)} "
                f"{self.paint(candidate.risk.label, MUTED)}"
            )
            self.line()

    def command_box(self, command: str, label: str = "command") -> None:
        terminal_width = shutil.get_terminal_size(fallback=(88, 24)).columns
        box_width = min(max(44, len(command) + 6), max(24, terminal_width - 4), 100)
        inner_width = box_width - 4
        wrapped = textwrap.wrap(
            command,
            width=inner_width,
            break_long_words=False,
            break_on_hyphens=False,
        ) or [""]

        label_text = f" {label} "
        top_fill = "─" * max(1, box_width - len(label_text) - 3)
        self.line(
            f"  {self.paint('╭─', MUTED)}"
            f"{self.paint(label_text, ACCENT, BOLD)}"
            f"{self.paint(top_fill + '╮', MUTED)}"
        )
        for part in wrapped:
            padding = " " * max(0, inner_width - len(part))
            self.line(
                f"  {self.paint('│', MUTED)} "
                f"{self.paint(part, BOLD)}{padding} "
                f"{self.paint('│', MUTED)}"
            )
        self.line(f"  {self.paint('╰' + '─' * (box_width - 2) + '╯', MUTED)}")

    def prompt(self, label: str, hint: str | None = None) -> str:
        suffix = f" {self.paint(hint, MUTED)}" if hint else ""
        return input(f"{self.paint('›', ACCENT, BOLD)} {self.paint(label, BOLD)}{suffix} ")

    def error(self, message: str) -> None:
        self.mark("Error", tone=DANGER, detail=message)

    def cancelled(self) -> None:
        self.mark("Cancelled", tone=MUTED)

    def welcome(self) -> None:
        self.line()
        self.mark("gitit", detail="Natural language → Git")
        self.line(f"  {self.paint('Describe what you want to do. Type q to exit.', MUTED)}")
        self.line()
