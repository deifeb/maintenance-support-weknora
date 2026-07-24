from pathlib import Path
from typing import Any

import yaml
from jinja2 import StrictUndefined, Template

from maintenance_ai.prompts.models import PromptTemplate


class PromptRegistry:
    def __init__(self, prompts: dict[str, PromptTemplate]):
        self.prompts = prompts

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PromptRegistry":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        rows = data.get("prompts", data)
        return cls({name: PromptTemplate(name=name, **value) for name, value in rows.items()})

    def render(self, name: str, context: dict[str, Any]) -> tuple[str, str, str]:
        prompt = self.prompts[name]
        user = Template(prompt.user_template, undefined=StrictUndefined).render(**context)
        return prompt.system, user, prompt.version
