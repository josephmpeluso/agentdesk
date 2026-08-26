"""Plain-assert tests for jsonio.py. No pytest — run directly with python.

Covers the two failure modes documented in jsonio.py's module docstring
(truncation, preamble) plus the brace-in-string case that motivated the
depth-tracking parser instead of a naive find/rfind slice.
"""

from __future__ import annotations

import sys

from jsonio import ParseFailure, extract_json, find_json_block


class FakeBlock:
    def __init__(self, type_: str, text: str | None = None):
        self.type = type_
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason=None, usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = ""):
    results.append((name, condition, detail))
    status = "PASS" if condition else "FAIL"
    line = f"[{status}] {name}"
    if not condition and detail:
        line += f" — {detail}"
    print(line)


def test_prose_wrapped_json():
    text = 'Here is the verdict:\n{"score": 8, "pass": true}\nLet me know if you need anything else.'
    block = find_json_block(text)
    check("find_json_block: prose-wrapped JSON returns just the block",
          block == '{"score": 8, "pass": true}', repr(block))
    try:
        parsed = __import__("json").loads(block)
        check("find_json_block: prose-wrapped JSON parses cleanly",
              parsed == {"score": 8, "pass": True}, repr(parsed))
    except Exception as e:
        check("find_json_block: prose-wrapped JSON parses cleanly", False, str(e))


def test_brace_inside_string():
    text = '{"body": "swap in [COMPANY] and {q3}", "score": 7}'
    block = find_json_block(text)
    check("find_json_block: brace inside string value doesn't close early",
          block == text, repr(block))
    try:
        parsed = __import__("json").loads(block)
        check("find_json_block: brace-in-string JSON parses cleanly",
              parsed == {"body": "swap in [COMPANY] and {q3}", "score": 7}, repr(parsed))
    except Exception as e:
        check("find_json_block: brace-in-string JSON parses cleanly", False, str(e))


def test_unterminated_string_returns_none():
    text = '{"a": "unterminated'
    block = find_json_block(text)
    check("find_json_block: unterminated string returns None (truncation signal)",
          block is None, repr(block))


def test_extract_json_no_text_content_raises():
    resp = FakeResponse(content=[FakeBlock("tool_use")], stop_reason="end_turn")
    try:
        extract_json(resp)
        check("extract_json: no text content raises ParseFailure", False, "no exception raised")
    except ParseFailure as e:
        check("extract_json: no text content raises ParseFailure",
              "no text content" in e.reason, e.reason)
    except Exception as e:
        check("extract_json: no text content raises ParseFailure", False,
              f"wrong exception type: {type(e).__name__}: {e}")


def main() -> int:
    test_prose_wrapped_json()
    test_brace_inside_string()
    test_unterminated_string_returns_none()
    test_extract_json_no_text_content_raises()

    failed = [name for name, ok, _ in results if not ok]
    print("-" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
