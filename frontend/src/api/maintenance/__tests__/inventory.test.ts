import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createInventoryApi,
  type InventoryApiClient,
  type InventoryBalanceListQuery,
  type InventoryBalanceRead,
  type InventoryExpectedVersionRequest,
  type InventoryOperationExecuteRequest,
  type InventoryOperationPreviewRequest,
  type InventoryReserveRequest,
  type InventoryReservationIssueRequest,
  type InventoryReservationReleaseRequest,
  type InventoryReservationReturnRequest,
  type InventoryReversePreviewRequest,
  type InventoryStocktakeConfirmExecuteRequest,
  type InventoryStocktakeCountRequest,
  type InventoryStocktakeCreateRequest,
  type InventoryStocktakeRebaseRequest,
  type InventoryTransferCreateRequest,
  type InventoryTransferExecuteRequest,
  type InventoryTransferReceivePreviewRequest,
} from '../inventory.ts'
import type { MaintenanceResult } from '../types.ts'

interface CapturedCall {
  method: 'GET' | 'POST' | 'PATCH'
  path: string
  body?: unknown
  headers?: Record<string, string>
}

type ResponseFactory = (
  method: CapturedCall['method'],
  path: string,
  body?: unknown,
) => unknown

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-inventory-red',
      tenant_id: 'tenant-inventory-red',
    },
  }
}

function headersFrom(config: unknown): Record<string, string> | undefined {
  if (typeof config !== 'object' || config === null) return undefined

  const headers = (config as { headers?: unknown }).headers
  if (typeof headers !== 'object' || headers === null) return undefined

  const normalized: Record<string, string> = {}
  for (const [key, value] of Object.entries(headers)) {
    if (typeof value === 'string') {
      normalized[key] = value
    }
  }
  return normalized
}

function fakeClient(
  calls: CapturedCall[],
  responseFactory: ResponseFactory = () => ({}),
): InventoryApiClient {
  return {
    async get<T>(path: string): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result(responseFactory('GET', path) as T)
    },
    async post<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'POST',
        path,
        body,
        headers: headersFrom(config),
      })
      return result(responseFactory('POST', path, body) as T)
    },
    async patch<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({
        method: 'PATCH',
        path,
        body,
        headers: headersFrom(config),
      })
      return result(responseFactory('PATCH', path, body) as T)
    },
  }
}

const balanceFixture: InventoryBalanceRead = {
  id: 1,
  warehouse_id: 7,
  location_id: 8,
  spare_part_id: 41,
  lot_id: null,
  serial_item_id: null,
  serial_item_ids: [],
  on_hand_quantity: '100.0000',
  reserved_quantity: '10.0000',
  damaged_quantity: '2.0000',
  quarantined_quantity: '3.0000',
  in_transit_quantity: '4.0000',
  available_quantity: '85.0000',
  version: 4,
  lot_version: null,
  lot_is_frozen: null,
}

const reserveRequest: InventoryReserveRequest = {
  owner_type: 'WORK_ORDER',
  owner_id: 'WO-001',
  spare_part_id: 41,
  warehouse_id: 7,
  requested_quantity: '5.0000',
  allow_partial: false,
  expected_balance_versions: { 91: 4 },
  as_of: '2026-08-16',
}

const expectedVersionRequest: InventoryExpectedVersionRequest = {
  expected_version: 4,
}

const issueRequest: InventoryReservationIssueRequest = {
  expected_version: 4,
  lines: [{ reservation_line_id: 101, quantity: '1.0000' }],
}

const releaseRequest: InventoryReservationReleaseRequest = {
  expected_version: 5,
  lines: [{ reservation_line_id: 101, quantity: '1.0000' }],
}

const returnRequest: InventoryReservationReturnRequest = {
  expected_version: 6,
  lines: [{
    reservation_line_id: 101,
    quantity: '1.0000',
    issue_transaction_id: 301,
  }],
}

const freezeRequest: InventoryOperationPreviewRequest = {
  operation_type: 'FREEZE',
  balance_id: 11,
  expected_balance_version: 5,
  reason: 'quality hold',
  deltas: null,
  lot_id: 71,
  expected_lot_version: 9,
}

const executeRequest: InventoryOperationExecuteRequest = {
  expected_transaction_version: 2,
  confirmation_token: 'confirm-token',
}

const reversePreviewRequest: InventoryReversePreviewRequest = {
  expected_transaction_version: 3,
  reason: 'reverse correction',
}

const transferCreateRequest: InventoryTransferCreateRequest = {
  source_warehouse_id: 7,
  source_location_id: 8,
  target_warehouse_id: 9,
  target_location_id: 10,
  reason: 'replenishment',
  lines: [{
    spare_part_id: 41,
    source_balance_id: 11,
    quantity: '2.0000',
    expected_source_version: 5,
  }],
}

