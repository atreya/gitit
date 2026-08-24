from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from .context import RepositoryContext
from .model import Candidate, Resolution, Risk
from .policy import PolicyError, validate_resolution


DEFAULT_MODEL = "gpt-5.4-mini"
API_URL = "https://api.openai.com/v1/responses"


class ModelError(RuntimeError):
    """A useful, user-facing model resolution failure."""


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "minLength": 1, "maxLength": 80},
        "clarification": {"type": ["string", "null"], "maxLength": 240},
        "candidates": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "argv": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 40,
                        "items": {"type": "string", "minLength": 1, "maxLength": 500},
                    },
                    "explanation": {"type": "string", "minLength": 10, "maxLength": 240},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["argv", "explanation", "confidence"],
            },
        },
    },
    "required": ["intent", "clarification", "candidates"],
}


INSTRUCTIONS = """You are gitit's Git command resolver. Convert the user's desired outcome into one to three precise command candidates.

Rules:
- Return argv arrays, never shell command strings.
- Use only git or gh commands. Never use a shell, command chaining, scripts, or file contents.
- Prefer modern, explicit Git commands and the safest behavior consistent with the request.
- If materially different interpretations are plausible, return ranked alternatives and a one-sentence clarification explaining the choice.
- Never invent branches or remotes when repository context provides them. Ask via alternatives when ambiguous.
- The explanation must state the observable effect in one concise sentence.
- Do not include risk labels; gitit computes risk independently.
- For a pull request, use gh pr commands.
- Do not add commentary outside the required schema."""


def _context_payload(ctx: RepositoryContext) -> dict[str, object]:
    return {
        "is_repository": ctx.is_repository,
        "current_branch": ctx.current_branch,
        "local_branches": list(ctx.branches),
        "remotes": list(ctx.remotes),
        "upstream": ctx.upstream,
        "working_tree_status": list(ctx.status),
    }


def _extract_output_text(response: dict[str, object]) -> str:
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    return text
    raise ModelError("the model returned no structured command output")


def parse_model_output(text: str, model: str, elapsed_ms: int) -> Resolution:
    try:
        data = json.loads(text)
        candidates = tuple(
            Candidate(tuple(item["argv"]), item["explanation"], Risk.READ_ONLY, float(item["confidence"]))
            for item in data["candidates"]
        )
        resolution = Resolution(
            str(data["intent"]),
            candidates,
            data.get("clarification"),
            model,
            elapsed_ms,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ModelError("the model returned malformed structured output") from error
    try:
        return validate_resolution(resolution)
    except PolicyError as error:
        raise ModelError(f"gitit rejected the model response: {error}") from error


def resolve_with_openai(
    prompt: str,
    ctx: RepositoryContext,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 15.0,
) -> Resolution:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    model = model or os.environ.get("GITIT_MODEL", DEFAULT_MODEL)
    if not api_key:
        raise ModelError("OPENAI_API_KEY is not set. Add it to your environment or use --offline.")

    user_input = json.dumps(
        {"request": prompt, "repository": _context_payload(ctx)},
        separators=(",", ":"),
    )
    payload = {
        "model": model,
        "instructions": INSTRUCTIONS,
        "input": user_input,
        "reasoning": {"effort": "none"},
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "git_command_resolution",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            },
        },
        "max_output_tokens": 1200,
        "store": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            body = json.loads(error.read().decode("utf-8"))
            detail = body.get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        message = f"OpenAI API returned HTTP {error.code}"
        raise ModelError(f"{message}: {detail}" if detail else message) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ModelError(f"could not reach the OpenAI API: {error.reason if hasattr(error, 'reason') else error}") from error
    except json.JSONDecodeError as error:
        raise ModelError("the OpenAI API returned invalid JSON") from error
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return parse_model_output(_extract_output_text(body), model, elapsed_ms)
