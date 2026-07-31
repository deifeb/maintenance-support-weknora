import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  ScenarioDraftEnvelope,
  ScenarioDraftPayload,
  ScenarioMaterializeResult,
  ScenarioVersionSummary,
} from '../../../api/maintenance/scenarios.ts'
import type { MaintenanceResult } from '../../../api/maintenance/types.ts'
import { createScenarioDraftState } from '../scenarioDraft.ts'

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'scenario-store',
      tenant_id: 'tenant-a',
    },
  }
}

function envelope(
  sessionId: number,
  version = 1,
  overrides: Partial<ScenarioDraftEnvelope> = {},
): ScenarioDraftEnvelope {
  return {
    session_id: sessionId,
    snapshot_id: version,
    version,
    origin: 'MANUAL',
    draft: {
      scenario_name: `Scenario ${sessionId}`,
      current_step: 1,
      fields: {},
    },
    completion: {},
    blocking_fields: ['mission_code'],
    updated_at: '2026-07-31T00:00:00Z',
    permissions: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('stale draft loads cannot replace the active session', async () => {
  const first = deferred<
    MaintenanceResult<ScenarioDraftEnvelope>
  >()
  const second = deferred<
    MaintenanceResult<ScenarioDraftEnvelope>
  >()
  const api = {
    getDraft: (id: number) => (
      id === 1 ? first.promise : second.promise
    ),
    createDraft: async () => result(envelope(3)),
    saveDraft: async () => result(envelope(1)),
    materialize: async () => result(
      {} as ScenarioMaterializeResult,
    ),
    publishVersion: async () => result(
      {} as ScenarioVersionSummary,
    ),
  }
  const state = createScenarioDraftState(api)

  const loadFirst = state.load(1)
  const loadSecond = state.load(2)
  second.resolve(result(envelope(2)))
  await loadSecond
  first.resolve(result(envelope(1)))
  await loadFirst

  assert.equal(state.sessionId.value, 2)
  assert.equal(
    state.draft.value?.scenario_name,
    'Scenario 2',
  )
})

test('save conflicts preserve local edits and expose server version', async () => {
  const initial = envelope(7, 2)
  const api = {
    getDraft: async () => result(initial),
    createDraft: async () => result(initial),
    saveDraft: async () => {
      throw {
        code: 'SCENARIO_DRAFT_VERSION_CONFLICT',
        message: 'Draft changed',
        retryable: false,
        details: { actual_version: 4 },
      }
    },
    materialize: async () => result(
      {} as ScenarioMaterializeResult,
    ),
    publishVersion: async () => result(
      {} as ScenarioVersionSummary,
    ),
  }
  const state = createScenarioDraftState(api, {
    autosaveDelayMs: 1,
  })
  await state.load(7)

  state.updateField('service_level', {
    value: '0.97',
    source: 'USER_INPUT',
    confidence: null,
    risk: 'LOW',
    confirmed: true,
    evidence_refs: [],
  })
  await state.flushSave()

  assert.equal(state.autosave.value.status, 'conflict')
  assert.equal(state.autosave.value.dirty, true)
  assert.equal(state.conflictServerVersion.value, 4)
  assert.equal(
    state.draft.value?.fields.service_level?.value,
    '0.97',
  )
  assert.equal(state.version.value, 2)
})

test('materialization flushes first and publication needs capability', async () => {
  const ready = envelope(9, 3, {
    blocking_fields: [],
    permissions: [],
  })
  const calls: string[] = []
  const api = {
    getDraft: async () => result(ready),
    createDraft: async () => result(ready),
    saveDraft: async (
      _id: number,
      payload: {
        expected_version: number
        draft: ScenarioDraftPayload
      },
    ) => {
      calls.push(`save:${payload.expected_version}`)
      return result(envelope(9, 4, {
        draft: payload.draft,
        blocking_fields: [],
      }))
    },
    materialize: async (
      _id: number,
      version: number,
      key: string,
    ) => {
      calls.push(`materialize:${version}:${key}`)
      return result({
        scenario_id: 10,
        scenario_version_id: 11,
        status: 'DRAFT',
        validation: {
          valid: true,
          issues: [],
        },
        replayed: false,
      } satisfies ScenarioMaterializeResult)
    },
    publishVersion: async (versionId: number) => {
      calls.push(`publish:${versionId}`)
      return result({
        id: versionId,
        status: 'PUBLISHED',
      } as ScenarioVersionSummary)
    },
  }
  const state = createScenarioDraftState(api, {
    autosaveDelayMs: 60_000,
  })
  await state.load(9)
  state.rename('Ready locally')

  const materialized = await state.materialize('stable-key')

  assert.equal(materialized.scenario_version_id, 11)
  assert.deepEqual(calls, [
    'save:3',
    'materialize:4:stable-key',
  ])
  await assert.rejects(
    () => state.publishVersion(11),
    /SCENARIO_PUBLISH permission/,
  )
})