const transferExecuteRequest: InventoryTransferExecuteRequest = {
  transaction_id: 501,
  expected_transaction_version: 2,
  confirmation_token: 'transfer-confirm-token',
}

const transferReceiveRequest: InventoryTransferReceivePreviewRequest = {
  expected_version: 3,
  lines: [{ transfer_line_id: 601, quantity: '1.0000' }],
}

const stocktakeCreateRequest: InventoryStocktakeCreateRequest = {
  warehouse_id: 7,
  location_id: 8,
}

const stocktakeCountRequest: InventoryStocktakeCountRequest = {
  expected_version: 4,
  expected_line_version: 2,
  counted_quantity: '99.0000',
}

const stocktakeConfirmExecuteRequest: InventoryStocktakeConfirmExecuteRequest = {
  transaction_id: 701,
  expected_transaction_version: 2,
  confirmation_token: 'stocktake-confirm-token',
}

const stocktakeRebaseRequest: InventoryStocktakeRebaseRequest = {
  expected_version: 5,
  lines: [{ line_id: 801, action: 'RECOUNT' }],
}

test('inventory lists serialize only frozen server query fields', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.listBalances({
    page: 2,
    page_size: 100,
    warehouse_id: 7,
    spare_part_id: 41,
    sort_by: 'available_quantity',
    sort_order: 'desc',
  })
  await api.listTransactions({
    page: 3,
    page_size: 50,
    operation_type: 'FREEZE',
    status: 'COMPLETED',
    reference_type: 'WORK_ORDER',
    reference_id: 'WO-001',
    sort_by: 'completed_at',
    sort_order: 'desc',
  })
  await api.listReservations({
    page: 4,
    page_size: 25,
    status: 'ACTIVE',
    owner_type: 'WORK_ORDER',
    owner_id: 'WO-001',
    sort_by: 'expires_at',
    sort_order: 'asc',
  })
  await api.listTransfers({
    page: 5,
    page_size: 20,
    status: 'DISPATCHED',
    source_warehouse_id: 7,
    source_location_id: 8,
    target_warehouse_id: 9,
    target_location_id: 10,
    reference_type: 'WORK_ORDER',
    reference_id: 'WO-001',
    sort_by: 'completed_at',
    sort_order: 'desc',
  })
  await api.listStocktakes({
    page: 6,
    page_size: 10,
    status: 'REVIEWING',
    warehouse_id: 7,
    location_id: 8,
    sort_by: 'snapshot_at',
    sort_order: 'desc',
  })

  assert.deepEqual(
    calls.map((call) => call.path),
    [
      (
        '/v1/inventory/balances'
        + '?page=2'
        + '&page_size=100'
        + '&warehouse_id=7'
        + '&spare_part_id=41'
        + '&sort_by=available_quantity'
        + '&sort_order=desc'
      ),
      (
        '/v1/inventory/transactions'
        + '?page=3'
        + '&page_size=50'
        + '&operation_type=FREEZE'
        + '&status=COMPLETED'
        + '&reference_type=WORK_ORDER'
        + '&reference_id=WO-001'
        + '&sort_by=completed_at'
        + '&sort_order=desc'
      ),
      (
        '/v1/inventory/reservations'
        + '?page=4'
        + '&page_size=25'
        + '&status=ACTIVE'
        + '&owner_type=WORK_ORDER'
        + '&owner_id=WO-001'
        + '&sort_by=expires_at'
        + '&sort_order=asc'
      ),
      (
        '/v1/inventory/transfers'
        + '?page=5'
        + '&page_size=20'
        + '&status=DISPATCHED'
        + '&source_warehouse_id=7'
        + '&source_location_id=8'
        + '&target_warehouse_id=9'
        + '&target_location_id=10'
        + '&reference_type=WORK_ORDER'
        + '&reference_id=WO-001'
        + '&sort_by=completed_at'
        + '&sort_order=desc'
      ),
      (
        '/v1/inventory/stocktakes'
        + '?page=6'
        + '&page_size=10'
        + '&status=REVIEWING'
        + '&warehouse_id=7'
        + '&location_id=8'
        + '&sort_by=snapshot_at'
        + '&sort_order=desc'
      ),
    ],
  )

  assert.equal(
    JSON.stringify(calls).includes('tenant_id'),
    false,
  )
})

test('inventory detail reads use exact frozen paths', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.getBalance(11)
  await api.getTransaction(12)
  await api.getReservation(13)
  await api.getTransfer(14)
  await api.getStocktake(15)

  assert.deepEqual(
    calls.map((call) => call.path),
    [
      '/v1/inventory/balances/11',
      '/v1/inventory/transactions/12',
      '/v1/inventory/reservations/13',
      '/v1/inventory/transfers/14',
      '/v1/inventory/stocktakes/15',
    ],
  )
})

