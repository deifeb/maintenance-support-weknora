import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  InventoryApi,
  InventoryBalanceListQuery,
  InventoryBalanceRead,
  InventoryLotStatePreviewRequest,
  InventoryOperationExecuteRequest,
  InventoryOperationPreviewRead,
  InventoryOperationPreviewRequest,
  InventoryPage,
  InventoryReserveRequest,
  InventoryReservationRead,
  InventoryStocktakeRead,
  InventoryTransactionRead,
  InventoryTransferRead,
} from '../../../api/maintenance/inventory.ts'
import type {
  MaintenanceResult,
} from '../../../api/maintenance/types.ts'
import {
  createInventoryState,
} from '../inventory.ts'

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'request-inventory-store',
      tenant_id: 'tenant-inventory-store',
    },
  }
}

function pageData<T>(
  items: T[],
  overrides: Partial<InventoryPage<T>> = {},
): InventoryPage<T> {
  return {
    items,
    page: 1,
    page_size: 20,
    total: items.length,
    pages: items.length === 0 ? 0 : 1,
    ...overrides,
  }
}

function balance(
  overrides: Partial<InventoryBalanceRead> = {},
): InventoryBalanceRead {
  return {
    id: 1,
    warehouse_id: 7,
    location_id: 3,
    spare_part_id: 41,
    lot_id: 71,
    serial_item_id: null,
    serial_item_ids: [],
    on_hand_quantity: '10.0000',
    reserved_quantity: '2.0000',
    damaged_quantity: '0.0000',
    quarantined_quantity: '0.0000',
    in_transit_quantity: '0.0000',
    available_quantity: '8.0000',
    version: 10,
    lot_version: 9,
    lot_is_frozen: false,
    ...overrides,
  }
}

function transaction(
  overrides: Partial<InventoryTransactionRead> = {},
): InventoryTransactionRead {
  return {
    id: 1,
    tenant_id: 'tenant-a',
    operation_type: 'ADJUST',
    status: 'COMPLETED',
    idempotency_key: 'key-transaction',
    request_hash: 'hash-transaction',
    reason: 'Task 11B fixture',
    actor_user_id: 'user-a',
    actor_roles: ['admin'],
    request_id: 'request-transaction',
    version: 4,
    completed_at: '2026-08-16T12:00:00Z',
    entries: [],
    ...overrides,
  }
}

function reservation(
  overrides: Partial<InventoryReservationRead> = {},
): InventoryReservationRead {
  return {
    id: 1,
    tenant_id: 'tenant-a',
    owner_type: 'maintenance_order',
    owner_id: 'MO-1',
    status: 'ACTIVE',
    expires_at: null,
    allow_partial: false,
    actor_user_id: 'user-a',
    actor_roles: ['contributor'],
    request_id: 'request-reservation',
    version: 3,
    requested_quantity: '5.0000',
    reserved_quantity: '5.0000',
    issued_quantity: '0.0000',
    released_quantity: '0.0000',
    unfilled_quantity: '0.0000',
    line_errors: [],
    lines: [],
    ...overrides,
  }
}

function transfer(
  overrides: Partial<InventoryTransferRead> = {},
): InventoryTransferRead {
  return {
    id: 1,
    tenant_id: 'tenant-a',
    status: 'DRAFT',
    source_warehouse_id: 7,
    source_location_id: 3,
    target_warehouse_id: 8,
    target_location_id: 4,
    reference_type: null,
    reference_id: null,
    reason: 'Task 11B fixture',
    actor_user_id: 'user-a',
    actor_roles: ['admin'],
    request_id: 'request-transfer',
    version: 2,
    dispatched_at: null,
    completed_at: null,
    cancelled_at: null,
    lines: [],
    ...overrides,
  }
}

function stocktake(
  overrides: Partial<InventoryStocktakeRead> = {},
): InventoryStocktakeRead {
  return {
    id: 1,
    tenant_id: 'tenant-a',
    warehouse_id: 7,
    location_id: 3,
    status: 'DRAFT',
    snapshot_at: '2026-08-16T12:00:00Z',
    actor_user_id: 'user-a',
    actor_roles: ['contributor'],
    request_id: 'request-stocktake',
    version: 2,
    confirmed_at: null,
    cancelled_at: null,
    lines: [],
    ...overrides,
  }
}

type DeferredValue<T> = {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason?: unknown) => void
}

function deferred<T>(): DeferredValue<T> {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return { promise, resolve, reject }
}

type ReadInventoryApi = Pick<
  InventoryApi,
  | 'listBalances'
  | 'getBalance'
  | 'listTransactions'
  | 'getTransaction'
  | 'listReservations'
  | 'getReservation'
  | 'listTransfers'
  | 'getTransfer'
  | 'listStocktakes'
  | 'getStocktake'
>

function readApiStub(
  overrides: Partial<ReadInventoryApi> = {},
): InventoryApi {
  const api: ReadInventoryApi = {
    async listBalances() {
      return result(pageData<InventoryBalanceRead>([]))
    },
    async getBalance(id) {
      return result(balance({ id }))
    },
    async listTransactions() {
      return result(pageData<InventoryTransactionRead>([]))
    },
    async getTransaction(id) {
      return result(transaction({ id }))
    },
    async listReservations() {
      return result(pageData<InventoryReservationRead>([]))
    },
    async getReservation(id) {
      return result(reservation({ id }))
    },
    async listTransfers() {
      return result(pageData<InventoryTransferRead>([]))
    },
    async getTransfer(id) {
      return result(transfer({ id }))
    },
    async listStocktakes() {
      return result(pageData<InventoryStocktakeRead>([]))
    },
    async getStocktake(id) {
      return result(stocktake({ id }))
    },
    ...overrides,
  }

  return api as InventoryApi
}

