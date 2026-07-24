from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from maintenance_ai.enums import ModelCapability, ProviderKind, SensitivityLevel


class ModelDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)
    name: str
    provider: ProviderKind
    model: str = ""
    model_env: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    api_key_env: str | None = None
    enabled_env: str | None = None
    capabilities: set[ModelCapability] = Field(default_factory=set)
    sensitivity_allowed: set[SensitivityLevel] = Field(
        default_factory=set,
        validation_alias=AliasChoices("sensitivity_allowed", "allowed_sensitivity"),
    )
    context_window: int = Field(default=32768, ge=1)
    enabled: bool = True
    options: dict = Field(default_factory=dict)


class RouteDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    primary: str
    fallbacks: tuple[str, ...] = ()
    required_capabilities: set[ModelCapability] = Field(default_factory=set)


class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    function_name: str
    selected: str
    candidates: tuple[str, ...]
    filtered: tuple[str, ...]
    reason: str
