from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    READ_ONLY = 0
    MUTATING = 1
    HISTORY_REWRITE = 2

    @property
    def label(self) -> str:
        return {
            self.READ_ONLY: "read-only",
            self.MUTATING: "changes repository state",
            self.HISTORY_REWRITE: "rewrites local history",
        }[self]


@dataclass(frozen=True)
class Candidate:
    argv: tuple[str, ...]
    explanation: str
    risk: Risk
    confidence: float = 1.0

    @property
    def command(self) -> str:
        import shlex

        return shlex.join(self.argv)


@dataclass(frozen=True)
class Resolution:
    intent: str
    candidates: tuple[Candidate, ...]
    clarification: str | None = None
