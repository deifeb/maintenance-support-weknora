from collections.abc import Sequence

from alembic import op

revision: str = "20260724_04"
down_revision: str | None = "20260723_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "ai_sessions", "ai_model_calls", "ai_execution_plans", "ai_plan_steps",
    "ai_tool_calls", "ai_confirmation_requests", "ai_messages", "ai_session_snapshots",
    "ai_events", "ai_evidence_packages", "ai_evidence_items", "ai_review_runs",
    "ai_review_findings", "ai_report_jobs", "ai_report_versions", "ai_report_sections",
    "ai_report_citations", "ai_report_validation_findings", "ai_report_exports",
]


def upgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    bind = op.get_bind()
    for name in _TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    bind = op.get_bind()
    for name in reversed(_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
