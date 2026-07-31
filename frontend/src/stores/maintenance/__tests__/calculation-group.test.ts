import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  CalculationGroup,
  CalculationGroupEvent,
} from '../../../api/maintenance/calculation-groups.ts'
import type { MaintenanceResult } from '../../../api/maintenance/types.ts'
import {
  initialCalculationGroupEventState,
  reduceGroupEvent,
} from '../../../components/maintenance/calculation/calculation-group-reducer.ts'
import { createCalculationGroupState } from '../calculationGroup.ts'

function event(
  sequence: number,
  type = 'child.progress',
): CalculationGroupEvent {
  return {
    id: sequence,
    group_id: 8,
    child_id: 2,
    sequence,
    event_type: type,
    payload: { progress_percent: '42.500000' },
    occurred_at: '2026-07-31T00:00:00Z',
  }
}

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
    },
  }
}

test('duplicate and out-of-order events are ignored', () => {
  const initial = initialCalculationGroupEventState(8)
  const state = reduceGroupEvent(initial, event(4))

  assert.deepEqual(
    reduceGroupEvent(state, event(4)),
    state,
  )
  assert.deepEqual(
    reduceGroupEvent(
      state,
      event(3, 'child.started'),
    ),
    state,
  )
})

test('events from another group are ignored', () => {
  const initial = initialCalculationGroupEventState(8)
  const foreign = {
    ...event(1),
    group_id: 9,
  }

  assert.deepEqual(
    reduceGroupEvent(initial, foreign),
    initial,
  )
})

test('group mutations are mutually exclusive', async () => {
  let finishCreate: (
    value: MaintenanceResult<CalculationGroup>,
  ) => void = () => undefined
  const createPromise = new Promise<
    MaintenanceResult<CalculationGroup>
  >((resolve) => {
    finishCreate = resolve
  })
  let retryCalls = 0
  const api = {
    create: async () => createPromise,
    get: async () => result({} as CalculationGroup),
    list: async () => result({
      items: [],
      page: 1,
      page_size: 20,
      total: 0,
      pages: 0,
    }),
    retryFailed: async () => {
      retryCalls += 1
      return result({} as CalculationGroup)
    },
    cancelRunning: async () => result(
      {} as CalculationGroup,
    ),
    getEvents: async () => result([]),
  }
  const state = createCalculationGroupState(
    api,
    () => ({
      start() {},
      stop() {},
      setVisible() {},
      setActive() {},
      lastSequence: () => 0,
    }),
  )
  const creating = state.create({
    scenario_version_id: 1,
    primary_candidate_key: 'WEIBULL:ANALYTICAL',
    selected_candidate_keys: [
      'WEIBULL:ANALYTICAL',
    ],
    random_seed: 20260723,
  }, 'create-key')

  await assert.rejects(
    () => state.retryFailed('retry-key'),
    /mutation is already in progress/,
  )
  assert.equal(retryCalls, 0)
  finishCreate(result({
    id: 8,
    scenario_version_id: 1,
    status: 'PENDING',
    primary_candidate_key: 'WEIBULL:ANALYTICAL',
    recommendation_snapshot: {},
    parameter_snapshot: {},
    last_event_sequence: 0,
    version: 1,
    created_by_user_id: 'user-a',
    created_by_request_id: 'request-a',
    created_at: '2026-07-31T00:00:00Z',
    updated_at: '2026-07-31T00:00:00Z',
    current_children: [],
  }))
  await creating

  assert.equal(state.group.value?.id, 8)
  assert.equal(state.mutating.value, false)
})
