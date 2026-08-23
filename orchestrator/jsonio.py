"""Robust JSON extraction from model replies.

Two failure modes killed the first live eval run, and both are the kind that
only appear once you leave fixtures behind:

1. **Truncation.** `max_tokens` was set below what a full `qa_verdict`
   needs — the verdict reproduces the whole email in `swap_test.redacted_body`
   and carries a location plus remediation per flag. The reply got cut
   mid-string and json.loads reported "Unterminated string", which reads like
   a model problem and is actually a budget problem.

2. **Preamble.** Naive fence-stripping only handles ``` at the exact start and
   end of the reply. One line of "Here is the verdict:" in front and parsing
   fails at character 0 with "Expecting value: line 1 column 1".

`extract_json` handles both, and `ParseFailure` carries enough context that
the next failure is diagnosable without another API call.
"""

from __future__ import annotations

import json
from typing import Any


class ParseFailure(Exception):
    """Raised when a model reply cannot be parsed. Carries the evidence."""

    def __init__(self, reason: str, raw: str, stop_reason: str | None = None,
                 usage: Any = None):
        self.reason = reason
        self.raw = raw
        self.stop_reason = stop_reason
        self.usage = usage
        super().__init__(self.summary())

    def summary(self) -> str:
        bits = [self.reason]
        if self.stop_reason:
            bits.append(f"stop_reason={self.stop_reason}")
            if self.stop_reason == "max_tokens":
                bits.append("REPLY WAS TRUNCATED — raise max_tokens")
        if self.usage is not None:
            bits.append(f"output_tokens={getattr(self.usage, 'output_tokens', '?')}")
        bits.append(f"reply_len={len(self.raw)}")
        return " | ".join(bits)

    def detail(self) -> str:
        """Full diagnostic including the head and tail of the raw reply."""
        head = self.raw[:400]
        tail = self.raw[-400:] if len(self.raw) > 800 else ""
        out = [self.summary(), "", "--- reply starts ---", head]
        if tail:
            out += ["", "   [...middle omitted...]", "", "--- reply ends ---", tail]
        return "\n".join(out)


def find_json_block(text: str) -> str | None:
    """Return the first balanced {...} block, ignoring braces inside strings.

    A plain `text[text.find('{'):text.rfind('}')+1]` breaks the moment a
    string value contains a brace, and email bodies contain `[COMPANY]`-style
    placeholders that make that likely.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(text[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None  # unbalanced — almost always truncation


def response_text(resp: Any) -> str:
    """Concatenate text blocks from an Anthropic response, skipping others."""
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def extract_json(resp: Any) -> dict:
    """Parse a JSON object out of an Anthropic response, or raise ParseFailure."""
    raw = response_text(resp)
    stop = getattr(resp, "stop_reason", None)
    usage = getattr(resp, "usage", None)

    if not raw:
        raise ParseFailure("model returned no text content", raw, stop, usage)

    # Fast path: the reply is already clean JSON.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    block = find_json_block(raw)
    if block is None:
        raise ParseFailure("no balanced JSON object found in reply", raw, stop, usage)

    try:
        return json.loads(block)
    except json.JSONDecodeError as e:
        raise ParseFailure(f"JSON block found but invalid: {e}", raw, stop, usage) from e
