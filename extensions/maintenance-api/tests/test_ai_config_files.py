from pathlib import Path

import yaml
from app.core.config import get_settings
from app.services.ai_tool_registry import ai_tool_registry
from maintenance_ai.routing import ModelRegistry


def test_ai_configuration_files_load_and_cross_references_are_valid() -> None:
    settings = get_settings()
    paths = [
        settings.ai_models_config_path,
        settings.ai_routes_config_path,
        settings.ai_tools_config_path,
        settings.ai_prompts_config_path,
        settings.ai_review_rules_path,
        settings.ai_report_templates_path,
    ]
    assert all(Path(path).exists() for path in paths)

    registry = ModelRegistry.from_yaml(
        settings.ai_models_config_path,
        settings.ai_routes_config_path,
    )
    assert len(registry.models) == 2
    assert len(registry.routes) == 4
    assert all(route.primary in registry.models for route in registry.routes.values())

    tools = yaml.safe_load(Path(settings.ai_tools_config_path).read_text(encoding="utf-8"))
    configured_names = set(tools["tools"])
    registered_names = {row.name for row in ai_tool_registry.list_definitions()}
    assert configured_names == registered_names

    prompts = yaml.safe_load(Path(settings.ai_prompts_config_path).read_text(encoding="utf-8"))
    assert {"scenario-parser", "tool-planner", "review-explainer", "report-section"} <= set(
        prompts["prompts"]
    )

    templates = yaml.safe_load(Path(settings.ai_report_templates_path).read_text(encoding="utf-8"))
    assert len(templates["templates"]) == 3
    assert all(len(row["sections"]) == 17 for row in templates["templates"].values())
