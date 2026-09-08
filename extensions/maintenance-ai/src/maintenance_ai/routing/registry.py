from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from maintenance_ai.routing.models import ModelDefinition, RouteDefinition


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ModelRegistry(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    models: dict[str, ModelDefinition]
    routes: dict[str, RouteDefinition]

    @classmethod
    def from_dicts(
        cls,
        models_data: dict[str, Any],
        routes_data: dict[str, Any],
    ) -> "ModelRegistry":
        models: dict[str, ModelDefinition] = {}
        for name, raw_definition in models_data.get("models", models_data).items():
            definition = dict(raw_definition)
            model_env = definition.get("model_env")
            base_url_env = definition.get("base_url_env")
            enabled_env = definition.get("enabled_env")
            if model_env:
                definition["model"] = os.getenv(model_env, definition.get("model", ""))
            if base_url_env:
                definition["base_url"] = os.getenv(
                    base_url_env,
                    definition.get("base_url"),
                )
            if enabled_env:
                definition["enabled"] = _env_bool(
                    enabled_env,
                    bool(definition.get("enabled", False)),
                )
            models[name] = ModelDefinition(name=name, **definition)
        routes = {
            name: RouteDefinition(**definition)
            for name, definition in routes_data.get("routes", routes_data).items()
        }
        return cls(models=models, routes=routes)

    @classmethod
    def from_yaml(
        cls,
        models_path: str | Path,
        routes_path: str | Path,
    ) -> "ModelRegistry":
        models_data = yaml.safe_load(Path(models_path).read_text(encoding="utf-8")) or {}
        routes_data = yaml.safe_load(Path(routes_path).read_text(encoding="utf-8")) or {}
        return cls.from_dicts(models_data, routes_data)
