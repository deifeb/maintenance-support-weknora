from typing import Any

from pydantic import BaseModel, Field


class AIContextMessage(BaseModel):
    role: str
    message_type: str
    content: str
    sequence: int


class AIContextRead(BaseModel):
    system_constraints: tuple[str, ...] = (
        "不得生成最终器材数量",
        "不得补造可靠性参数",
        "不得调用未注册工具",
        "证据不足时必须明确说明",
    )
    user_goal: str | None = None
    session_summary: str = ""
    recent_messages: list[AIContextMessage] = Field(default_factory=list)
    scenario_draft: dict[str, Any] = Field(default_factory=dict)
    current_plan: dict[str, Any] | None = None
    completed_tool_summaries: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirmations: list[dict[str, Any]] = Field(default_factory=list)
    evidence_package_summaries: list[dict[str, Any]] = Field(default_factory=list)
