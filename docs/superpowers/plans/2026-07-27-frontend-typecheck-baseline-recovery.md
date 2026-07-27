# Frontend Type-Check Baseline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the existing WeKnora frontend `npm run type-check` baseline from seven known TypeScript errors to a clean pass without changing runtime behavior or mixing the maintenance typed-client work into the baseline-fix commit.

**Architecture:** Apply three minimal, source-local corrections: remove a dead compatibility read from sidebar bucket options, narrow unknown MCP service IDs to strings before building select options, and import Vue's already-used `nextTick` helper. Preserve the currently uncommitted Plan 05-2 Task 1 files and use exact-path staging so the plan, baseline repair, and typed client remain independently reviewable.

**Tech Stack:** Vue 3.5, TypeScript 6, vue-tsc, Node `test` through `tsx --test`, npm lockfile v3, PowerShell 5.1, Git worktrees.

## Global Constraints

- Worktree: `E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05`.
- Branch: `feature/maintenance-frontend-plan05`.
- Starting HEAD before the plan commit: `85732e41512ea6f993e644707dd332dfd2fe6de0`.
- Preserve the five uncommitted Plan 05-2 Task 1 paths exactly; do not stage them in either baseline-recovery commit.
- Do not modify API behavior, sidebar visibility behavior, agent configuration persistence, or system-setting interaction behavior.
- Do not add dependencies or change `package.json` or `package-lock.json`.
- Use exact-path staging only; never use `git add .` or `git add -A`.
- Stop for review before each commit, push, or Draft PR update.
- Full `npm run type-check` must pass before the baseline-fix commit is approved.
- The Plan 05-2 Task 1 targeted tests must remain green after the baseline repair.

---

## File Map

**Create:**

```text
docs/superpowers/plans/2026-07-27-frontend-typecheck-baseline-recovery.md
```

**Modify:**

```text
frontend/src/components/sessionSidebarBuckets.ts
frontend/src/views/agent/AgentEditorModal.vue
frontend/src/views/system/SystemSettings.vue
```

**Existing tests used without modification:**

```text
frontend/src/components/sessionSidebarBuckets.test.ts
frontend/src/api/maintenance/__tests__/client.test.ts
frontend/src/api/maintenance/__tests__/query.test.ts
```

---

### Task 0: Record the Approved Baseline-Recovery Plan

**Files:**
- Create: `docs/superpowers/plans/2026-07-27-frontend-typecheck-baseline-recovery.md`

**Interfaces:**
- Consumes: the verified seven-error baseline report from Plan 05-2 Task 1.
- Produces: the durable implementation and review contract for the three-file baseline repair.

- [ ] **Step 1: Verify the plan file and current dirty scope**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
git status --short
git diff --check -- docs/superpowers/plans/2026-07-27-frontend-typecheck-baseline-recovery.md
```

Expected: the plan is one untracked file; the five existing Task 1 paths remain present and unstaged; no trailing-whitespace errors.

- [ ] **Step 2: Review the exact contracts**

Confirm the plan contains:

```text
sessionSidebarBuckets.ts: remove the dead includeApiBucket fallback
AgentEditorModal.vue: narrow mcp_services entries to strings
SystemSettings.vue: import nextTick from vue
npm run type-check: PASS required
Task 1 targeted tests: PASS required
baseline implementation commit: fix: restore frontend type-check baseline
```

- [ ] **Step 3: Commit only the approved plan**

Run only after explicit review approval:

```powershell
git add -- docs/superpowers/plans/2026-07-27-frontend-typecheck-baseline-recovery.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: plan frontend type-check baseline recovery"
```

Expected: the cached path list contains exactly the plan file. The five Task 1 paths remain unstaged.

---

### Task 1: Restore the Seven-Error Frontend Type-Check Baseline

**Files:**
- Modify: `frontend/src/components/sessionSidebarBuckets.ts:77-89`
- Modify: `frontend/src/views/agent/AgentEditorModal.vue:1835-1860`
- Modify: `frontend/src/views/system/SystemSettings.vue:484`
- Test: `frontend/src/components/sessionSidebarBuckets.test.ts`
- Test: `frontend/src/api/maintenance/__tests__/client.test.ts`
- Test: `frontend/src/api/maintenance/__tests__/query.test.ts`

**Interfaces:**
- Consumes: `buildBucketDefinitions`, `formData.value.config.mcp_services`, Vue `nextTick`, and the existing npm scripts.
- Produces: a clean `vue-tsc --build` result with no runtime contract changes.

- [ ] **Step 1: Reproduce the exact failing baseline**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\frontend
npm run type-check
```