function controlledReadApi() {
  const balanceListCalls: Array<DeferredValue<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>> = []
  const transactionListCalls: Array<DeferredValue<MaintenanceResult<InventoryPage<InventoryTransactionRead>>>> = []
  const reservationListCalls: Array<DeferredValue<MaintenanceResult<InventoryPage<InventoryReservationRead>>>> = []
  const transferListCalls: Array<DeferredValue<MaintenanceResult<InventoryPage<InventoryTransferRead>>>> = []
  const stocktakeListCalls: Array<DeferredValue<MaintenanceResult<InventoryPage<InventoryStocktakeRead>>>> = []

  const balanceDetailCalls: Array<{
    id: number
    call: DeferredValue<MaintenanceResult<InventoryBalanceRead>>
  }> = []
  const reservationDetailCalls: Array<{
    id: number
    call: DeferredValue<MaintenanceResult<InventoryReservationRead>>
  }> = []

  const api = readApiStub({
    listBalances: async () => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>()
      balanceListCalls.push(call)
      return call.promise
    },
    listTransactions: async () => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryTransactionRead>>>()
      transactionListCalls.push(call)
      return call.promise
    },
    listReservations: async () => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryReservationRead>>>()
      reservationListCalls.push(call)
      return call.promise
    },
    listTransfers: async () => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryTransferRead>>>()
      transferListCalls.push(call)
      return call.promise
    },
    listStocktakes: async () => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryStocktakeRead>>>()
      stocktakeListCalls.push(call)
      return call.promise
    },
    getBalance: async (id) => {
      const call = deferred<MaintenanceResult<InventoryBalanceRead>>()
      balanceDetailCalls.push({ id, call })
      return call.promise
    },
    getReservation: async (id) => {
      const call = deferred<MaintenanceResult<InventoryReservationRead>>()
      reservationDetailCalls.push({ id, call })
      return call.promise
    },
  })

  return {
    api,
    balanceListCalls,
    transactionListCalls,
    reservationListCalls,
    transferListCalls,
    stocktakeListCalls,
    balanceDetailCalls,
    reservationDetailCalls,
  }
}

test('inventory list slices load independently', async () => {
  const controlled = controlledReadApi()
  const state = createInventoryState(controlled.api)

  const balances = state.fetchBalances()
  assert.equal(state.balances.loading, true)
  assert.equal(state.transactions.loading, false)
  assert.equal(state.reservations.loading, false)
  assert.equal(state.transfers.loading, false)
  assert.equal(state.stocktakes.loading, false)
  controlled.balanceListCalls[0]!.resolve(result(pageData(
    [balance({ id: 11 })],
    { page: 2, page_size: 10, total: 21, pages: 3 },
  )))
  await balances
  assert.equal(state.balances.loading, false)
  assert.deepEqual(state.balances.items.map((item) => item.id), [11])
  assert.equal(state.balances.page, 2)
  assert.equal(state.balances.pageSize, 10)
  assert.equal(state.balances.total, 21)
  assert.equal(state.balances.pages, 3)

  const transactions = state.fetchTransactions()
  assert.equal(state.balances.loading, false)
  assert.equal(state.transactions.loading, true)
  assert.equal(state.reservations.loading, false)
  assert.equal(state.transfers.loading, false)
  assert.equal(state.stocktakes.loading, false)
  controlled.transactionListCalls[0]!.resolve(result(pageData(
    [transaction({ id: 22 })],
  )))
  await transactions
  assert.deepEqual(state.transactions.items.map((item) => item.id), [22])
  assert.equal(state.transactions.loading, false)

  const reservations = state.fetchReservations()
  assert.equal(state.balances.loading, false)
  assert.equal(state.transactions.loading, false)
  assert.equal(state.reservations.loading, true)
  assert.equal(state.transfers.loading, false)
  assert.equal(state.stocktakes.loading, false)
  controlled.reservationListCalls[0]!.resolve(result(pageData(
    [reservation({ id: 33 })],
  )))
  await reservations
  assert.deepEqual(state.reservations.items.map((item) => item.id), [33])
  assert.equal(state.reservations.loading, false)

  const transfers = state.fetchTransfers()
  assert.equal(state.balances.loading, false)
  assert.equal(state.transactions.loading, false)
  assert.equal(state.reservations.loading, false)
  assert.equal(state.transfers.loading, true)
  assert.equal(state.stocktakes.loading, false)
  controlled.transferListCalls[0]!.resolve(result(pageData(
    [transfer({ id: 44 })],
  )))
  await transfers
  assert.deepEqual(state.transfers.items.map((item) => item.id), [44])
  assert.equal(state.transfers.loading, false)

  const stocktakes = state.fetchStocktakes()
  assert.equal(state.balances.loading, false)
  assert.equal(state.transactions.loading, false)
  assert.equal(state.reservations.loading, false)
  assert.equal(state.transfers.loading, false)
  assert.equal(state.stocktakes.loading, true)
  controlled.stocktakeListCalls[0]!.resolve(result(pageData(
    [stocktake({ id: 55 })],
  )))
  await stocktakes
  assert.deepEqual(state.stocktakes.items.map((item) => item.id), [55])
  assert.equal(state.stocktakes.loading, false)
})

test('older balance list response cannot overwrite newer query state', async () => {
  const calls: Array<{
    query: InventoryBalanceListQuery | undefined
    call: DeferredValue<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>
  }> = []
  const api = readApiStub({
    listBalances: async (query) => {
      const call = deferred<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>()
      calls.push({ query, call })
      return call.promise
    },
  })
  const state = createInventoryState(api)

  const oldRequest = state.fetchBalances({
    warehouse_id: 1,
    sort_by: 'id',
    sort_order: 'asc',
  })
  const newRequest = state.fetchBalances({
    warehouse_id: 2,
    sort_by: 'id',
    sort_order: 'asc',
  })

  calls[1]!.call.resolve(result(pageData([balance({ id: 200 })])))
  await newRequest
  calls[0]!.call.resolve(result(pageData([balance({ id: 100 })])))
  await oldRequest

  assert.deepEqual(state.balances.items.map((item) => item.id), [200])
  assert.equal(state.balances.query.warehouse_id, 2)
  assert.equal(state.balances.loading, false)
})

test('balance query is forwarded unchanged and server result order is preserved', async () => {
  const balanceQueries: Array<InventoryBalanceListQuery | undefined> = []
  const api = readApiStub({
    listBalances: async (query) => {
      balanceQueries.push(query)
      return result(pageData([
        balance({
          id: 900,
          warehouse_id: 99,
          spare_part_id: 999,
          available_quantity: '1.0000',
        }),
        balance({
          id: 100,
          warehouse_id: 7,
          spare_part_id: 41,
          available_quantity: '99.0000',
        }),
      ]))
    },
  })
  const state = createInventoryState(api)
  const query: InventoryBalanceListQuery = {
    warehouse_id: 7,
    spare_part_id: 41,
    page: 3,
    page_size: 20,
    sort_by: 'available_quantity',
    sort_order: 'desc',
  }

  await state.fetchBalances(query)

  assert.deepEqual(balanceQueries, [query])
  assert.deepEqual(state.balances.query, query)
  assert.deepEqual(
    state.balances.items.map((item) => item.id),
    [900, 100],
  )
})


