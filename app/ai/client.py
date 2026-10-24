"""Calls to Claude (live mode only).

- `diagnose` sends the brief prompt, plus the ticket photo if there is one, to
  claude-sonnet-5-5 and returns the validated brief.
- `match_fix` asks claude-haiku-5-5 whether a technician's free-text fix is the
  same as one of the known fix variants.

Token usage is logged for every call so we can watch the budget.
"""

import base64
import io
import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from app.ai.schema import BriefData
from app.config import settings

log = logging.getLogger("techmind.ai")

BRIEF_MODEL = "claude-sonnet-5-5"
MATCH_MODEL = "claude-haiku-5-5"


class AIError(RuntimeError):
    pass


def _client():
    import anthropic

    if not settings.anthropic_api_key:
        raise AIError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=90)


def _image_block(photo_path: str) -> dict | None:
    """Resize the photo to at most 1200px on its long side (fewer tokens, same detail) and encode it."""
    from PIL import Image

    path = Path(photo_path)
    if not path.exists():
        return None
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((1200, 1200))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buffer.getvalue()).decode()}}


def _json_from(text: str) -> dict:
    """Pull the JSON object out of a reply, tolerating code fences or stray words around it."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def diagnose(system: str, user: str, photo_path: str | None) -> tuple[BriefData, int, int]:
    """Returns (brief, input_tokens, output_tokens). Retries once if the reply isn't valid."""
    client = _client()
    content = []
    if photo_path:
        image = _image_block(photo_path)
        if image:
            content.append(image)
    content.append({"type": "text", "text": user})
    messages = [{"role": "user", "content": content}]
    tokens_in = tokens_out = 0
    for attempt in (1, 2):
        reply = client.messages.create(model=BRIEF_MODEL, max_tokens=4000, system=system, messages=messages)
        tokens_in += reply.usage.input_tokens
        tokens_out += reply.usage.output_tokens
        log.info("brief call %d: %d input tokens, %d output tokens", attempt, reply.usage.input_tokens,
                 reply.usage.output_tokens)
        text = "".join(block.text for block in reply.content if block.type == "text")
        try:
            return BriefData.model_validate(_json_from(text)), tokens_in, tokens_out
        except (ValueError, ValidationError) as error:
            log.warning("brief reply invalid (%s)", error)
            messages = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": f"That reply was not valid: {error}. "
                                                               "Reply again with only the corrected JSON object."}]
    raise AIError("Claude returned an invalid brief twice")


def match_fix(description: str, variants: list[list[str]]) -> int | None:
    """Index of the variant that matches the described fix, or None if it is a new fix."""
    client = _client()
    listing = "\n".join(f"{i}: {' | '.join(steps)}" for i, steps in enumerate(variants))
    reply = client.messages.create(
        model=MATCH_MODEL, max_tokens=10,
        messages=[{"role": "user", "content":
                   f"A technician described the fix they performed:\n\"{description}\"\n\n"
                   f"Known fixes:\n{listing}\n\nIf the technician's fix is essentially the same procedure as one "
                   "known fix, reply with its number only. If it is a different procedure, reply NEW."}])
    log.info("fix match call: %d input tokens, %d output tokens", reply.usage.input_tokens, reply.usage.output_tokens)
    answer = "".join(b.text for b in reply.content if b.type == "text").strip()
    return int(answer) if answer.isdigit() and int(answer) < len(variants) else None
