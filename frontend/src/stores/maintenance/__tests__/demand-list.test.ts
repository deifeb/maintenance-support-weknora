import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  DecimalString,
  DemandList,
  DemandListCreateRequest,
  DemandListItemUpdateRequest,
} from '../../../api/maintenance/demand-lists.ts'
import type {
  MaintenanceResult,
} from '../../../api/maintenance/types.ts'
import {
  createDemandListState,
  type DemandListStoreApi,
} from '../demandList.ts'

function result<T>(
  data: T,
): MaintenanceResult<T> {
  let version: number | undefined
  if (
    typeof data === 'object'
    && data !== null
    && 'version' in data
  ) {
    const candidate = (
      data as { version?: unknown }
    ).version
    if (typeof candidate === 'number') {
      version = candidate
    }
  }

  return {
    data,
    meta: {
      request_id: 'request-a',
      tenant_id: 'tenant-a',
      version,
    },
  }
}

function demandList(
  overrides: Partial<DemandList> = {},
): DemandList {
  return {
    id: 41,
    name: 'Demand list 41',
    description: 'Task 5 fixture',
    lineage_id: '11111111-2222-3333-4444-555555555555',
    version_number: 1,
    derived_from_id: null,
    scenario_version_id: 3,
    calculation_group_id: 9,
    status: 'DRAFT',
    is_current: false,
    superseded_by_id: null,
    superseded_at: null,
    version: 7,
    created_by_user_id: 'user-a',
    created_by_request_id: 'request-a',
    created_at: '2026-08-01T12:00:00Z',
    updated_at: '2026-08-01T12:00:00Z',
    submitted_by_user_id: null,
    submitted_by_request_id: null,
    submitted_at: null,
    confirmed_by_user_id: null,
    confirmed_by_request_id: null,
    confirmed_at: null,
    published_by_user_id: null,
    published_by_request_id: null,
    published_at: null,
    voided_by_user_id: null,
    voided_by_request_id: null,
    voided_at: null,
    items: [],
    events: [],
    ...overrides,
  }
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return {
    promise,
    resolve,
    reject,
  }
}

function keyFactory(...keys: string[]): () => string {
  let index = 0
  return () => keys[index++] ?? `unexpected-key-${index}`
}

const retryableFailure = {
  status: 503,
  error: {
    code: 'SERVICE_UNAVAILABLE',
    message: 'Response outcome is unknown',
    details: { retryable: true },
  },
  meta: { request_id: 'retryable-request' },
}

function apiStub(
  overrides: Partial<DemandListStoreApi> = {},
): DemandListStoreApi {
  return {
    async create(
      _request: DemandListCreateRequest,
      _idempotencyKey: string,
    ) {
      return result(demandList())
    },
    async get(_demandListId: number) {
      return result(demandList())
    },
    async updateItem(
      _demandListId: number,
      _itemId: number,
      _request: DemandListItemUpdateRequest,
    ) {
      return result(demandList())
    },
    async submit(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 8,
      }))
    },
    async confirm(
      _demandListId: number,
      _expectedVersion: number,
      _confirmationNote: string,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'CONFIRMED',
        version: 9,
      }))
    },
    async publish(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'PUBLISHED',
        is_current: true,
        version: 10,
      }))
    },
    async derive(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        id: 42,
        version_number: 2,
        derived_from_id: 41,
        status: 'DRAFT',
        is_current: false,
        version: 1,
      }))
    },
    async void(
      _demandListId: number,
      _expectedVersion: number,
      _idempotencyKey: string,
    ) {
      return result(demandList({
        status: 'VOIDED',
        is_current: false,
        version: 11,
      }))
    },
    ...overrides,
  }
}

test('create applies the returned aggregate', async () => {
  const state = createDemandListState(apiStub({
    create: async () => result(demandList({
      id: 51,
      name: 'Created list',
    })),
  }))

  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Created list',
  }
  const created = await state.create(request)

  assert.equal(created.id, 51)
  assert.equal(state.current.value?.id, 51)
  assert.equal(state.mutating.value, false)
})