test('all five inventory detail domains load into separate state', async () => {
  const state = createInventoryState(readApiStub())

  await Promise.all([
    state.fetchBalanceDetail(11),
    state.fetchTransactionDetail(22),
    state.fetchReservationDetail(33),
    state.fetchTransferDetail(44),
    state.fetchStocktakeDetail(55),
  ])

  assert.equal(state.balanceDetail.item?.id, 11)
  assert.equal(state.transactionDetail.item?.id, 22)
  assert.equal(state.reservationDetail.item?.id, 33)
  assert.equal(state.transferDetail.item?.id, 44)
  assert.equal(state.stocktakeDetail.item?.id, 55)
})

test('balance and reservation detail generations reject stale responses independently', async () => {
  const controlled = controlledReadApi()
  const state = createInventoryState(controlled.api)

  const oldBalance = state.fetchBalanceDetail(1)
  const oldReservation = state.fetchReservationDetail(1)
  const newBalance = state.fetchBalanceDetail(2)
  const newReservation = state.fetchReservationDetail(2)

  controlled.balanceDetailCalls[1]!.call.resolve(result(balance({ id: 2 })))
  controlled.reservationDetailCalls[1]!.call.resolve(result(reservation({ id: 2 })))
  await Promise.all([newBalance, newReservation])

  controlled.balanceDetailCalls[0]!.call.resolve(result(balance({ id: 1 })))
  controlled.reservationDetailCalls[0]!.call.resolve(result(reservation({ id: 1 })))
  await Promise.all([oldBalance, oldReservation])

  assert.equal(state.balanceDetail.item?.id, 2)
  assert.equal(state.reservationDetail.item?.id, 2)
  assert.equal(state.balanceDetail.loading, false)
  assert.equal(state.reservationDetail.loading, false)
})

test('balance list and detail preserve lot concurrency fields including null fail-closed state', async () => {
  let listed = balance({
    id: 11,
    lot_id: 71,
    version: 5,
    lot_version: 9,
    lot_is_frozen: false,
  })
  let detailed = balance({
    id: 11,
    lot_id: 71,
    version: 5,
    lot_version: 9,
    lot_is_frozen: false,
  })
  const api = readApiStub({
    listBalances: async () => result(pageData([listed])),
    getBalance: async () => result(detailed),
  })
  const state = createInventoryState(api)

  await state.fetchBalances()
  await state.fetchBalanceDetail(11)

  assert.equal(state.balances.items[0]!.lot_version, 9)
  assert.equal(state.balances.items[0]!.lot_is_frozen, false)
  assert.equal(state.balanceDetail.item?.lot_version, 9)
  assert.equal(state.balanceDetail.item?.lot_is_frozen, false)

  listed = balance({
    id: 12,
    lot_id: 72,
    version: 6,
    lot_version: null,
    lot_is_frozen: null,
  })
  detailed = balance({
    id: 12,
    lot_id: 72,
    version: 6,
    lot_version: null,
    lot_is_frozen: null,
  })

  await state.fetchBalances()
  await state.fetchBalanceDetail(12)

  assert.equal(state.balances.items[0]!.lot_version, null)
  assert.equal(state.balances.items[0]!.lot_is_frozen, null)
  assert.equal(state.balanceDetail.item?.lot_version, null)
  assert.equal(state.balanceDetail.item?.lot_is_frozen, null)
})

test('collects reservation balance versions across all server pages', async () => {
  const balanceQueries: InventoryBalanceListQuery[] = []
  const firstPage = pageData(
    Array.from({ length: 100 }, (_, index) =>
      balance({ id: index + 1, version: index + 10 })),
    { page: 1, page_size: 100, pages: 2, total: 101 },
  )
  const secondPage = pageData(
    [balance({ id: 101, version: 777 })],
    { page: 2, page_size: 100, pages: 2, total: 101 },
  )
  const api = readApiStub({
    listBalances: async (query = {}) => {
      balanceQueries.push({ ...query })
      return result(query.page === 2 ? secondPage : firstPage)
    },
  })
  const state = createInventoryState(api)

  const versions = await state.collectReservationBalanceVersions({
    warehouse_id: 7,
    spare_part_id: 41,
    location_id: 3,
  })

  assert.equal(Object.keys(versions).length, 101)
  assert.equal(versions[1], 10)
  assert.equal(versions[101], 777)
  assert.deepEqual(balanceQueries, [
    {
      page: 1,
      page_size: 100,
      warehouse_id: 7,
      spare_part_id: 41,
      location_id: 3,
      sort_by: 'id',
      sort_order: 'asc',
    },
    {
      page: 2,
      page_size: 100,
      warehouse_id: 7,
      spare_part_id: 41,
      location_id: 3,
      sort_by: 'id',
      sort_order: 'asc',
    },
  ])
})
function previewResult(
  overrides: Partial<InventoryOperationPreviewRead> = {},
): InventoryOperationPreviewRead {
  return {
    transaction_id: 301,
    operation_type: 'ADJUST',
    status: 'PREVIEWED',
    transaction_version: 7,
    confirmation_token: 'confirm-301',
    confirmation_expires_at: '2026-08-16T12:30:00Z',
    ...overrides,
  }
}

function reservationCommand(
  requestedQuantity: string = '5.0000',
): InventoryReserveRequest {
  return {
    owner_type: 'maintenance_order',
    owner_id: 'MO-11C',
    spare_part_id: 41,
    warehouse_id: 7,
    requested_quantity: requestedQuantity,
    allow_partial: false,
    expected_balance_versions: { 11: 5 },
    as_of: '2026-08-16T12:00:00Z',
    location_id: 3,
    lot_id: 71,
    serial_item_id: null,
    expires_at: null,
    fefo_override_reason: null,
  }
}

function adjustPreviewCommand(): InventoryOperationPreviewRequest {
  return {
    operation_type: 'ADJUST',
    balance_id: 11,
    expected_balance_version: 5,
    reason: 'Task 11C adjustment',
    deltas: {
      on_hand: '1.0000',
      reserved: '0.0000',
      damaged: '0.0000',
      quarantined: '0.0000',
      in_transit: '0.0000',
    },
  }
}

function freezePreviewCommand(
  overrides: Partial<InventoryLotStatePreviewRequest> = {},
): InventoryLotStatePreviewRequest {
  return {
    operation_type: 'FREEZE',
    balance_id: 11,
    expected_balance_version: 5,
    reason: 'Task 11C freeze',
    deltas: null,
    lot_id: 71,
    expected_lot_version: 9,
    ...overrides,
  }
}

function keyFactory(
  ...keys: string[]
): () => string {
  let index = 0
  return () => keys[index++] ?? `unexpected-key-${index}`
}

