from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from maintenance_ai.routing import ModelRegistry
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.services.ai_report_service import REPORT_SECTION_DEFINITIONS
from app.services.ai_tool_registry import ai_tool_registry


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return value


def seed_ai_configuration(
    session: Session | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    del session
    settings = settings or get_settings()
    paths = {
        "models": Path(settings.ai_models_config_path),
        "routes": Path(settings.ai_routes_config_path),
        "tools": Path(settings.ai_tools_config_path),
        "prompts": Path(settings.ai_prompts_config_path),
        "review_rules": Path(settings.ai_review_rules_path),
        "report_templates": Path(settings.ai_report_templates_path),
    }
    loaded = {name: _load(path) for name, path in paths.items()}
    registry = ModelRegistry.from_dicts(loaded["models"], loaded["routes"])

    for route_name, route in registry.routes.items():
        candidates = (route.primary, *route.fallbacks)
        unknown = [
            name for name in candidates if name != "RULE_FALLBACK" and name not in registry.models
        ]
        if unknown:
            raise ValueError(f"route {route_name} references unknown models: {unknown}")

    configured_tools = set(loaded["tools"].get("tools", {}))
    registered_tools = {row.name for row in ai_tool_registry.list_definitions()}
    if configured_tools != registered_tools:
        raise ValueError(
            "configured tools do not match registry: "
            f"missing={sorted(registered_tools - configured_tools)}, "
            f"unknown={sorted(configured_tools - registered_tools)}"
        )

    prompt_functions = {
        row.get("function")
        for row in loaded["prompts"].get("prompts", {}).values()
        if isinstance(row, dict)
    }
    if set(registry.routes) - prompt_functions:
        raise ValueError(
            f"routes without prompt definitions: {sorted(set(registry.routes) - prompt_functions)}"
        )

    allowed_sections = {code for code, _ in REPORT_SECTION_DEFINITIONS}
    templates = loaded["report_templates"].get("templates", {})
    for name, template in templates.items():
        section_codes = {row["code"] for row in template.get("sections", [])}
        if section_codes != allowed_sections:
            raise ValueError(f"report template {name} has invalid section set")

    normalized = json.dumps(
        loaded,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {
        "models": len(registry.models),
        "routes": len(registry.routes),
        "tools": len(configured_tools),
        "prompts": len(loaded["prompts"].get("prompts", {})),
        "review_rules": len(loaded["review_rules"].get("rules", {})),
        "report_templates": len(templates),
        "digest": digest,
    }


def main() -> None:
    print(seed_ai_configuration())


if __name__ == "__main__":
    main()