test('a slower first load cannot overwrite a newer route', async () => {
  const first = deferred<MaintenanceResult<DemandList>>()
  const second = deferred<MaintenanceResult<DemandList>>()
  let call = 0

  const state = createDemandListState(apiStub({
    get: async () => {
      call += 1
      return call === 1
        ? first.promise
        : second.promise
    },
  }))

  const loadingFirst = state.load(41)
  const loadingSecond = state.load(42)

  second.resolve(result(demandList({
    id: 42,
    name: 'New route',
  })))
  await loadingSecond

  first.resolve(result(demandList({
    id: 41,
    name: 'Stale route',
  })))
  await loadingFirst

  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.name, 'New route')
  assert.equal(state.loading.value, false)
})

test('dispose invalidates an in-flight load', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()
  const state = createDemandListState(apiStub({
    get: async () => pending.promise,
  }))

  const loading = state.load(41)
  state.dispose()
  pending.resolve(result(demandList({
    id: 41,
  })))
  await loading

  assert.equal(state.current.value, null)
})

test('all demand-list mutations are mutually exclusive', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()
  let submitCalls = 0

  const state = createDemandListState(apiStub({
    updateItem: async () => pending.promise,
    submit: async () => {
      submitCalls += 1
      return result(demandList())
    },
  }))

  await state.load(41)
  const updating = state.updateItem(
    501,
    '12.500000',
    'Approved',
  )

  await assert.rejects(
    () => state.submit(),
    /mutation is already in progress/,
  )
  assert.equal(submitCalls, 0)

  pending.resolve(result(demandList({
    version: 8,
  })))
  await updating
  assert.equal(state.mutating.value, false)
})

test('mutation without a loaded aggregate is rejected before API use', async () => {
  let calls = 0
  const state = createDemandListState(apiStub({
    submit: async () => {
      calls += 1
      return result(demandList())
    },
  }))

  await assert.rejects(
    () => state.submit(),
    /Demand list is not loaded/,
  )
  assert.equal(calls, 0)
  assert.equal(state.mutating.value, false)
})

test('update and submit use successive server versions', async () => {
  const captured: Array<{
    operation: string
    version: number
  }> = []

  const state = createDemandListState(apiStub({
    updateItem: async (
      _listId,
      _itemId,
      request,
    ) => {
      captured.push({
        operation: 'update',
        version: request.expected_version,
      })
      return result(demandList({
        version: 8,
      }))
    },
    submit: async (
      _listId,
      expectedVersion,
    ) => {
      captured.push({
        operation: 'submit',
        version: expectedVersion,
      })
      return result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 9,
      }))
    },
  }))

  await state.load(41)
  await state.updateItem(
    501,
    '12.500000',
    'Approved',
  )
  await state.submit()

  assert.deepEqual(captured, [
    { operation: 'update', version: 7 },
    { operation: 'submit', version: 8 },
  ])
  assert.equal(state.current.value?.version, 9)
})

test('confirm forwards the exact note and current version', async () => {
  let captured:
    | {
        id: number
        version: number
        note: string
        key: string
      }
    | undefined

  const state = createDemandListState(
    apiStub({
      get: async () => result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 8,
      })),
      confirm: async (
        id,
        version,
        note,
        key,
      ) => {
        captured = { id, version, note, key }
        return result(demandList({
          status: 'CONFIRMED',
          version: 9,
        }))
      },
    }),
    () => 'confirm-key',
  )

  await state.load(41)
  await state.confirm('Approved by administrator')

  assert.deepEqual(captured, {
    id: 41,
    version: 8,
    note: 'Approved by administrator',
    key: 'confirm-key',
  })
  assert.equal(
    state.current.value?.status,
    'CONFIRMED',
  )
})

