import { defineStore } from 'pinia'
import { reactive } from 'vue'

import {
  createInventoryApi,
  type InventoryApi,
  type InventoryBalanceListQuery,
  type InventoryBalanceRead,
  type InventoryExpectedVersionRequest,
  type InventoryOperationExecuteRequest,
  type InventoryOperationPreviewRead,
  type InventoryOperationPreviewRequest,
  type InventoryPage,
  type InventoryReserveRequest,
  type InventoryReservationIssueRequest,
  type InventoryReservationListQuery,
  type InventoryReservationRead,
  type InventoryReservationReleaseRequest,
  type InventoryReservationReturnRequest,
  type InventoryStocktakeConfirmExecuteRequest,
  type InventoryStocktakeCountRequest,
  type InventoryStocktakeCreateRequest,
  type InventoryStocktakeListQuery,
  type InventoryStocktakeRead,
  type InventoryStocktakeRebaseRequest,
  type InventoryTransactionListQuery,
  type InventoryTransactionRead,
  type InventoryTransferCreateRequest,
  type InventoryTransferExecuteRequest,
  type InventoryTransferListQuery,
  type InventoryTransferRead,
  type InventoryTransferReceivePreviewRequest,
} from '../../api/maintenance/inventory'
import {
  normalizeMaintenanceError,
} from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
} from '../../api/maintenance/types'

export interface InventoryListSlice<
  T,
  Q extends object,
