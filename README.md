# gitit

`gitit` is a fast, confirmation-first natural-language interface for Git.

```console
$ gitit undo my last commit but keep my changes

  1. git reset --soft HEAD~1
     Removes the last commit while keeping its changes staged.

  2. git reset --mixed HEAD~1
     Removes the last commit while keeping its changes unstaged.
```

The first version resolves common intents locally, shows the exact command and a one-line explanation, and requires confirmation before executing any state-changing operation.

## Try it

No runtime dependencies are required beyond Python 3.10+ and Git.

```bash
python3 -m pip install -e .
gitit "show me diff b/w feature-a and main"
gitit
```

Use `--no-execute` to resolve and display commands without offering to run them:

```bash
gitit --no-execute "rebase current branch onto main"
```

Currently supported intent families include branch switching, rebasing, pulling, branch-to-branch diffs, pull-request creation through `gh`, undoing the last commit while preserving changes, status, and recent history.

## Safety model

- Commands are represented as executable plus arguments and run without a shell.
- Every candidate is visible and explained before execution.
- State-changing commands require confirmation.
- Higher-risk history rewrites are clearly labeled.
- Repository inspection is read-only.

See [abstract.md](abstract.md) for the product direction and Phase 2 local-model plan.