test('publish replaces state with the complete server aggregate', async () => {
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'CONFIRMED',
      version: 9,
    })),
    publish: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      published_by_user_id: 'admin-a',
      published_at: '2026-08-01T13:00:00Z',
      version: 10,
      events: [{
        id: 700,
        demand_list_id: 41,
        event_type: 'PUBLISHED',
        actor_user_id: 'admin-a',
        actor_roles_json: ['admin'],
        request_id: 'request-publish',
        idempotency_key: 'publish-key',
        request_hash: 'hash-a',
        before_summary_json: {
          status: 'CONFIRMED',
        },
        after_summary_json: {
          status: 'PUBLISHED',
        },
        response_snapshot_json: {
          id: 41,
          version: 10,
        },
        occurred_at: '2026-08-01T13:00:00Z',
      }],
    })),
  }))

  await state.load(41)
  const published = await state.publish()

  assert.equal(published.status, 'PUBLISHED')
  assert.equal(state.current.value?.is_current, true)
  assert.equal(
    state.current.value?.events.at(-1)?.event_type,
    'PUBLISHED',
  )
})

test('derive replaces current with the returned new DRAFT id', async () => {
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      version: 10,
    })),
    derive: async () => result(demandList({
      id: 42,
      version_number: 2,
      derived_from_id: 41,
      status: 'DRAFT',
      version: 1,
    })),
  }))

  await state.load(41)
  const derived = await state.derive()

  assert.equal(derived.id, 42)
  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.status, 'DRAFT')
})

test('voidList forwards the current version', async () => {
  let capturedVersion = 0
  const state = createDemandListState(apiStub({
    get: async () => result(demandList({
      status: 'PUBLISHED',
      is_current: true,
      version: 10,
    })),
    void: async (
      _id,
      version,
    ) => {
      capturedVersion = version
      return result(demandList({
        status: 'VOIDED',
        is_current: false,
        version: 11,
      }))
    },
  }))

  await state.load(41)
  await state.voidList()

  assert.equal(capturedVersion, 10)
  assert.equal(state.current.value?.status, 'VOIDED')
})

test('route change during mutation prevents stale state replacement', async () => {
  const pending = deferred<
    MaintenanceResult<DemandList>
  >()

  const state = createDemandListState(apiStub({
    get: async (id) => result(demandList({
      id,
      name: `List ${id}`,
    })),
    updateItem: async () => pending.promise,
  }))

  await state.load(41)
  const updating = state.updateItem(
    501,
    '12.500000',
    'Approved',
  )

  await state.load(42)
  pending.resolve(result(demandList({
    id: 41,
    name: 'Stale mutation result',
    version: 8,
  })))
  await updating

  assert.equal(state.current.value?.id, 42)
  assert.equal(state.current.value?.name, 'List 42')
})

test('mutation failure preserves aggregate and structured conflict details', async () => {
  const conflict = {
    status: 409,
    error: {
      code: 'DEMAND_LIST_VERSION_CONFLICT',
      message: 'Demand list version conflict',
      details: {
        expected_version: 7,
        actual_version: 8,
        conflict_object: 'demand_list',
        retryable: false,
      },
    },
    meta: {
      request_id: 'request-conflict',
    },
  }

  const state = createDemandListState(apiStub({
    updateItem: async () => {
      throw conflict
    },
  }))

  await state.load(41)
  const before = state.current.value

  await assert.rejects(
    () => state.updateItem(
      501,
      '12.500000',
      'Approved',
    ),
  )

  assert.equal(state.current.value, before)
  assert.equal(
    state.error.value?.code,
    'DEMAND_LIST_VERSION_CONFLICT',
  )
  assert.deepEqual(
    state.error.value?.details,
    conflict.error.details,
  )
  assert.equal(
    state.error.value?.request_id,
    'request-conflict',
  )
  assert.equal(state.mutating.value, false)
})

test('decimal-string values remain strings in store calls', async () => {
  let captured: DecimalString | undefined

  const state = createDemandListState(apiStub({
    updateItem: async (
      _listId,
      _itemId,
      request,
    ) => {
      captured = request.final_quantity
      return result(demandList({
        version: 8,
      }))
    },
  }))

  await state.load(41)
  await state.updateItem(
    501,
    '9007199254740993.125000',
    'Preserve exact precision',
  )

  assert.equal(
    captured,
    '9007199254740993.125000',
  )
  assert.equal(typeof captured, 'string')
})