Expected: FAIL with exactly seven diagnostics:

```text
src/components/sessionSidebarBuckets.ts: one TS2339 includeApiBucket diagnostic
src/views/agent/AgentEditorModal.vue: one TS2345 and one TS2322 unknown-to-string diagnostic
src/views/system/SystemSettings.vue: four TS2304 nextTick diagnostics
```

No diagnostic may reference `src/api/maintenance` or `src/utils/request.ts`.

- [ ] **Step 2: Establish the existing sidebar behavior baseline**

Run:

```powershell
npm run test -- src/components/sessionSidebarBuckets.test.ts
```

Expected: PASS. The repair must preserve current admin-only channel-bucket behavior.

- [ ] **Step 3: Remove the dead sidebar compatibility read**

In `frontend/src/components/sessionSidebarBuckets.ts`, replace:

```ts
const includeChannels = options.includeAdminChannelBuckets ?? options.includeApiBucket ?? false
```

with:

```ts
const includeChannels = options.includeAdminChannelBuckets ?? false
```

Repository search shows no caller or declared option named `includeApiBucket`; current callers and tests use `includeAdminChannelBuckets`.

- [ ] **Step 4: Narrow MCP service IDs before option construction**

In `frontend/src/views/agent/AgentEditorModal.vue`, replace:

```ts
const selectedIds = new Set(formData.value.config.mcp_services || []);
```

with:

```ts
const selectedIds = new Set(
  Array.isArray(formData.value.config.mcp_services)
    ? formData.value.config.mcp_services.filter(
        (id): id is string => typeof id === 'string',
      )
    : [],
);
```

Only string IDs are valid for the string-keyed service map and TDesign option values. Invalid persisted entries are ignored rather than coerced.

- [ ] **Step 5: Import the Vue helper already used by System Settings**

In `frontend/src/views/system/SystemSettings.vue`, replace:

```ts
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue'
```

with:

```ts
import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue'
```

Do not change any `nextTick()` call sites.

- [ ] **Step 6: Verify the full type check is green**

Run:

```powershell
npm run type-check
```

Expected: PASS with exit code 0 and no TypeScript diagnostics.

- [ ] **Step 7: Verify existing behavior and Task 1 remain green**

Run:

```powershell
npm run test -- src/components/sessionSidebarBuckets.test.ts
npm run test -- src/api/maintenance/__tests__/client.test.ts src/api/maintenance/__tests__/query.test.ts
```

Expected: both commands PASS.

- [ ] **Step 8: Verify exact scope and stop for review**

Run:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05
git diff --check
git diff --name-only
git diff --cached --name-only
git status --short
```

Expected:

- no staged paths;
- baseline-repair changes are exactly the three files in this task;
- the five Task 1 paths remain unstaged;
- no package or lockfile changes.

Export a three-file review diff and status manifest. Do not stage, commit, push, or update the Draft PR.

- [ ] **Step 9: Commit only the approved baseline repair**

Run only after explicit review approval:

```powershell
git add -- frontend/src/components/sessionSidebarBuckets.ts frontend/src/views/agent/AgentEditorModal.vue frontend/src/views/system/SystemSettings.vue
git diff --cached --check
git diff --cached --name-only
git commit -m "fix: restore frontend type-check baseline"
```

Expected: the commit contains exactly the three baseline files. The five Task 1 paths remain uncommitted.

---

## Final Verification Contract

Before Plan 05-2 Task 1 can be committed:

```powershell
cd E:\weknora_projects\maintenance-support-weknora\.worktrees\maintenance-frontend-plan05\frontend
npm run type-check
npm run test -- src/components/sessionSidebarBuckets.test.ts
npm run test -- src/api/maintenance/__tests__/client.test.ts src/api/maintenance/__tests__/query.test.ts
```

Expected:

```text
FULL_TYPE_CHECK=PASS
SIDEBAR_BUCKET_TESTS=PASS
TASK1_TYPED_CLIENT_TESTS=PASS
TASK1_TYPECHECK_REGRESSION=0
```

The next independent implementation commit remains:

```text
feat: add typed maintenance frontend client
```
