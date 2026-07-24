from maintenance_ai import (
    AI_CORE_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    PROMPT_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    __version__,
)


def test_public_versions_are_stable():
    assert (__version__, AI_CORE_VERSION) == ("0.1.0", "0.1.0")
    assert {
        PROMPT_SCHEMA_VERSION,
        PLAN_SCHEMA_VERSION,
        EVIDENCE_SCHEMA_VERSION,
        REPORT_SCHEMA_VERSION,
    } == {"1.0"}
