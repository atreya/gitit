# gitit

`gitit` is a fast, model-first, confirmation-first natural-language interface for Git.

```console
$ gitit undo my last commit but keep my changes

  1. git reset --soft HEAD~1
     Removes the last commit while keeping its changes staged.

  2. git reset --mixed HEAD~1
     Removes the last commit while keeping its changes unstaged.
```

The first version uses a hosted LLM to interpret open-ended requests, shows the exact command and a one-line explanation, and requires confirmation before executing any state-changing operation. Deterministic code validates the model's structured output and controls execution.

## Try it

No Python package dependencies are required beyond Python 3.10+. Normal operation uses the OpenAI Responses API and defaults to `gpt-5.4-mini`.

```bash
python3 -m pip install -e .
export OPENAI_API_KEY="your-api-key"
gitit "show me diff b/w feature-a and main"
gitit
```

Interactive terminals get a color-aware interface with a status dot, highlighted commands, muted explanations, and risk colors. Styling automatically switches off for redirected output, `TERM=dumb`, or when the standard `NO_COLOR` environment variable is set.

Use `--no-execute` to resolve and display commands without offering to run them:

```bash
gitit --no-execute "rebase current branch onto main"
```

Override the model with `GITIT_MODEL` or `--model`. Use `--offline` only when no network or API key is available; it invokes the deliberately limited local fast path.

The model can interpret open-ended Git requests rather than a fixed catalog. Repository context includes only metadata: current branch, local branch names, remotes, upstream, and compact working-tree status. Source-file contents are not sent.

## Safety model

- Commands are represented as executable plus arguments and run without a shell.
- Model output must satisfy a strict JSON schema and a local command policy.
- Every candidate is visible and explained before execution.
- State-changing commands require confirmation.
- Higher-risk history rewrites are clearly labeled.
- Repository inspection is read-only.

See [abstract.md](abstract.md) for the product direction and Phase 2 local-model plan.
