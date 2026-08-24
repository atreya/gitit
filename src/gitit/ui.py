from __future__ import annotations

import os
import select
import shutil
import sys
import termios
import textwrap
import tty
from dataclasses import dataclass
from typing import TextIO

from .model import Candidate, Resolution, Risk


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
REVERSE = "\x1b[7m"

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

    def command_box(self, command: str, label: str = "command") -> int:
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
        return len(wrapped) + 2

    def _resolution_header(self, resolution: Resolution) -> None:
        timing = f"{resolution.elapsed_ms} ms" if resolution.elapsed_ms is not None else None
        self.line()
        self.mark("Command ready", detail=" · ".join(x for x in (resolution.source, timing) if x))
        if resolution.clarification:
            self.line(f"  {self.paint(resolution.clarification, MUTED)}")
        self.line()

    def _choice_line(self, title: str, labels: list[str], selected: int) -> str:
        choices: list[str] = []
        for index, label in enumerate(labels):
            if index == selected:
                choices.append(self.paint(f" {label} ", REVERSE, BOLD))
            else:
                choices.append(self.paint(f" {label} ", DIM))
        choices_text = "  ".join(choices)
        hint_text = "←→ select · Enter · Esc"
        plain_width = 2 + len(title) + 2 + sum(len(label) + 2 for label in labels)
        plain_width += 2 * max(0, len(labels) - 1)
        terminal_width = shutil.get_terminal_size(fallback=(88, 24)).columns
        hint = f"   {self.paint(hint_text, MUTED)}" if plain_width + 3 + len(hint_text) <= terminal_width else ""
        return f"  {self.paint(title, BOLD)}  {choices_text}{hint}"

    def _candidate_list(self, resolution: Resolution) -> None:
        if len(resolution.candidates) == 1:
            candidate = resolution.candidates[0]
            self.command_box(candidate.command)
            self._candidate_detail(candidate)
            return

        terminal_width = shutil.get_terminal_size(fallback=(88, 24)).columns
        box_width = min(max(52, max(len(item.command) for item in resolution.candidates) + 8), max(28, terminal_width - 4), 100)
        inner_width = box_width - 4
        label_text = " choices "
        top_fill = "─" * max(1, box_width - len(label_text) - 3)
        self.line(
            f"  {self.paint('╭─', MUTED)}{self.paint(label_text, ACCENT, BOLD)}"
            f"{self.paint(top_fill + '╮', MUTED)}"
        )
        for index, candidate in enumerate(resolution.candidates, 1):
            prefix = f"{index} "
            parts = textwrap.wrap(
                candidate.command,
                width=max(12, inner_width - len(prefix)),
                break_long_words=False,
                break_on_hyphens=False,
            ) or [""]
            for part_index, part in enumerate(parts):
                row_prefix = prefix if part_index == 0 else " " * len(prefix)
                plain = f"{row_prefix}{part}"
                padding = " " * max(0, inner_width - len(plain))
                self.line(
                    f"  {self.paint('│', MUTED)} "
                    f"{self.paint(row_prefix, ACCENT, BOLD)}{self.paint(part, BOLD)}{padding} "
                    f"{self.paint('│', MUTED)}"
                )
        self.line(f"  {self.paint('╰' + '─' * (box_width - 2) + '╯', MUTED)}")
        for index, candidate in enumerate(resolution.candidates, 1):
            self.line(f"     {self.paint(str(index), ACCENT, BOLD)} {self.paint(candidate.explanation, MUTED)}")
        highest_risk = max(candidate.risk for candidate in resolution.candidates)
        risk_color = {
            Risk.READ_ONLY: SUCCESS,
            Risk.MUTATING: WARNING,
            Risk.HISTORY_REWRITE: WARNING,
            Risk.DESTRUCTIVE: DANGER,
        }[highest_risk]
        self.line(f"     {self.paint('·', MUTED)} {self.paint(highest_risk.label, risk_color)}")

    def _candidate_detail(self, candidate: Candidate) -> None:
        risk_color = {
            Risk.READ_ONLY: SUCCESS,
            Risk.MUTATING: WARNING,
            Risk.HISTORY_REWRITE: WARNING,
            Risk.DESTRUCTIVE: DANGER,
        }[candidate.risk]
        self.line(
            f"     {self.paint(candidate.explanation, MUTED)} "
            f"{self.paint('·', MUTED)} {self.paint(candidate.risk.label, risk_color)}"
        )

    def _write_choice(self, title: str, labels: list[str], selected: int, *, replace: bool = False) -> None:
        if replace:
            self.stream.write("\r\x1b[2K")
        self.stream.write(self._choice_line(title, labels, selected))
        self.stream.flush()

    def select_candidate(self, resolution: Resolution, key_reader=None) -> Candidate | None:
        self._resolution_header(resolution)
        read = key_reader or read_key
        labels_count = len(resolution.candidates) + 1
        selected = (
            0
            if all(candidate.risk == Risk.READ_ONLY for candidate in resolution.candidates)
            else len(resolution.candidates)
        )
        self._candidate_list(resolution)
        labels = (
            ["Run"]
            if len(resolution.candidates) == 1
            else [str(index) for index in range(1, len(resolution.candidates) + 1)]
        ) + ["Cancel"]
        self._write_choice("Action", labels, selected)
        while True:
            key = read()
            if key in {"left", "up"}:
                selected = (selected - 1) % labels_count
            elif key in {"right", "down", "tab"}:
                selected = (selected + 1) % labels_count
            elif key in {"escape", "q"}:
                self.line()
                return None
            elif key == "enter":
                self.line()
                return None if selected == len(resolution.candidates) else resolution.candidates[selected]
            elif key.isdigit() and 1 <= int(key) <= len(resolution.candidates):
                selected = int(key) - 1
            else:
                continue
            self._write_choice("Action", labels, selected, replace=True)

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


def read_key() -> str:
    """Read one terminal navigation key without requiring Enter."""
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        first = os.read(fd, 1)
        if first in {b"\r", b"\n"}:
            return "enter"
        if first == b"\t":
            return "tab"
        if first == b"\x1b":
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                return "escape"
            sequence = os.read(fd, 2)
            return {
                b"[A": "up",
                b"[B": "down",
                b"[C": "right",
                b"[D": "left",
            }.get(sequence, "escape")
        try:
            return first.decode("utf-8").lower()
        except UnicodeDecodeError:
            return "unknown"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
