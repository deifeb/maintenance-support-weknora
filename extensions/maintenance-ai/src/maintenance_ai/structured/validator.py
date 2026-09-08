from typing import TypeVar

from pydantic import BaseModel, ValidationError

from maintenance_ai.exceptions import StructuredOutputError
from maintenance_ai.structured.extraction import extract_json_object

T = TypeVar("T", bound=BaseModel)


def validate_structured_output(raw: str | dict, response_model: type[T]) -> T:
    value = extract_json_object(raw)
    allowed = set(response_model.model_fields)
    value = {key: item for key, item in value.items() if key in allowed}
    try:
        return response_model.model_validate(value)
    except ValidationError as exc:
        raise StructuredOutputError(str(exc)) from exc
