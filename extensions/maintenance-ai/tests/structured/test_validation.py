import pytest
from pydantic import BaseModel

from maintenance_ai.structured import extract_json_object, validate_structured_output


class Shape(BaseModel):
    enabled: bool
    count: int


def test_deterministic_repairs_only_syntax_and_types():
    raw = '```json\n{"enabled":"true","count":"2","extra":1}\n```'
    assert extract_json_object(raw)["count"] == "2"
    result = validate_structured_output(raw, Shape)
    assert result.model_dump() == {"enabled": True, "count": 2}


def test_missing_business_field_is_not_invented():
    with pytest.raises(Exception):
        validate_structured_output('{"enabled":true}', Shape)
