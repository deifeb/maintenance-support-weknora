from maintenance_ai.enums import FieldSourceType
from maintenance_ai.scenarios.models import FieldValue

_PRIORITY = {
    FieldSourceType.USER_CONFIRMED: 0,
    FieldSourceType.USER_PROVIDED: 1,
    FieldSourceType.MASTER_DATA: 2,
    FieldSourceType.KNOWLEDGE_RETRIEVED: 3,
    FieldSourceType.SYSTEM_DEFAULT: 4,
    FieldSourceType.LLM_INFERRED: 5,
}


def merge_field_values(
    current: FieldValue | None, incoming: FieldValue | None
) -> FieldValue | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    current_key = (_PRIORITY[current.source_type], -current.confidence)
    incoming_key = (_PRIORITY[incoming.source_type], -incoming.confidence)
    return incoming if incoming_key < current_key else current
