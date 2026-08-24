from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepositoryContext:
    root: Path | None
    current_branch: str | None
    branches: tuple[str, ...]
    remotes: tuple[str, ...]
    upstream: str | None = None
    status: tuple[str, ...] = ()

    @property
    def is_repository(self) -> bool:
        return self.root is not None


def _git(*args: str, cwd: Path) -> str | None:
    result = subprocess.run(
        ("git", *args), cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def inspect_repository(cwd: Path | None = None) -> RepositoryContext:
    cwd = (cwd or Path.cwd()).resolve()
    root_text = _git("rev-parse", "--show-toplevel", cwd=cwd)
    if not root_text:
        return RepositoryContext(None, None, (), ())

    root = Path(root_text)
    current = _git("branch", "--show-current", cwd=root) or None
    branch_text = _git("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=root)
    remote_text = _git("remote", cwd=root)
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=root)
    status_text = _git("status", "--short", cwd=root)
    branches = tuple(line for line in (branch_text or "").splitlines() if line)
    remotes = tuple(line for line in (remote_text or "").splitlines() if line)
    status = tuple(line for line in (status_text or "").splitlines() if line)[:50]
    return RepositoryContext(root, current, branches, remotes, upstream, status)