test('balance reads preserve additive lot concurrency fields unchanged', async () => {
  const thawedBalance: InventoryBalanceRead = {
    ...balanceFixture,
    id: 11,
    lot_id: 71,
    version: 5,
    lot_version: 9,
    lot_is_frozen: false,
  }
  const frozenBalance: InventoryBalanceRead = {
    ...balanceFixture,
    id: 12,
    lot_id: 72,
    version: 6,
    lot_version: 10,
    lot_is_frozen: true,
  }
  const unavailableLotState: InventoryBalanceRead = {
    ...balanceFixture,
    id: 13,
    lot_id: 73,
    version: 7,
    lot_version: null,
    lot_is_frozen: null,
  }

  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(
    calls,
    (method, path) => {
      if (method !== 'GET') return {}
      if (path === '/v1/inventory/balances/13') {
        return unavailableLotState
      }
      if (path === '/v1/inventory/balances?page=1') {
        return {
          items: [thawedBalance, frozenBalance, unavailableLotState],
          page: 1,
          page_size: 20,
          total: 3,
          pages: 1,
        }
      }
      return {}
    },
  ))

  const detail = await api.getBalance(13)
  const page = await api.listBalances({ page: 1 })

  assert.deepEqual(
    {
      lot_version: detail.data.lot_version,
      lot_is_frozen: detail.data.lot_is_frozen,
    },
    {
      lot_version: null,
      lot_is_frozen: null,
    },
  )

  assert.deepEqual(
    page.data.items.map((item) => ({
      id: item.id,
      lot_version: item.lot_version,
      lot_is_frozen: item.lot_is_frozen,
    })),
    [
      { id: 11, lot_version: 9, lot_is_frozen: false },
      { id: 12, lot_version: 10, lot_is_frozen: true },
      { id: 13, lot_version: null, lot_is_frozen: null },
    ],
  )
})

test('lot concurrency fields remain response-only list fields', async () => {
  if (false) {
    const invalidLotVersionQuery: InventoryBalanceListQuery = {
      // @ts-expect-error lot_version is response-only
      lot_version: 9,
    }
    const invalidFrozenQuery: InventoryBalanceListQuery = {
      // @ts-expect-error lot_is_frozen is response-only
      lot_is_frozen: false,
    }
    const invalidLotVersionSort: InventoryBalanceListQuery = {
      // @ts-expect-error lot_version is not a balance sort key
      sort_by: 'lot_version',
    }
    void invalidLotVersionQuery
    void invalidFrozenQuery
    void invalidLotVersionSort
  }

  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.listBalances({
    page: 1,
    lot_version: 9,
    lot_is_frozen: true,
    tenant_id: 'forbidden-tenant',
  } as unknown as InventoryBalanceListQuery)

  assert.equal(
    calls[0]?.path,
    '/v1/inventory/balances?page=1',
  )
})

test('freeze and unfreeze preview require authoritative lot version', async () => {
  if (false) {
    // @ts-expect-error FREEZE requires expected_lot_version
    const missingLotVersion: InventoryOperationPreviewRequest = {
      operation_type: 'FREEZE',
      balance_id: 11,
      expected_balance_version: 5,
      reason: 'quality hold',
      deltas: null,
      lot_id: 71,
    }

    const nullLotVersion: InventoryOperationPreviewRequest = {
      operation_type: 'UNFREEZE',
      balance_id: 12,
      expected_balance_version: 6,
      reason: 'release hold',
      deltas: null,
      lot_id: 72,
      // @ts-expect-error UNFREEZE requires a non-null expected_lot_version
      expected_lot_version: null,
    }

    void missingLotVersion
    void nullLotVersion
  }

  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.previewOperation(freezeRequest, 'freeze-preview-key')

  assert.deepEqual(calls[0], {
    method: 'POST',
    path: '/v1/inventory/operations/preview',
    body: freezeRequest,
    headers: { 'Idempotency-Key': 'freeze-preview-key' },
  })
})

test('freeze and unfreeze reject non-positive lot versions before transport', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  for (const expectedLotVersion of [0, -1]) {
    const invalidRequest = {
      ...freezeRequest,
      expected_lot_version: expectedLotVersion,
    }

    await assert.rejects(
      api.previewOperation(
        invalidRequest,
        `invalid-lot-version-${expectedLotVersion}`,
      ),
      /expected_lot_version|lot version|positive/i,
    )
  }

  assert.equal(calls.length, 0)
})