test('retryable create failure reuses the same logical-command key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      create: async (_request, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({ id: 51 }))
      },
    }),
    keyFactory('create-key-1', 'create-key-2'),
  )
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Created list',
    description: null,
  }

  await assert.rejects(() => state.create(request))
  await state.create(request)
  await state.create({ ...request, name: 'Another list' })

  assert.deepEqual(captured, [
    'create-key-1',
    'create-key-1',
    'create-key-2',
  ])
})

test('retryable submit failure reuses the same current-version key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      submit: async (_id, _version, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({
          status: 'PENDING_CONFIRMATION',
          version: 8,
        }))
      },
    }),
    keyFactory('submit-key-1', 'submit-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.submit())
  await state.submit()

  assert.deepEqual(captured, [
    'submit-key-1',
    'submit-key-1',
  ])
})

test('non-retryable failure releases the logical-command key', async () => {
  const captured: string[] = []
  let calls = 0
  const conflict = {
    status: 409,
    error: {
      code: 'DEMAND_LIST_VERSION_CONFLICT',
      message: 'Demand list version conflict',
      details: { retryable: false },
    },
    meta: { request_id: 'conflict-request' },
  }
  const state = createDemandListState(
    apiStub({
      submit: async (_id, _version, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw conflict
        return result(demandList({
          status: 'PENDING_CONFIRMATION',
          version: 8,
        }))
      },
    }),
    keyFactory('submit-key-1', 'submit-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.submit())
  await state.submit()

  assert.deepEqual(captured, [
    'submit-key-1',
    'submit-key-2',
  ])
})

test('dispose abandons a retryable pending command key', async () => {
  const captured: string[] = []
  let calls = 0
  const state = createDemandListState(
    apiStub({
      create: async (_request, key) => {
        captured.push(key)
        calls += 1
        if (calls === 1) throw retryableFailure
        return result(demandList({ id: 52 }))
      },
    }),
    keyFactory('create-key-1', 'create-key-2'),
  )
  const request: DemandListCreateRequest = {
    calculation_group_id: 9,
    name: 'Disposable create',
    description: null,
  }

  await assert.rejects(() => state.create(request))
  state.dispose()
  await state.create(request)

  assert.deepEqual(captured, [
    'create-key-1',
    'create-key-2',
  ])
})

test('a changed confirmation note starts a new logical command', async () => {
  const captured: string[] = []
  const state = createDemandListState(
    apiStub({
      get: async () => result(demandList({
        status: 'PENDING_CONFIRMATION',
        version: 8,
      })),
      confirm: async (_id, _version, _note, key) => {
        captured.push(key)
        throw retryableFailure
      },
    }),
    keyFactory('confirm-key-1', 'confirm-key-2'),
  )

  await state.load(41)
  await assert.rejects(() => state.confirm('First note'))
  await assert.rejects(() => state.confirm('Second note'))

  assert.deepEqual(captured, [
    'confirm-key-1',
    'confirm-key-2',
  ])
})

test('publish derive and void use action-owned command keys', async () => {
  const captured: Array<[string, string]> = []
  const state = createDemandListState(
    apiStub({
      publish: async (_id, _version, key) => {
        captured.push(['publish', key])
        return result(demandList({
          status: 'PUBLISHED',
          version: 8,
        }))
      },
      derive: async (_id, _version, key) => {
        captured.push(['derive', key])
        return result(demandList({ id: 42, version: 1 }))
      },
      void: async (_id, _version, key) => {
        captured.push(['void', key])
        return result(demandList({
          id: 42,
          status: 'VOIDED',
          version: 2,
        }))
      },
    }),
    (action) => `${action}-owned-key`,
  )

  await state.load(41)
  await state.publish()
  await state.derive()
  await state.voidList()

  assert.deepEqual(captured, [
    ['publish', 'publish-owned-key'],
    ['derive', 'derive-owned-key'],
    ['void', 'void-owned-key'],
  ])
})
