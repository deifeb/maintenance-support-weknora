from pydantic import BaseModel, ConfigDict


class PromptTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    system: str
    user_template: str