function writeApiStub(
  overrides: Partial<InventoryApi> = {},
): InventoryApi {
  const base = readApiStub()

  return {
    ...base,
    async createReservation(request) {
      return result(reservation({
        requested_quantity: request.requested_quantity,
      }))
    },
    async issueReservation(id) {
      return result(reservation({ id, status: 'PARTIALLY_ISSUED' }))
    },
    async releaseReservation(id) {
      return result(reservation({ id, status: 'RELEASED' }))
    },
    async returnReservation(id) {
      return result(reservation({ id, status: 'PARTIALLY_ISSUED' }))
    },
    async cancelReservation(id) {
      return result(reservation({ id, status: 'CANCELLED' }))
    },
    async previewOperation() {
      return result(previewResult())
    },
    async executeOperation(transactionId) {
      return result(transaction({ id: transactionId, version: 8 }))
    },
    async previewReverse(transactionId) {
      return result(previewResult({
        transaction_id: transactionId + 1000,
        operation_type: 'REVERSE',
      }))
    },
    async executeReverse(transactionId) {
      return result(transaction({
        id: transactionId,
        operation_type: 'REVERSE',
        version: 8,
      }))
    },
    async createTransfer() {
      return result(transfer())
    },
    async previewTransferDispatch() {
      return result(previewResult({
        transaction_id: 801,
        operation_type: 'TRANSFER_DISPATCH',
      }))
    },
    async executeTransferDispatch(transferId) {
      return result(transfer({
        id: transferId,
        status: 'DISPATCHED',
        version: 3,
      }))
    },
    async previewTransferReceive() {
      return result(previewResult({
        transaction_id: 802,
        operation_type: 'TRANSFER_RECEIVE',
      }))
    },
    async executeTransferReceive(transferId) {
      return result(transfer({
        id: transferId,
        status: 'COMPLETED',
        version: 4,
      }))
    },
    async cancelTransfer(transferId) {
      return result(transfer({
        id: transferId,
        status: 'CANCELLED',
      }))
    },
    async createStocktake() {
      return result(stocktake())
    },
    async startStocktake(stocktakeId) {
      return result(stocktake({
        id: stocktakeId,
        status: 'COUNTING',
        version: 3,
      }))
    },
    async updateStocktakeLine(stocktakeId) {
      return result(stocktake({ id: stocktakeId, version: 4 }))
    },
    async reviewStocktake(stocktakeId) {
      return result(stocktake({
        id: stocktakeId,
        status: 'REVIEWING',
        version: 5,
      }))
    },
    async previewStocktakeConfirm() {
      return result(previewResult({
        transaction_id: 901,
        operation_type: 'STOCKTAKE_CONFIRM',
      }))
    },
    async executeStocktakeConfirm(stocktakeId) {
      return result(stocktake({
        id: stocktakeId,
        status: 'CONFIRMED',
        version: 6,
        confirmed_at: '2026-08-16T12:20:00Z',
      }))
    },
    async rebaseStocktake(stocktakeId) {
      return result(stocktake({ id: stocktakeId, version: 7 }))
    },
    async cancelStocktake(stocktakeId) {
      return result(stocktake({
        id: stocktakeId,
        status: 'CANCELLED',
        version: 8,
      }))
    },
    ...overrides,
  }
}

async function waitFor(
  predicate: () => boolean,
  message: string,
): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (predicate()) return
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
  }
  throw new Error(message)
}

const retryableInventoryFailure = {
  code: 'MAINTENANCE_CLIENT_ERROR',
  message: 'network',
  retryable: true,
}

const reservationConflict = {
  status: 409,
  code: 'RESERVATION_STATE_CONFLICT',
  message: 'conflict',
  retryable: false,
  details: {
    expected_version: 3,
    actual_version: 4,
    suggested_action: 'reload_reservation',
  },
}

const lotVersionConflict = {
  status: 409,
  code: 'INVENTORY_OPERATION_STATE_CONFLICT',
  message: 'lot changed',
  retryable: false,
  details: {
    conflict_object: 'inventory_lot',
    expected_version: 9,
    actual_version: 10,
    suggested_action: 'reload inventory state and preview again',
  },
}

