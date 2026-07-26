from __future__ import annotations

from inspect import signature

from app.services.ai_confirmation_service import (
    AIConfirmationService,
)
from app.services.ai_context_service import (
    AIContextService,
)
from app.services.ai_event_service import (
    AIEventService,
)
from app.services.ai_evidence_service import (
    AIEvidenceService,
)
from app.services.ai_model_runtime import (
    AIModelRuntime,
)
from app.services.ai_session_service import (
    AISessionService,
)


def test_ai_service_public_methods_require_actor() -> None:
    matrix = (
        (
            AISessionService,
            (
                "create",
                "get",
                "add_message",
                "append_event",
                "create_snapshot",
            ),
        ),
        (
            AIConfirmationService,
            (
                "create",
                "approve",
                "reject",
            ),
        ),
        (
            AIContextService,
            ("build_context",),
        ),
        (
            AIEventService,
            ("append", "list"),
        ),
        (
            AIEvidenceService,
            ("retrieve_and_persist",),
        ),
        (
            AIModelRuntime,
            (
                "complete_structured",
                "complete_text",
            ),
        ),
    )

    for service_type, method_names in matrix:
        for method_name in method_names:
            parameters = signature(
                getattr(
                    service_type,
                    method_name,
                )
            ).parameters
            assert "actor" in parameters, (
                service_type.__name__,
                method_name,
                parameters,
            )


def test_identity_fields_are_not_public_inputs() -> None:
    session_create = signature(
        AISessionService.create
    ).parameters
    approve = signature(
        AIConfirmationService.approve
    ).parameters
    reject = signature(
        AIConfirmationService.reject
    ).parameters

    assert "created_by" not in session_create
    assert "resolved_by" not in approve
    assert "resolved_by" not in reject