test('all 23 inventory writes send an explicit Idempotency-Key', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.createReservation(reserveRequest, 'key-01')
  await api.issueReservation(101, issueRequest, 'key-02')
  await api.releaseReservation(101, releaseRequest, 'key-03')
  await api.returnReservation(101, returnRequest, 'key-04')
  await api.cancelReservation(101, expectedVersionRequest, 'key-05')

  await api.previewOperation(freezeRequest, 'key-06')
  await api.executeOperation(201, executeRequest, 'key-07')
  await api.previewReverse(201, reversePreviewRequest, 'key-08')
  await api.executeReverse(202, executeRequest, 'key-09')

  await api.createTransfer(transferCreateRequest, 'key-10')
  await api.previewTransferDispatch(301, expectedVersionRequest, 'key-11')
  await api.executeTransferDispatch(301, transferExecuteRequest, 'key-12')
  await api.previewTransferReceive(301, transferReceiveRequest, 'key-13')
  await api.executeTransferReceive(301, transferExecuteRequest, 'key-14')
  await api.cancelTransfer(301, expectedVersionRequest, 'key-15')

  await api.createStocktake(stocktakeCreateRequest, 'key-16')
  await api.startStocktake(401, expectedVersionRequest, 'key-17')
  await api.updateStocktakeLine(401, 402, stocktakeCountRequest, 'key-18')
  await api.reviewStocktake(401, expectedVersionRequest, 'key-19')
  await api.previewStocktakeConfirm(401, expectedVersionRequest, 'key-20')
  await api.executeStocktakeConfirm(
    401,
    stocktakeConfirmExecuteRequest,
    'key-21',
  )
  await api.rebaseStocktake(401, stocktakeRebaseRequest, 'key-22')
  await api.cancelStocktake(401, expectedVersionRequest, 'key-23')

  const expected = [
    ['POST', '/v1/inventory/reservations', 'key-01'],
    ['POST', '/v1/inventory/reservations/101/issue', 'key-02'],
    ['POST', '/v1/inventory/reservations/101/release', 'key-03'],
    ['POST', '/v1/inventory/reservations/101/return', 'key-04'],
    ['POST', '/v1/inventory/reservations/101/cancel', 'key-05'],
    ['POST', '/v1/inventory/operations/preview', 'key-06'],
    ['POST', '/v1/inventory/operations/201/execute', 'key-07'],
    ['POST', '/v1/inventory/operations/201/reverse/preview', 'key-08'],
    ['POST', '/v1/inventory/operations/202/reverse/execute', 'key-09'],
    ['POST', '/v1/inventory/transfers', 'key-10'],
    ['POST', '/v1/inventory/transfers/301/dispatch/preview', 'key-11'],
    ['POST', '/v1/inventory/transfers/301/dispatch/execute', 'key-12'],
    ['POST', '/v1/inventory/transfers/301/receive/preview', 'key-13'],
    ['POST', '/v1/inventory/transfers/301/receive/execute', 'key-14'],
    ['POST', '/v1/inventory/transfers/301/cancel', 'key-15'],
    ['POST', '/v1/inventory/stocktakes', 'key-16'],
    ['POST', '/v1/inventory/stocktakes/401/start', 'key-17'],
    ['PATCH', '/v1/inventory/stocktakes/401/lines/402', 'key-18'],
    ['POST', '/v1/inventory/stocktakes/401/review', 'key-19'],
    ['POST', '/v1/inventory/stocktakes/401/confirm/preview', 'key-20'],
    ['POST', '/v1/inventory/stocktakes/401/confirm/execute', 'key-21'],
    ['POST', '/v1/inventory/stocktakes/401/rebase', 'key-22'],
    ['POST', '/v1/inventory/stocktakes/401/cancel', 'key-23'],
  ] as const

  assert.equal(calls.length, 23)

  assert.deepEqual(
    calls.map((call) => [
      call.method,
      call.path,
      call.headers?.['Idempotency-Key'],
    ]),
    expected,
  )
})

test('stocktake line update uses PATCH rather than POST', async () => {
  const calls: CapturedCall[] = []
  const api = createInventoryApi(fakeClient(calls))

  await api.updateStocktakeLine(
    21,
    22,
    stocktakeCountRequest,
    'count-key',
  )

  assert.deepEqual(calls, [{
    method: 'PATCH',
    path: '/v1/inventory/stocktakes/21/lines/22',
    body: stocktakeCountRequest,
    headers: { 'Idempotency-Key': 'count-key' },
  }])
})

test('inventory quantities remain exact decimal strings', () => {
  const request: InventoryReserveRequest = {
    owner_type: 'WORK_ORDER',
    owner_id: 'WO-001',
    spare_part_id: 41,
    warehouse_id: 7,
    requested_quantity: '9007199254740993.1250',
    allow_partial: false,
    expected_balance_versions: { 91: 4 },
    as_of: '2026-08-16',
  }

  const serialized = JSON.stringify(request)

  assert.match(serialized, /9007199254740993\.1250/)
  assert.equal(
    JSON.parse(serialized).requested_quantity,
    '9007199254740993.1250',
  )
})