> {
  items: T[]
  query: Q
  page: number
  pageSize: number
  total: number
  pages: number
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

export interface InventoryDetailSlice<T> {
  item: T | null
  loading: boolean
  error: MaintenanceClientError | null
  generation: number
}

export type InventoryCommandKind =
  | 'reservation.create'
  | 'reservation.issue'
  | 'reservation.release'
  | 'reservation.return'
  | 'reservation.cancel'
  | 'operation.preview'
  | 'operation.execute'
  | 'transfer.create'
  | 'transfer.dispatch.preview'
  | 'transfer.dispatch.execute'
  | 'transfer.receive.preview'
  | 'transfer.receive.execute'
  | 'transfer.cancel'
  | 'stocktake.create'
  | 'stocktake.start'
  | 'stocktake.count'
  | 'stocktake.review'
  | 'stocktake.confirm.preview'
  | 'stocktake.confirm.execute'
  | 'stocktake.rebase'
  | 'stocktake.cancel'

export type InventoryPreviewKind =
  | 'operation.preview'
  | 'transfer.dispatch.preview'
  | 'transfer.receive.preview'
  | 'stocktake.confirm.preview'

export type InventoryCommandState =
  | { phase: 'idle' }
  | {
      phase: 'running'
      kind: InventoryCommandKind
      identity: string
    }
  | {
      phase: 'uncertain'
      kind: InventoryCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'conflicted'
      kind: InventoryCommandKind
      identity: string
      error: MaintenanceClientError
    }
  | {
      phase: 'previewed'
      kind: InventoryPreviewKind
      identity: string
      scope: number
      transactionId: number
      transactionVersion: number
      confirmationToken: string | null
      confirmationExpiresAt: string
    }
  | {
      phase: 'succeeded'
      kind: InventoryCommandKind
      identity: string
    }
  | {
      phase: 'failed'
      kind: InventoryCommandKind
      identity: string
      error: MaintenanceClientError
    }

interface CommandStateHolder {
  current: InventoryCommandState
}

function createListSlice<
  T,
  Q extends object,
>(): InventoryListSlice<T, Q> {
  return reactive({
    items: [] as T[],
    query: {} as Q,
    page: 1,
    pageSize: 20,
    total: 0,
    pages: 0,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as InventoryListSlice<T, Q>
}

function createDetailSlice<T>(): InventoryDetailSlice<T> {
  return reactive({
    item: null as T | null,
    loading: false,
    error: null as MaintenanceClientError | null,
    generation: 0,
  }) as InventoryDetailSlice<T>
}

function applyPage<T, Q extends object>(
  slice: InventoryListSlice<T, Q>,
  page: InventoryPage<T>,
): void {
  slice.items = page.items
  slice.page = page.page
  slice.pageSize = page.page_size
  slice.total = page.total
  slice.pages = page.pages
}

async function loadList<
  T,
  Q extends object,
>(
  slice: InventoryListSlice<T, Q>,
  query: Q,
  loader: (
    query: Q,
  ) => Promise<MaintenanceResult<InventoryPage<T>>>,
): Promise<void> {
  const generation = ++slice.generation
  slice.loading = true
  slice.error = null
  slice.query = { ...query }

  try {
    const response = await loader(query)
    if (generation !== slice.generation) return
    applyPage(slice, response.data)
  } catch (value) {
    if (generation === slice.generation) {
      slice.error = normalizeMaintenanceError(value)
    }
    throw value
  } finally {
    if (generation === slice.generation) {
      slice.loading = false
    }
  }
}

async function loadDetail<T>(
  slice: InventoryDetailSlice<T>,
  loader: () => Promise<MaintenanceResult<T>>,
): Promise<void> {
  const generation = ++slice.generation
  slice.loading = true
  slice.error = null

  try {
    const response = await loader()
    if (generation !== slice.generation) return
    slice.item = response.data
  } catch (value) {
    if (generation === slice.generation) {
      slice.error = normalizeMaintenanceError(value)
    }
    throw value
  } finally {
    if (generation === slice.generation) {
      slice.loading = false
    }
  }
}

const defaultInventoryApi = createInventoryApi()

export function createInventoryState(
  api: InventoryApi = defaultInventoryApi,
  createCommandKey: () => string = () =>
    globalThis.crypto?.randomUUID?.()
    ?? `inventory-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  now: () => Date = () => new Date(),
) {
  const balances = createListSlice<
    InventoryBalanceRead,
    InventoryBalanceListQuery
  >()
  const transactions = createListSlice<
    InventoryTransactionRead,
    InventoryTransactionListQuery
  >()
  const reservations = createListSlice<
    InventoryReservationRead,
    InventoryReservationListQuery
  >()
  const transfers = createListSlice<
    InventoryTransferRead,
    InventoryTransferListQuery
  >()
  const stocktakes = createListSlice<
    InventoryStocktakeRead,
    InventoryStocktakeListQuery
  >()

  const balanceDetail = createDetailSlice<InventoryBalanceRead>()
  const transactionDetail =
    createDetailSlice<InventoryTransactionRead>()
  const reservationDetail =
    createDetailSlice<InventoryReservationRead>()
  const transferDetail = createDetailSlice<InventoryTransferRead>()
  const stocktakeDetail = createDetailSlice<InventoryStocktakeRead>()

  const command = reactive<CommandStateHolder>({
    current: { phase: 'idle' },
  })
  const pendingCommandKeys = new Map<string, string>()

  function commandIdentity(
    kind: InventoryCommandKind,
    payload: unknown,
  ): string {
    return JSON.stringify([kind, payload])
  }

  function keyForIdentity(identity: string): string {
    const existing = pendingCommandKeys.get(identity)
    if (existing !== undefined) return existing
    const created = createCommandKey()
    pendingCommandKeys.set(identity, created)
    return created
  }

  function classifyCommandFailure(
    kind: InventoryCommandKind,
    identity: string,
    value: unknown,
  ): MaintenanceClientError {
    const error = normalizeMaintenanceError(value)
    if (error.status === 409) {
      pendingCommandKeys.delete(identity)
      command.current = {
        phase: 'conflicted',
        kind,
        identity,
        error,
      }
      return error
    }
    if (error.retryable) {
      command.current = {
        phase: 'uncertain',
        kind,
        identity,
        error,
      }
      return error
    }
    pendingCommandKeys.delete(identity)
    command.current = {
      phase: 'failed',
      kind,
      identity,
      error,
    }
    return error
  }

  async function runCommand<T>(
    kind: InventoryCommandKind,
    payload: unknown,
    operation: (idempotencyKey: string) => Promise<T>,
  ): Promise<T> {
    const identity = commandIdentity(kind, payload)
    const key = keyForIdentity(identity)
    command.current = { phase: 'running', kind, identity }
    try {
      const value = await operation(key)
      pendingCommandKeys.delete(identity)
      command.current = { phase: 'succeeded', kind, identity }
      return value
    } catch (value) {
      throw classifyCommandFailure(kind, identity, value)
    }
  }

  async function runPreview(
    kind: InventoryPreviewKind,
    scope: number,
    payload: unknown,
    operation: (
      idempotencyKey: string,
    ) => Promise<MaintenanceResult<InventoryOperationPreviewRead>>,
  ): Promise<InventoryOperationPreviewRead> {
    const identity = commandIdentity(kind, payload)
    const key = keyForIdentity(identity)
    command.current = { phase: 'running', kind, identity }
    try {
      const response = await operation(key)
      pendingCommandKeys.delete(identity)
      const preview = response.data
      command.current = {
        phase: 'previewed',
        kind,
        identity,
        scope,
        transactionId: preview.transaction_id,
        transactionVersion: preview.transaction_version,
        confirmationToken: preview.confirmation_token,
        confirmationExpiresAt: preview.confirmation_expires_at,
      }
      return preview
    } catch (value) {
      throw classifyCommandFailure(kind, identity, value)
    }
  }

  function currentPreview(
    kind?: InventoryPreviewKind,
  ): Extract<InventoryCommandState, { phase: 'previewed' }> {
    const current = command.current
    if (current.phase !== 'previewed') {
      throw new Error('Inventory preview is not executable')
    }
    if (kind !== undefined && current.kind !== kind) {
      throw new Error('Inventory preview kind does not match command')
    }
    if (
      current.confirmationToken === null
      || !Number.isFinite(Date.parse(current.confirmationExpiresAt))
      || now().getTime() >= Date.parse(current.confirmationExpiresAt)
    ) {
      throw new Error('Inventory preview is not executable')
    }
    return current
  }

  function previewExecutable(): boolean {
    const current = command.current
    if (
      current.phase !== 'previewed'
      || current.confirmationToken === null
    ) {
      return false
    }
    const expiresAt = Date.parse(current.confirmationExpiresAt)
    return Number.isFinite(expiresAt) && now().getTime() < expiresAt
  }

  function fetchBalances(
    query: InventoryBalanceListQuery = {},
  ): Promise<void> {
    return loadList(
      balances,
      query,
      (value) => api.listBalances(value),
    )
  }

  function fetchTransactions(
    query: InventoryTransactionListQuery = {},
  ): Promise<void> {
    return loadList(
      transactions,
      query,
      (value) => api.listTransactions(value),
    )
  }

  function fetchReservations(
    query: InventoryReservationListQuery = {},
  ): Promise<void> {
    return loadList(
      reservations,
      query,
      (value) => api.listReservations(value),
    )
  }

  function fetchTransfers(
    query: InventoryTransferListQuery = {},
  ): Promise<void> {
    return loadList(
      transfers,
      query,
      (value) => api.listTransfers(value),
    )
  }

  function fetchStocktakes(
    query: InventoryStocktakeListQuery = {},
  ): Promise<void> {
    return loadList(
      stocktakes,
      query,
      (value) => api.listStocktakes(value),
    )
  }

  function fetchBalanceDetail(id: number): Promise<void> {
    return loadDetail(
      balanceDetail,
      () => api.getBalance(id),
    )
  }

  function fetchTransactionDetail(id: number): Promise<void> {
    return loadDetail(
      transactionDetail,
      () => api.getTransaction(id),
    )
  }

  function fetchReservationDetail(id: number): Promise<void> {
    return loadDetail(
      reservationDetail,
      () => api.getReservation(id),
    )
  }

  function fetchTransferDetail(id: number): Promise<void> {
    return loadDetail(
      transferDetail,
      () => api.getTransfer(id),
    )
  }

  function fetchStocktakeDetail(id: number): Promise<void> {
    return loadDetail(
      stocktakeDetail,
      () => api.getStocktake(id),
    )
  }

  async function collectReservationBalanceVersions(
    query: InventoryBalanceListQuery = {},
  ): Promise<Record<number, number>> {
    const {
      page: _page,
      page_size: _pageSize,
      sort_by: _sortBy,
      sort_order: _sortOrder,
      ...filters
    } = query

    const versions: Record<number, number> = {}
    let page = 1
    let pages = 1

    do {
      const response = await api.listBalances({
        page,
        page_size: 100,
        ...filters,
        sort_by: 'id',
        sort_order: 'asc',
      })

      response.data.items.forEach((item) => {
        versions[item.id] = item.version
      })

      pages = response.data.pages
      page += 1
    } while (page <= pages)

    return versions
  }

  async function refreshReservationAggregate(
    value: InventoryReservationRead,
  ): Promise<void> {
    reservationDetail.item = value
    await fetchReservations({ ...reservations.query })
    await fetchBalances({ ...balances.query })
  }

  async function refreshTransferAggregate(
    value: InventoryTransferRead,
  ): Promise<void> {
    transferDetail.item = value
    await fetchTransfers({ ...transfers.query })
    await fetchBalances({ ...balances.query })
  }

  async function refreshStocktakeAggregate(
    value: InventoryStocktakeRead,
  ): Promise<void> {
    stocktakeDetail.item = value
    await fetchStocktakes({ ...stocktakes.query })
    await fetchBalances({ ...balances.query })
  }

  async function createReservation(
    request: InventoryReserveRequest,
  ): Promise<InventoryReservationRead> {
    const response = await runCommand(
      'reservation.create',
      request,
      (key) => api.createReservation(request, key),
    )
    await refreshReservationAggregate(response.data)
    return response.data
  }

  async function issueReservation(
    id: number,
    request: InventoryReservationIssueRequest,
  ): Promise<InventoryReservationRead> {
    const response = await runCommand(
      'reservation.issue',
      [id, request],
      (key) => api.issueReservation(id, request, key),
    )
    await refreshReservationAggregate(response.data)
    return response.data
  }

  async function releaseReservation(
    id: number,
    request: InventoryReservationReleaseRequest,
  ): Promise<InventoryReservationRead> {
    const response = await runCommand(
      'reservation.release',
      [id, request],
      (key) => api.releaseReservation(id, request, key),
    )
    await refreshReservationAggregate(response.data)
    return response.data
  }

  async function returnReservation(
    id: number,
    request: InventoryReservationReturnRequest,
  ): Promise<InventoryReservationRead> {
    const response = await runCommand(
      'reservation.return',
      [id, request],
      (key) => api.returnReservation(id, request, key),
    )
    await refreshReservationAggregate(response.data)
    return response.data
  }

  async function cancelReservation(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryReservationRead> {
    const response = await runCommand(
      'reservation.cancel',
      [id, request],
      (key) => api.cancelReservation(id, request, key),
    )
    await refreshReservationAggregate(response.data)
    return response.data
  }

  async function previewOperation(
    request: InventoryOperationPreviewRequest,
  ): Promise<InventoryOperationPreviewRead> {
    return runPreview(
      'operation.preview',
      request.balance_id,
      request,
      (key) => api.previewOperation(request, key),
    )
  }

  async function executeOperation(): Promise<InventoryTransactionRead> {
    const preview = currentPreview('operation.preview')
    const request: InventoryOperationExecuteRequest = {
      expected_transaction_version: preview.transactionVersion,
      confirmation_token: preview.confirmationToken as string,
    }
    const payload = [preview.transactionId, request]
    try {
      const response = await runCommand(
        'operation.execute',
        payload,
        (key) => api.executeOperation(
          preview.transactionId,
          request,
          key,
        ),
      )
      await fetchTransactionDetail(preview.transactionId)
      await fetchTransactions({ ...transactions.query })
      await fetchBalances({ ...balances.query })
      await fetchBalanceDetail(preview.scope)
      return response.data
    } catch (value) {
      if (command.current.phase === 'conflicted') {
        await fetchBalanceDetail(preview.scope)
      }
      throw value
    }
  }

  async function createTransfer(
    request: InventoryTransferCreateRequest,
  ): Promise<InventoryTransferRead> {
    const response = await runCommand(
      'transfer.create',
      request,
      (key) => api.createTransfer(request, key),
    )
    await refreshTransferAggregate(response.data)
    return response.data
  }

  function previewTransferDispatch(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryOperationPreviewRead> {
    return runPreview(
      'transfer.dispatch.preview',
      id,
      [id, request],
      (key) => api.previewTransferDispatch(id, request, key),
    )
  }

  async function executeTransferDispatch(): Promise<InventoryTransferRead> {
    const preview = currentPreview('transfer.dispatch.preview')
    const request: InventoryTransferExecuteRequest = {
      transaction_id: preview.transactionId,
      expected_transaction_version: preview.transactionVersion,
      confirmation_token: preview.confirmationToken as string,
    }
    const response = await runCommand(
      'transfer.dispatch.execute',
      [preview.scope, request],
      (key) => api.executeTransferDispatch(
        preview.scope,
        request,
        key,
      ),
    )
    await refreshTransferAggregate(response.data)
    return response.data
  }

  function previewTransferReceive(
    id: number,
    request: InventoryTransferReceivePreviewRequest,
  ): Promise<InventoryOperationPreviewRead> {
    return runPreview(
      'transfer.receive.preview',
      id,
      [id, request],
      (key) => api.previewTransferReceive(id, request, key),
    )
  }

  async function executeTransferReceive(): Promise<InventoryTransferRead> {
    const preview = currentPreview('transfer.receive.preview')
    const request: InventoryTransferExecuteRequest = {
      transaction_id: preview.transactionId,
      expected_transaction_version: preview.transactionVersion,
      confirmation_token: preview.confirmationToken as string,
    }
    const response = await runCommand(
      'transfer.receive.execute',
      [preview.scope, request],
      (key) => api.executeTransferReceive(
        preview.scope,
        request,
        key,
      ),
    )
    await refreshTransferAggregate(response.data)
    return response.data
  }

  async function cancelTransfer(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryTransferRead> {
    const response = await runCommand(
      'transfer.cancel',
      [id, request],
      (key) => api.cancelTransfer(id, request, key),
    )
    await refreshTransferAggregate(response.data)
    return response.data
  }

  async function createStocktake(
    request: InventoryStocktakeCreateRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.create',
      request,
      (key) => api.createStocktake(request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  async function startStocktake(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.start',
      [id, request],
      (key) => api.startStocktake(id, request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  async function updateStocktakeLine(
    id: number,
    lineId: number,
    request: InventoryStocktakeCountRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.count',
      [id, lineId, request],
      (key) => api.updateStocktakeLine(id, lineId, request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  async function reviewStocktake(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.review',
      [id, request],
      (key) => api.reviewStocktake(id, request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  function previewStocktakeConfirm(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryOperationPreviewRead> {
    return runPreview(
      'stocktake.confirm.preview',
      id,
      [id, request],
      (key) => api.previewStocktakeConfirm(id, request, key),
    )
  }

  async function executeStocktakeConfirm(): Promise<InventoryStocktakeRead> {
    const preview = currentPreview('stocktake.confirm.preview')
    const request: InventoryStocktakeConfirmExecuteRequest = {
      transaction_id: preview.transactionId,
      expected_transaction_version: preview.transactionVersion,
      confirmation_token: preview.confirmationToken as string,
    }
    const response = await runCommand(
      'stocktake.confirm.execute',
      [preview.scope, request],
      (key) => api.executeStocktakeConfirm(
        preview.scope,
        request,
        key,
      ),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  async function rebaseStocktake(
    id: number,
    request: InventoryStocktakeRebaseRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.rebase',
      [id, request],
      (key) => api.rebaseStocktake(id, request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  async function cancelStocktake(
    id: number,
    request: InventoryExpectedVersionRequest,
  ): Promise<InventoryStocktakeRead> {
    const response = await runCommand(
      'stocktake.cancel',
      [id, request],
      (key) => api.cancelStocktake(id, request, key),
    )
    await refreshStocktakeAggregate(response.data)
    return response.data
  }

  return {
    balances,
    transactions,
    reservations,
    transfers,
    stocktakes,
    balanceDetail,
    transactionDetail,
    reservationDetail,
    transferDetail,
    stocktakeDetail,
    fetchBalances,
    fetchTransactions,
    fetchReservations,
    fetchTransfers,
    fetchStocktakes,
    fetchBalanceDetail,
    fetchTransactionDetail,
    fetchReservationDetail,
    fetchTransferDetail,
    fetchStocktakeDetail,
    collectReservationBalanceVersions,
    get commandState() {
      return command.current
    },
    get canExecutePreview() {
      return previewExecutable()
    },
    createReservation,
    issueReservation,
    releaseReservation,
    returnReservation,
    cancelReservation,
    previewOperation,
    executeOperation,
    createTransfer,
    previewTransferDispatch,
    executeTransferDispatch,
    previewTransferReceive,
    executeTransferReceive,
    cancelTransfer,
    createStocktake,
    startStocktake,
    updateStocktakeLine,
    reviewStocktake,
    previewStocktakeConfirm,
    executeStocktakeConfirm,
    rebaseStocktake,
    cancelStocktake,
  }
}

export const useInventoryStore = defineStore(
  'maintenanceInventory',
  () => createInventoryState(),
)
