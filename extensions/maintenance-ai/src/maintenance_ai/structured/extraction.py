import json
from typing import Any

from maintenance_ai.exceptions import StructuredOutputError


def extract_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise StructuredOutputError("no JSON object found")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StructuredOutputError("structured response must be an object")
    return value
