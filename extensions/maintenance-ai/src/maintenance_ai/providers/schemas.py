from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from maintenance_ai.enums import (
    ExecutionMode,
    ProviderHealthStatus,
    ProviderKind,
    SensitivityLevel,
    StreamEventType,
)


class TextMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)


class TextCompletionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    messages: tuple[TextMessage, ...] = Field(min_length=1)
    function_name: str
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=2048, ge=1, le=32768)
    prompt_name: str
    prompt_version: str
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class StructuredCompletionRequest(TextCompletionRequest):
    schema_version: str


class CompletionUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class CompletionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: ProviderKind
    model: str
    request_id: str
    finish_reason: str | None = None
    latency_ms: int = Field(ge=0)
    retry_count: int = Field(default=0, ge=0)
    structured_validation_attempts: int = Field(default=0, ge=0)
    fallback_used: bool = False
    raw_response_digest: str
    usage: CompletionUsage = Field(default_factory=CompletionUsage)


class TextCompletionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str
    metadata: CompletionMetadata
    execution_mode: ExecutionMode = ExecutionMode.LLM
    llm_generated: bool = True
    fallback_reason: str | None = None


class StructuredCompletionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    data: Mapping[str, Any]
    metadata: CompletionMetadata
    execution_mode: ExecutionMode = ExecutionMode.LLM
    llm_generated: bool = True
    fallback_reason: str | None = None


class StreamEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_type: StreamEventType
    text: str = ""
    sequence: int = Field(ge=1)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: ProviderKind
    model: str
    status: ProviderHealthStatus
    detail: str
    latency_ms: int | None = Field(default=None, ge=0)
