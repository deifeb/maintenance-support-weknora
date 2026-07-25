# Maintenance Unit 05 Internal JWT Implementation Plan Review

**Reviewed plan:** `docs/superpowers/plans/2026-07-25-maintenance-unit05-internal-jwt-implementation.md`

**Reviewed head:** `047a84fdc263f024fa0a502ef098862189b677ba`

**Status:** Approved after the normative corrections below. These corrections are part of the implementation plan and take precedence where the main plan is incomplete.

## 1. Review Method

The plan was checked against the approved Unit 5 design for:

- complete requirement coverage;
- real RED/GREEN task boundaries;
- placeholder or vague-step absence;
- type and function-name consistency;
- secret exposure;
- PyJWT algorithm and time-check behavior;
- FastAPI dependency override behavior;
- scope isolation from existing routers and business code.

The initial draft was corrected because Task 3 implemented Task 4 strictness too early and because the first defensive-copy test did not actually pass a mutable mapping. The corrected main plan now preserves a real minimal-verifier RED/GREEN boundary and a meaningful exception-header test.

## 2. Normative Correction: Hide Inputs in Pydantic Errors

### Finding

`SecretStr` masks model representation and serialization, but a field-validator failure can still include the original raw input in Pydantic's `ValidationError` text unless settings error input display is disabled. The Task 1 test intentionally asserts that a rejected short secret is not disclosed, so the model configuration must enforce this behavior.

### Required implementation

In Task 1, when editing the existing `Settings.model_config = SettingsConfigDict(...)`, add:

```python
        hide_input_in_errors=True,
```

The resulting existing block must retain all current options and include the new option, for example:

```python
    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )
```

Do not replace or remove the current `env_file`, `env_file_encoding`, `case_sensitive`, or `extra` settings.

### Required verification

The following Task 1 assertion must pass:

```python
assert short_secret not in str(exc_info.value)
```

Also add this assertion to prove general input hiding rather than relying only on the chosen string:

```python
assert "input_value=" not in str(exc_info.value)
```

## 3. Normative Correction: Explicit Issuer Type Coverage

### Finding

The design requires every claim to have the correct type. The main plan explicitly tests audience, role, actor strings, UUID, and numeric dates, but wrong issuer values should also have a direct table-driven test rather than relying only on PyJWT behavior.

### Required Task 4 test

Append to `tests/security/test_internal_jwt.py` before the Task 4 RED run:

```python
@pytest.mark.parametrize("issuer", [123, True, [], {}, None])
def test_verifier_rejects_non_string_issuer(issuer: object) -> None:
    with pytest.raises(InternalTokenError):
        make_verifier().verify(encode_token(canonical_payload(iss=issuer)))
```

The final `_validate_issuer_and_audience` implementation already requires:

```python
if type(issuer) is not str or issuer != self._issuer:
    raise InternalTokenError("invalid internal JWT")
```

No production change beyond the main plan is required for this correction.

## 4. Normative Correction: Task 4 Commit Classification

Task 4 changes production verification behavior as well as tests. Use this commit message instead of the `test:` message shown in the main plan:

```powershell
git commit -m "feat: enforce strict internal token claims"
```

Update the planned commit sequence accordingly.

## 5. Execution Evidence Granularity

Where a main-plan step contains verification and commit commands in the same code block, execute and record them as two checkpoints:

1. run the tests, Ruff, and `git diff --check`; inspect their output;
2. only after that evidence is clean, stage and commit.

This preserves the required RED → GREEN → review → commit order without changing the task boundaries.

## 6. Confirmed Clean Decisions

The following plan decisions passed review without changes:

- `PyJWT>=2.10,<3` is the only added runtime dependency;
- allowed algorithms are hard-coded as `algorithms=["HS256"]`;
- built-in PyJWT wall-clock checks are disabled and replaced by the injected UTC clock;
- issuer and audience signature-bound validation remains enabled in PyJWT;
- all nine claims are required;
- Task 3 is now a true minimal verifier and Task 4 owns strict content and time validation;
- `roles` and `aud` are exact one-element arrays;
- `ActorContext` is frozen, slotted, and single-role;
- UUIDv4 canonicalization is explicit;
- bool numeric dates are rejected with `type(value) is int` checks;
- five-second boundary semantics are deterministic;
- the FastAPI test dependency override uses `lambda: make_verifier()` and therefore does not expose helper parameters as request inputs;
- `AppException` defensively copies caller-provided headers;
- all HTTP authentication failures use one controlled exception and one response envelope;
- no current router, endpoint, repository, service, model, migration, or Go file is in scope.

## 7. Placeholder and Consistency Review

No `TBD`, `TODO`, `implement later`, undefined interface, or cross-task naming mismatch remains. The fixed interfaces are:

```text
MaintenanceRole
ActorContext(user_id, tenant_id, role, request_id, token_id)
InternalTokenError
InternalTokenVerifier.verify(token: str) -> ActorContext
get_internal_token_verifier() -> InternalTokenVerifier
get_actor(...) -> ActorContext
InternalAuthenticationError
```

## 8. Approval Gate

Implementation may begin only after the user explicitly approves both:

```text
docs/superpowers/plans/2026-07-25-maintenance-unit05-internal-jwt-implementation.md
docs/superpowers/plans/2026-07-25-maintenance-unit05-internal-jwt-plan-review.md
```

During execution, apply the normative corrections in Sections 2–5 as if they were written directly into the corresponding main-plan steps.