test('uncertain reservation create reuses the same idempotency key for the same logical identity', async () => {
  const calls: Array<{
    request: InventoryReserveRequest
    key: string
  }> = []
  let attempt = 0
  const api = writeApiStub({
    createReservation: async (request, key) => {
      calls.push({ request, key })
      attempt += 1
      if (attempt === 1) throw retryableInventoryFailure
      return result(reservation({ id: 61 }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('uuid-1', 'uuid-2'),
  )
  const command = reservationCommand('5.0000')

  await assert.rejects(() => state.createReservation(command))

  assert.equal(state.commandState.phase, 'uncertain')
  assert.equal(calls[0]!.key, 'uuid-1')
  const firstIdentity = state.commandState.phase === 'uncertain'
    ? state.commandState.identity
    : ''

  await state.createReservation(command)

  assert.equal(calls[1]!.key, 'uuid-1')
  assert.deepEqual(calls[1]!.request, command)
  assert.notEqual(firstIdentity, '')
  assert.equal(state.commandState.phase, 'succeeded')
})

test('changed reservation payload after uncertain failure starts a new logical command key', async () => {
  const keys: string[] = []
  let attempt = 0
  const api = writeApiStub({
    createReservation: async (_request, key) => {
      keys.push(key)
      attempt += 1
      if (attempt === 1) throw retryableInventoryFailure
      return result(reservation({ id: 62 }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('uuid-1', 'uuid-2', 'uuid-3'),
  )

  await assert.rejects(() =>
    state.createReservation(reservationCommand('5.0000')))
  await state.createReservation(reservationCommand('6.0000'))

  assert.deepEqual(keys, ['uuid-1', 'uuid-2'])
})

test('definite conflict retains identity but corrected payload uses a fresh UUID', async () => {
  const keys: string[] = []
  let attempt = 0
  const api = writeApiStub({
    createReservation: async (_request, key) => {
      keys.push(key)
      attempt += 1
      if (attempt === 1) throw reservationConflict
      return result(reservation({ id: 63 }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('uuid-1', 'uuid-2', 'uuid-3'),
  )

  await assert.rejects(() =>
    state.createReservation(reservationCommand('5.0000')))

  assert.equal(state.commandState.phase, 'conflicted')
  assert.equal(
    state.commandState.phase === 'conflicted'
      ? state.commandState.kind
      : '',
    'reservation.create',
  )
  const conflictedIdentity = state.commandState.phase === 'conflicted'
    ? state.commandState.identity
    : ''
  assert.notEqual(conflictedIdentity, '')

  await state.createReservation(reservationCommand('6.0000'))

  assert.deepEqual(keys, ['uuid-1', 'uuid-2'])
  assert.equal(state.commandState.phase, 'succeeded')
})

test('preview and execute are separate logical writes and execute uses only stored preview authority', async () => {
  const previewCalls: Array<{
    request: InventoryOperationPreviewRequest
    key: string
  }> = []
  const executeCalls: Array<{
    transactionId: number
    request: InventoryOperationExecuteRequest
    key: string
  }> = []
  const api = writeApiStub({
    previewOperation: async (request, key) => {
      previewCalls.push({ request, key })
      return result(previewResult({
        transaction_id: 301,
        transaction_version: 7,
        confirmation_token: 'confirm-301',
      }))
    },
    executeOperation: async (transactionId, request, key) => {
      executeCalls.push({ transactionId, request, key })
      return result(transaction({ id: transactionId, version: 8 }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('preview-key', 'execute-key'),
    () => new Date('2026-08-16T12:00:00Z'),
  )

  await state.previewOperation(adjustPreviewCommand())

  assert.equal(state.commandState.phase, 'previewed')
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.scope
      : 0,
    11,
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.transactionId
      : 0,
    301,
  )

  await state.executeOperation()

  assert.equal(previewCalls[0]!.key, 'preview-key')
  assert.equal(executeCalls[0]!.key, 'execute-key')
  assert.notEqual(previewCalls[0]!.key, executeCalls[0]!.key)
  assert.equal(executeCalls[0]!.transactionId, 301)
  assert.deepEqual(executeCalls[0]!.request, {
    expected_transaction_version: 7,
    confirmation_token: 'confirm-301',
  })
})

test('expired preview is locally non-executable without consuming a new write key', async () => {
  const generatedKeys: string[] = []
  const executeCalls: unknown[] = []
  const createUuid = () => {
    const value = `uuid-${generatedKeys.length + 1}`
    generatedKeys.push(value)
    return value
  }
  const api = writeApiStub({
    previewOperation: async () => result(previewResult({
      confirmation_expires_at: '2026-08-16T11:59:59Z',
    })),
    executeOperation: async (...args) => {
      executeCalls.push(args)
      return result(transaction())
    },
  })
  const state = createInventoryState(
    api,
    createUuid,
    () => new Date('2026-08-16T12:00:00Z'),
  )

  await state.previewOperation(adjustPreviewCommand())

  assert.equal(state.canExecutePreview, false)
  assert.equal(generatedKeys.length, 1)
  await assert.rejects(() => state.executeOperation())
  assert.equal(generatedKeys.length, 1)
  assert.equal(executeCalls.length, 0)
})

test('FREEZE execute waits for authoritative refresh and never optimistically toggles lot state', async () => {
  const initial = balance({
    id: 11,
    version: 5,
    lot_version: 9,
    lot_is_frozen: false,
  })
  const refreshed = balance({
    id: 11,
    version: 6,
    lot_version: 10,
    lot_is_frozen: true,
  })
  const refreshedDetail = deferred<MaintenanceResult<InventoryBalanceRead>>()
  const order: string[] = []
  let detailRead = 0
  const api = writeApiStub({
    getBalance: async (id) => {
      detailRead += 1
      if (detailRead === 1) return result(initial)
      order.push(`fetchBalanceDetail:${id}`)
      return refreshedDetail.promise
    },
    previewOperation: async () => result(previewResult({
      transaction_id: 401,
      operation_type: 'FREEZE',
      transaction_version: 7,
      confirmation_token: 'freeze-token',
    })),
    executeOperation: async (transactionId) => {
      order.push('executeOperation')
      return result(transaction({
        id: transactionId,
        operation_type: 'FREEZE',
        version: 8,
      }))
    },
    getTransaction: async (id) => {
      order.push(`fetchTransactionDetail:${id}`)
      return result(transaction({
        id,
        operation_type: 'FREEZE',
        version: 8,
      }))
    },
    listTransactions: async () => {
      order.push('fetchTransactions')
      return result(pageData([transaction({
        id: 401,
        operation_type: 'FREEZE',
        version: 8,
      })]))
    },
    listBalances: async () => {
      order.push('fetchBalances')
      return result(pageData([refreshed]))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('freeze-preview', 'freeze-execute'),
    () => new Date('2026-08-16T12:00:00Z'),
  )

  await state.fetchBalanceDetail(11)
  await state.previewOperation(freezePreviewCommand())
  order.length = 0

  const executing = state.executeOperation()
  await waitFor(
    () => order.includes('fetchBalanceDetail:11'),
    'authoritative balance detail refresh did not start',
  )

  assert.deepEqual(order, [
    'executeOperation',
    'fetchTransactionDetail:401',
    'fetchTransactions',
    'fetchBalances',
    'fetchBalanceDetail:11',
  ])
  assert.equal(state.balanceDetail.item?.version, 5)
  assert.equal(state.balanceDetail.item?.lot_version, 9)
  assert.equal(state.balanceDetail.item?.lot_is_frozen, false)

  refreshedDetail.resolve(result(refreshed))
  await executing

  assert.equal(state.balanceDetail.item?.version, 6)
  assert.equal(state.balanceDetail.item?.lot_version, 10)
  assert.equal(state.balanceDetail.item?.lot_is_frozen, true)
})

test('lot version conflict retires preview, reloads authority, and requires a fresh preview key and versions', async () => {
  const previewCalls: Array<{
    request: InventoryOperationPreviewRequest
    key: string
  }> = []
  const executeCalls: string[] = []
  let detailRead = 0
  let executeAttempt = 0
  const api = writeApiStub({
    getBalance: async (id) => {
      detailRead += 1
      return result(balance({
        id,
        version: detailRead === 1 ? 5 : 6,
        lot_version: detailRead === 1 ? 9 : 10,
        lot_is_frozen: false,
      }))
    },
    previewOperation: async (request, key) => {
      previewCalls.push({ request, key })
      return result(previewResult({
        transaction_id: previewCalls.length === 1 ? 501 : 502,
        operation_type: 'FREEZE',
        transaction_version: previewCalls.length === 1 ? 7 : 8,
        confirmation_token: previewCalls.length === 1
          ? 'stale-token'
          : 'fresh-token',
      }))
    },
    executeOperation: async (_transactionId, _request, key) => {
      executeCalls.push(key)
      executeAttempt += 1
      if (executeAttempt === 1) throw lotVersionConflict
      return result(transaction({ id: 502, operation_type: 'FREEZE' }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('preview-1', 'execute-1', 'preview-2', 'execute-2'),
    () => new Date('2026-08-16T12:00:00Z'),
  )

  await state.fetchBalanceDetail(11)
  await state.previewOperation(freezePreviewCommand())
  await assert.rejects(() => state.executeOperation())

  assert.equal(state.commandState.phase, 'conflicted')
  assert.equal(state.canExecutePreview, false)
  assert.equal(detailRead, 2)
  assert.equal(state.balanceDetail.item?.version, 6)
  assert.equal(state.balanceDetail.item?.lot_version, 10)
  assert.equal(executeCalls.length, 1)

  await state.previewOperation(freezePreviewCommand({
    expected_balance_version: 6,
    expected_lot_version: 10,
  }))

  assert.equal(previewCalls.length, 2)
  assert.equal(previewCalls[0]!.key, 'preview-1')
  assert.equal(previewCalls[1]!.key, 'preview-2')
  assert.equal(
    'expected_lot_version' in previewCalls[1]!.request
      ? previewCalls[1]!.request.expected_lot_version
      : null,
    10,
  )
  assert.equal(
    previewCalls[1]!.request.expected_balance_version,
    6,
  )
  assert.equal(executeCalls.length, 1)
})

test('reservation commands map to typed API methods and refresh aggregate, list, and balances', async () => {
  const writes: string[] = []
  const refreshes: string[] = []
  const api = writeApiStub({
    createReservation: async (_request, key) => {
      writes.push(`create:${key}`)
      return result(reservation({ id: 71, version: 3 }))
    },
    issueReservation: async (id, request, key) => {
      writes.push(`issue:${id}:${request.expected_version}:${key}`)
      return result(reservation({
        id,
        status: 'PARTIALLY_ISSUED',
        version: 4,
      }))
    },
    releaseReservation: async (id, request, key) => {
      writes.push(`release:${id}:${request.expected_version}:${key}`)
      return result(reservation({ id, status: 'RELEASED', version: 5 }))
    },
    returnReservation: async (id, request, key) => {
      writes.push(`return:${id}:${request.expected_version}:${key}`)
      return result(reservation({
        id,
        status: 'PARTIALLY_ISSUED',
        version: 6,
      }))
    },
    cancelReservation: async (id, request, key) => {
      writes.push(`cancel:${id}:${request.expected_version}:${key}`)
      return result(reservation({ id, status: 'CANCELLED', version: 7 }))
    },
    listReservations: async () => {
      refreshes.push('reservations')
      return result(pageData([]))
    },
    listBalances: async () => {
      refreshes.push('balances')
      return result(pageData([]))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('r1', 'r2', 'r3', 'r4', 'r5'),
  )

  await state.createReservation(reservationCommand())
  await state.issueReservation(71, {
    expected_version: 3,
    lines: [{ reservation_line_id: 1, quantity: '1.0000' }],
  })
  await state.releaseReservation(71, {
    expected_version: 4,
    lines: [{ reservation_line_id: 1, quantity: '1.0000' }],
  })
  await state.returnReservation(71, {
    expected_version: 5,
    lines: [{
      reservation_line_id: 1,
      issue_transaction_id: 1001,
      quantity: '1.0000',
    }],
  })
  await state.cancelReservation(71, { expected_version: 6 })

  assert.deepEqual(writes, [
    'create:r1',
    'issue:71:3:r2',
    'release:71:4:r3',
    'return:71:5:r4',
    'cancel:71:6:r5',
  ])
  assert.equal(state.reservationDetail.item?.id, 71)
  assert.equal(state.reservationDetail.item?.status, 'CANCELLED')
  assert.equal(refreshes.filter((value) => value === 'reservations').length, 5)
  assert.equal(refreshes.filter((value) => value === 'balances').length, 5)
})

test('transfer and stocktake commands map to typed APIs, preserve preview metadata, and refresh authoritative aggregates', async () => {
  const writes: string[] = []
  const refreshes: string[] = []
  const api = writeApiStub({
    createTransfer: async (_request, key) => {
      writes.push(`transfer.create:${key}`)
      return result(transfer({ id: 81, version: 2 }))
    },
    previewTransferDispatch: async (id, request, key) => {
      writes.push(`transfer.dispatch.preview:${id}:${request.expected_version}:${key}`)
      return result(previewResult({
        transaction_id: 811,
        operation_type: 'TRANSFER_DISPATCH',
        transaction_version: 3,
        confirmation_token: 'dispatch-token',
      }))
    },
    executeTransferDispatch: async (id, request, key) => {
      writes.push(`transfer.dispatch.execute:${id}:${request.transaction_id}:${key}`)
      assert.equal(request.expected_transaction_version, 3)
      assert.equal(request.confirmation_token, 'dispatch-token')
      return result(transfer({ id, status: 'DISPATCHED', version: 3 }))
    },
    previewTransferReceive: async (id, request, key) => {
      writes.push(`transfer.receive.preview:${id}:${request.expected_version}:${key}`)
      return result(previewResult({
        transaction_id: 812,
        operation_type: 'TRANSFER_RECEIVE',
        transaction_version: 4,
        confirmation_token: 'receive-token',
      }))
    },
    executeTransferReceive: async (id, request, key) => {
      writes.push(`transfer.receive.execute:${id}:${request.transaction_id}:${key}`)
      return result(transfer({ id, status: 'COMPLETED', version: 4 }))
    },
    cancelTransfer: async (id, request, key) => {
      writes.push(`transfer.cancel:${id}:${request.expected_version}:${key}`)
      return result(transfer({ id, status: 'CANCELLED', version: 5 }))
    },
    createStocktake: async (_request, key) => {
      writes.push(`stocktake.create:${key}`)
      return result(stocktake({ id: 91, version: 2 }))
    },
    startStocktake: async (id, request, key) => {
      writes.push(`stocktake.start:${id}:${request.expected_version}:${key}`)
      return result(stocktake({ id, status: 'COUNTING', version: 3 }))
    },
    updateStocktakeLine: async (id, lineId, request, key) => {
      writes.push(`stocktake.count:${id}:${lineId}:${request.counted_quantity}:${key}`)
      return result(stocktake({ id, status: 'COUNTING', version: 4 }))
    },
    reviewStocktake: async (id, request, key) => {
      writes.push(`stocktake.review:${id}:${request.expected_version}:${key}`)
      return result(stocktake({ id, status: 'REVIEWING', version: 5 }))
    },
    previewStocktakeConfirm: async (id, request, key) => {
      writes.push(`stocktake.confirm.preview:${id}:${request.expected_version}:${key}`)
      return result(previewResult({
        transaction_id: 911,
        operation_type: 'STOCKTAKE_CONFIRM',
        transaction_version: 6,
        confirmation_token: 'stocktake-token',
      }))
    },
    executeStocktakeConfirm: async (id, request, key) => {
      writes.push(`stocktake.confirm.execute:${id}:${request.transaction_id}:${key}`)
      assert.equal(request.expected_transaction_version, 6)
      assert.equal(request.confirmation_token, 'stocktake-token')
      return result(stocktake({
        id,
        status: 'CONFIRMED',
        version: 6,
        confirmed_at: '2026-08-16T12:25:00Z',
      }))
    },
    rebaseStocktake: async (id, request, key) => {
      writes.push(`stocktake.rebase:${id}:${request.expected_version}:${key}`)
      return result(stocktake({ id, status: 'COUNTING', version: 7 }))
    },
    cancelStocktake: async (id, request, key) => {
      writes.push(`stocktake.cancel:${id}:${request.expected_version}:${key}`)
      return result(stocktake({ id, status: 'CANCELLED', version: 8 }))
    },
    listTransfers: async () => {
      refreshes.push('transfers')
      return result(pageData([]))
    },
    listStocktakes: async () => {
      refreshes.push('stocktakes')
      return result(pageData([]))
    },
    listBalances: async () => {
      refreshes.push('balances')
      return result(pageData([]))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory(
      't1', 't2', 't3', 't4', 't5', 't6',
      's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8',
    ),
    () => new Date('2026-08-16T12:00:00Z'),
  )

  await state.createTransfer({
    source_warehouse_id: 7,
    source_location_id: 3,
    target_warehouse_id: 8,
    target_location_id: 4,
    reason: 'Task 11C transfer',
    lines: [{
      spare_part_id: 41,
      source_balance_id: 11,
      quantity: '2.0000',
      expected_source_version: 5,
    }],
  })
  await state.previewTransferDispatch(81, { expected_version: 2 })
  assert.equal(state.commandState.phase, 'previewed')
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.scope
      : 0,
    81,
  )
  await state.executeTransferDispatch()
  await state.previewTransferReceive(81, {
    expected_version: 3,
    lines: [{ transfer_line_id: 1, quantity: '2.0000' }],
  })
  await state.executeTransferReceive()
  await state.cancelTransfer(81, { expected_version: 4 })

  await state.createStocktake({ warehouse_id: 7, location_id: 3 })
  await state.startStocktake(91, { expected_version: 2 })
  await state.updateStocktakeLine(91, 901, {
    expected_version: 3,
    expected_line_version: 1,
    counted_quantity: '9.5000',
  })
  await state.reviewStocktake(91, { expected_version: 4 })
  await state.previewStocktakeConfirm(91, { expected_version: 5 })
  assert.equal(state.commandState.phase, 'previewed')
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.scope
      : 0,
    91,
  )
  await state.executeStocktakeConfirm()
  await state.rebaseStocktake(91, {
    expected_version: 6,
    lines: [{ line_id: 901, action: 'RECOUNT' }],
  })
  await state.cancelStocktake(91, { expected_version: 7 })

  assert.deepEqual(writes, [
    'transfer.create:t1',
    'transfer.dispatch.preview:81:2:t2',
    'transfer.dispatch.execute:81:811:t3',
    'transfer.receive.preview:81:3:t4',
    'transfer.receive.execute:81:812:t5',
    'transfer.cancel:81:4:t6',
    'stocktake.create:s1',
    'stocktake.start:91:2:s2',
    'stocktake.count:91:901:9.5000:s3',
    'stocktake.review:91:4:s4',
    'stocktake.confirm.preview:91:5:s5',
    'stocktake.confirm.execute:91:911:s6',
    'stocktake.rebase:91:6:s7',
    'stocktake.cancel:91:7:s8',
  ])
  assert.equal(state.transferDetail.item?.id, 81)
  assert.equal(state.transferDetail.item?.status, 'CANCELLED')
  assert.equal(state.stocktakeDetail.item?.id, 91)
  assert.equal(state.stocktakeDetail.item?.status, 'CANCELLED')
  assert.ok(refreshes.includes('transfers'))
  assert.ok(refreshes.includes('stocktakes'))
  assert.ok(refreshes.includes('balances'))
})
type ReversePreviewCommand = {
  expected_transaction_version: number
  reason: string
}

type ReverseStoreContract = {
  previewReverse: (
    transactionId: number,
    request: ReversePreviewCommand,
  ) => Promise<InventoryOperationPreviewRead>
  executeReverse: () => Promise<InventoryTransactionRead>
}

function requireReverseStoreMethod<
  K extends keyof ReverseStoreContract,
>(
  state: ReturnType<typeof createInventoryState>,
  method: K,
): ReverseStoreContract[K] {
  const candidate = (
    state as unknown as Partial<ReverseStoreContract>
  )[method]
  assert.equal(
    typeof candidate,
    'function',
    `inventory Store is missing ${String(method)}()`,
  )
  return candidate as ReverseStoreContract[K]
}

test('reverse preview maps to typed API and stores source transaction scope with backend preview metadata', async () => {
  const previewCalls: Array<{
    transactionId: number
    request: ReversePreviewCommand
    key: string
  }> = []
  const api = writeApiStub({
    previewReverse: async (transactionId, request, key) => {
      previewCalls.push({ transactionId, request, key })
      return result(previewResult({
        transaction_id: 701,
        operation_type: 'REVERSE',
        transaction_version: 7,
        confirmation_token: 'reverse-token-701',
        confirmation_expires_at: '2026-08-16T12:05:00Z',
      }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('reverse-preview-key'),
    () => new Date('2026-08-16T12:00:00Z'),
  )
  const previewReverse = requireReverseStoreMethod(
    state,
    'previewReverse',
  )

  const command = {
    expected_transaction_version: 4,
    reason: 'Reverse incorrect issue',
  }
  await previewReverse(51, command)

  assert.deepEqual(previewCalls, [{
    transactionId: 51,
    request: command,
    key: 'reverse-preview-key',
  }])
  assert.equal(state.commandState.phase, 'previewed')
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.kind
      : '',
    'operation.reverse.preview',
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.scope
      : 0,
    51,
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.transactionId
      : 0,
    701,
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.transactionVersion
      : 0,
    7,
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.confirmationToken
      : '',
    'reverse-token-701',
  )
})

test('reverse execute accepts no caller authority and consumes stored preview with a distinct key', async () => {
  const executeCalls: Array<{
    transactionId: number
    request: InventoryOperationExecuteRequest
    key: string
  }> = []
  const refreshes: string[] = []
  const api = writeApiStub({
    previewReverse: async () => result(previewResult({
      transaction_id: 711,
      operation_type: 'REVERSE',
      transaction_version: 9,
      confirmation_token: 'reverse-token-711',
      confirmation_expires_at: '2026-08-16T12:05:00Z',
    })),
    executeReverse: async (transactionId, request, key) => {
      executeCalls.push({ transactionId, request, key })
      return result(transaction({
        id: 712,
        operation_type: 'REVERSE',
        version: 10,
      }))
    },
    getTransaction: async (id) => {
      refreshes.push(`detail:${id}`)
      return result(transaction({
        id,
        status: 'REVERSED',
        version: 5,
      }))
    },
    listTransactions: async () => {
      refreshes.push('list')
      return result(pageData([]))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory('reverse-preview-key', 'reverse-execute-key'),
    () => new Date('2026-08-16T12:00:00Z'),
  )

  const executeReverse = requireReverseStoreMethod(
    state,
    'executeReverse',
  )
  assert.equal(
    executeReverse.length,
    0,
    'executeReverse() must not accept caller token or transaction authority',
  )
  const previewReverse = requireReverseStoreMethod(
    state,
    'previewReverse',
  )

  await previewReverse(61, {
    expected_transaction_version: 4,
    reason: 'Reverse source transaction 61',
  })
  await executeReverse()

  assert.deepEqual(executeCalls, [{
    transactionId: 61,
    request: {
      expected_transaction_version: 9,
      confirmation_token: 'reverse-token-711',
    },
    key: 'reverse-execute-key',
  }])
  assert.notEqual(
    'reverse-preview-key',
    executeCalls[0]!.key,
  )
  assert.deepEqual(refreshes, ['detail:61', 'list'])
})

test('reverse preview with null or expired token fails closed without consuming an execute key', async () => {
  for (const previewOverride of [
    {
      confirmation_token: null,
      confirmation_expires_at: '2026-08-16T12:05:00Z',
    },
    {
      confirmation_token: 'expired-reverse-token',
      confirmation_expires_at: '2026-08-16T11:59:59Z',
    },
  ]) {
    const generatedKeys: string[] = []
    const executeCalls: unknown[] = []
    const api = writeApiStub({
      previewReverse: async () => result(previewResult({
        transaction_id: 721,
        operation_type: 'REVERSE',
        transaction_version: 8,
        ...previewOverride,
      })),
      executeReverse: async (...args) => {
        executeCalls.push(args)
        return result(transaction({
          id: 722,
          operation_type: 'REVERSE',
        }))
      },
    })
    const state = createInventoryState(
      api,
      () => {
        const key = `reverse-key-${generatedKeys.length + 1}`
        generatedKeys.push(key)
        return key
      },
      () => new Date('2026-08-16T12:00:00Z'),
    )
    const previewReverse = requireReverseStoreMethod(
      state,
      'previewReverse',
    )
    const executeReverse = requireReverseStoreMethod(
      state,
      'executeReverse',
    )

    await previewReverse(71, {
      expected_transaction_version: 4,
      reason: 'Reverse with guarded preview',
    })

    assert.equal(state.canExecutePreview, false)
    assert.equal(generatedKeys.length, 1)
    await assert.rejects(() => executeReverse())
    assert.equal(generatedKeys.length, 1)
    assert.equal(executeCalls.length, 0)
  }
})

test('reverse execute conflict retires stale preview, reloads source transaction, and requires a fresh preview key', async () => {
  const previewCalls: Array<{
    transactionId: number
    request: ReversePreviewCommand
    key: string
  }> = []
  const executeCalls: string[] = []
  const detailReads: number[] = []
  let executeAttempt = 0
  const reverseConflict = {
    status: 409,
    code: 'INVENTORY_OPERATION_STATE_CONFLICT',
    message: 'source transaction changed',
    retryable: false,
    details: {
      conflict_object: 'inventory_transaction',
      expected_version: 4,
      actual_version: 5,
      suggested_action: 'reload source transaction and preview again',
    },
  }
  const api = writeApiStub({
    previewReverse: async (transactionId, request, key) => {
      previewCalls.push({ transactionId, request, key })
      return result(previewResult({
        transaction_id: previewCalls.length === 1 ? 731 : 732,
        operation_type: 'REVERSE',
        transaction_version: previewCalls.length === 1 ? 8 : 9,
        confirmation_token: previewCalls.length === 1
          ? 'stale-reverse-token'
          : 'fresh-reverse-token',
        confirmation_expires_at: '2026-08-16T12:05:00Z',
      }))
    },
    executeReverse: async (_transactionId, _request, key) => {
      executeCalls.push(key)
      executeAttempt += 1
      if (executeAttempt === 1) throw reverseConflict
      return result(transaction({
        id: 733,
        operation_type: 'REVERSE',
      }))
    },
    getTransaction: async (id) => {
      detailReads.push(id)
      return result(transaction({
        id,
        version: 5,
      }))
    },
  })
  const state = createInventoryState(
    api,
    keyFactory(
      'reverse-preview-1',
      'reverse-execute-1',
      'reverse-preview-2',
      'reverse-execute-2',
    ),
    () => new Date('2026-08-16T12:00:00Z'),
  )
  const previewReverse = requireReverseStoreMethod(
    state,
    'previewReverse',
  )
  const executeReverse = requireReverseStoreMethod(
    state,
    'executeReverse',
  )

  await previewReverse(81, {
    expected_transaction_version: 4,
    reason: 'Initial reverse',
  })
  await assert.rejects(() => executeReverse())

  assert.equal(state.commandState.phase, 'conflicted')
  assert.equal(state.canExecutePreview, false)
  assert.deepEqual(detailReads, [81])
  assert.equal(state.transactionDetail.item?.id, 81)
  assert.equal(state.transactionDetail.item?.version, 5)
  assert.deepEqual(executeCalls, ['reverse-execute-1'])

  await previewReverse(81, {
    expected_transaction_version: 5,
    reason: 'Corrected reverse after reload',
  })

  assert.equal(previewCalls.length, 2)
  assert.equal(previewCalls[0]!.key, 'reverse-preview-1')
  assert.equal(previewCalls[1]!.key, 'reverse-preview-2')
  assert.equal(
    previewCalls[1]!.request.expected_transaction_version,
    5,
  )
  assert.equal(
    state.commandState.phase === 'previewed'
      ? state.commandState.scope
      : 0,
    81,
  )
  assert.equal(executeCalls.length, 1)
})
