# Maintenance Task 9 Browser Coverage Design

## Goal

Close the two remaining Plan 05 Task 9 browser-acceptance gaps with repeatable
real-stack tests: six Maintenance Chat Card types through a real chat request,
and allocation partial-failure/retry behavior through the real browser/API
path.

## Scope

In scope:

- local Ollama-backed WeKnora chat request and SSE completion handling;
- backend business-card projection and frontend card rendering/navigation;
- deterministic allocation execution with one successful line and one failed
  line;
- retrying only failed allocation lines without duplicating successful effects;
- E2E seed fixtures, browser specs, runtime configuration, and acceptance docs.

Out of scope:

- changing the six card schemas or their visual design;
- changing allocation authority, reservation semantics, or production retry
  policy;
- browser mocks that replace the WeKnora or Maintenance API response;
- requiring a local model to populate optional fields beyond schema validity.

## Architecture and Data Flow

The browser origin remains Vite. Chat traffic follows the existing production
path:

```text
Playwright -> Vite proxy -> WeKnora chat endpoint -> Maintenance MCP/tool
           -> Maintenance API -> business_card_service -> SSE completion
           -> botmsg -> MaintenanceBusinessCardHost
```

The E2E runtime passes `OLLAMA_BASE_URL` and `OLLAMA_MODEL` through the
disposable WeKnora process. The seed creates deterministic maintenance records
and a chat-capable agent/session context. The browser sends a real maintenance
question and waits for the terminal SSE event. The test asserts that the
terminal message contains exactly one valid instance of each registered card
type, that malformed/unknown cards are absent, and that each safe navigation
path opens the expected maintenance route.

Allocation coverage uses the existing published demand-list and allocation-plan
fixtures. A test-only failure selector is supplied through the E2E seed/runtime
environment and is consumed at the reservation authority boundary. It fails a
single known line after the other line is committed. The browser then verifies
the partial result, selects the failed line only, retries, and verifies the
final authoritative plan and ledger state. The selector is disabled by default
and is rejected outside the E2E runtime.

## Failure Handling

- Chat transport, model-unavailable, malformed-card, and timeout errors remain
  visible as the existing chat error state; the test records the response body
  and fails with the request correlation id.
- A partial allocation response must preserve successful lines, identify failed
  lines with retryable metadata, and expose an explicit retry action.
- Retry requests must contain only failed line identifiers and the same logical
  command/idempotency key. Replaying the completed request must not create a
  second reservation or ledger entry.
- Tenant identity continues to come from the authenticated actor; browser
  requests must not add a `tenant_id` query parameter.

## Testing Strategy

### Chat Card browser test

- Run against Docker PostgreSQL, Maintenance API, Vite, WeKnora, and local
  Ollama.
- Authenticate with the seeded tenant-admin storage state.
- Create or select the seeded chat session, submit a maintenance question, and
  wait for the terminal response.
- Assert six card types, card titles/summaries, safe navigation targets, and no
  duplicate cards after history reload.
- Keep the model contract structural: a valid terminal response and valid card
  payloads are required; optional scenario fields are not asserted by value.

### Allocation partial/retry browser test

- Open the seeded allocation-plan workflow.
- Execute with the deterministic failure selector enabled.
- Assert partial status, one successful line, one retryable failed line, and a
  visible retry action.
- Retry only the failed line and assert completed status plus exactly one
  authoritative effect per line.
- Replay the same retry command and assert no additional effect.

### Verification commands

```powershell
$env:E2E_GO_RUNTIME = 'wsl'
$env:E2E_WSL_GO_PATH = '/usr/local/go/bin/go'
$env:E2E_WSL_GOMODCACHE = 'C:\Users\<user>\go\pkg\mod'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:OLLAMA_MODEL = 'Qwen3.5-9B:latest'
npm run test -- e2e/maintenance/runtime.test.ts
npm run test:e2e -- e2e/maintenance/chat-cards-real.spec.ts e2e/maintenance/allocation-partial-retry.spec.ts
```

The final gate reruns the complete Maintenance browser suite, frontend type
checking, focused Maintenance API tests, provider tests, and `git diff --check`.
