import {
  buildQuery,
  maintenanceGet,
  maintenancePost,
  normalizeMaintenanceError,
  unwrapMaintenanceResponse,
} from './client'
import type {
  MaintenanceResponse,
  MaintenanceResult,
} from './types'

export type DecimalString = string

export type InventoryOperationType =
  | 'OPENING'
  | 'ADJUST'
  | 'RESERVE'
  | 'UNRESERVE'
  | 'ISSUE'
  | 'RETURN'
  | 'TRANSFER_DISPATCH'
  | 'TRANSFER_RECEIVE'
  | 'FREEZE'
  | 'UNFREEZE'
  | 'REVERSE'
  | 'STOCKTAKE_CONFIRM'

export type InventoryTransactionStatus =
  | 'PREVIEWED'
  | 'COMPLETED'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'EXPIRED'
  | 'REVERSED'

export type InventoryReservationStatus =
  | 'ACTIVE'
  | 'PARTIALLY_ISSUED'
  | 'FULFILLED'
  | 'RELEASED'
  | 'CANCELLED'
  | 'EXPIRED'

export type InventoryTransferStatus =
  | 'DRAFT'
  | 'DISPATCHED'
  | 'PARTIALLY_RECEIVED'
  | 'COMPLETED'
  | 'CANCELLED'

export type InventoryStocktakeStatus =
  | 'DRAFT'
  | 'COUNTING'
  | 'REVIEWING'
  | 'CONFIRMED'
  | 'CONFLICTED'
  | 'CANCELLED'

export type InventorySortOrder = 'asc' | 'desc'

export interface InventoryBalanceRead {
  id: number
  warehouse_id: number
  location_id: number
  spare_part_id: number
  lot_id: number | null
  serial_item_id: number | null
  serial_item_ids: number[]
  on_hand_quantity: DecimalString
  reserved_quantity: DecimalString
  damaged_quantity: DecimalString
  quarantined_quantity: DecimalString
  in_transit_quantity: DecimalString
  available_quantity: DecimalString
  version: number
  lot_version: number | null
  lot_is_frozen: boolean | null
}

export interface InventoryLedgerEntryRead {
  id: number
  balance_id: number
  spare_part_id: number
  warehouse_id: number
  location_id: number
  lot_id: number | null
  serial_item_id: number | null
  on_hand_delta: DecimalString
  reserved_delta: DecimalString
  damaged_delta: DecimalString
  quarantined_delta: DecimalString
  in_transit_delta: DecimalString
  state_before_json: Record<string, unknown>
  state_after_json: Record<string, unknown>
  before_balance_version: number
  resulting_balance_version: number
  created_at: string
}

export interface InventoryTransactionRead {
  id: number
  tenant_id: string
  operation_type: InventoryOperationType
  status: InventoryTransactionStatus
  idempotency_key: string
  request_hash: string
  reason: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  completed_at: string | null
  entries: InventoryLedgerEntryRead[]
}

export interface InventoryReservationLineRead {
  id: number
  reservation_id: number
  spare_part_id: number
  balance_id: number
  lot_id: number | null
  serial_item_id: number | null
  requested_quantity: DecimalString
  reserved_quantity: DecimalString
  issued_quantity: DecimalString
  released_quantity: DecimalString
  expected_balance_version: number
  fefo_rank: number
  fefo_override_reason: string | null
  version: number
}

export interface InventoryReservationRead {
  id: number
  tenant_id: string
  owner_type: string
  owner_id: string
  status: InventoryReservationStatus
  expires_at: string | null
  allow_partial: boolean
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  requested_quantity: DecimalString
  reserved_quantity: DecimalString
  issued_quantity: DecimalString
  released_quantity: DecimalString
  unfilled_quantity: DecimalString
  line_errors: string[]
  lines: InventoryReservationLineRead[]
}

export interface InventoryQuantityDeltaRequest {
  on_hand: DecimalString
  reserved: DecimalString
  damaged: DecimalString
  quarantined: DecimalString
  in_transit: DecimalString
}

export interface InventoryAdjustPreviewRequest {
  operation_type: 'ADJUST'
  balance_id: number
  expected_balance_version: number
  reason: string
  deltas: InventoryQuantityDeltaRequest
  lot_id?: never
  expected_lot_version?: never
}

export interface InventoryLotStatePreviewRequest {
  operation_type: 'FREEZE' | 'UNFREEZE'
  balance_id: number
  expected_balance_version: number
  reason: string
  deltas: null
  lot_id: number
  expected_lot_version: number
}

export type InventoryOperationPreviewRequest =
  | InventoryAdjustPreviewRequest
  | InventoryLotStatePreviewRequest

export interface InventoryOperationPreviewRead {
  transaction_id: number
  operation_type: InventoryOperationType
  status: 'PREVIEWED'
  transaction_version: number
  confirmation_token: string | null
  confirmation_expires_at: string
}

export interface InventoryBalanceListQuery {
  page?: number
  page_size?: number
  warehouse_id?: number
  spare_part_id?: number
  location_id?: number
  lot_id?: number
  serial_item_id?: number
  sort_by?:
    | 'id'
    | 'warehouse_id'
    | 'spare_part_id'
    | 'location_id'
    | 'lot_id'
    | 'on_hand_quantity'
    | 'reserved_quantity'
    | 'available_quantity'
  sort_order?: InventorySortOrder
}

export interface InventoryTransactionListQuery {
  page?: number
  page_size?: number
  operation_type?: InventoryOperationType
  status?: InventoryTransactionStatus
  reference_type?: string
  reference_id?: string
  sort_by?: 'id' | 'operation_type' | 'status' | 'completed_at'
  sort_order?: InventorySortOrder
}

export interface InventoryReservationListQuery {
  page?: number
  page_size?: number
  status?: InventoryReservationStatus
  owner_type?: string
  owner_id?: string
  sort_by?: 'id' | 'status' | 'expires_at'
  sort_order?: InventorySortOrder
}

export interface InventoryTransferListQuery {
  page?: number
  page_size?: number
  status?: InventoryTransferStatus
  source_warehouse_id?: number
  source_location_id?: number
  target_warehouse_id?: number
  target_location_id?: number
  reference_type?: string
  reference_id?: string
  sort_by?: 'id' | 'status' | 'dispatched_at' | 'completed_at'
  sort_order?: InventorySortOrder
}

export interface InventoryStocktakeListQuery {
  page?: number
  page_size?: number
  status?: InventoryStocktakeStatus
  warehouse_id?: number
  location_id?: number
  sort_by?: 'id' | 'status' | 'snapshot_at' | 'confirmed_at'
  sort_order?: InventorySortOrder
}

export interface InventoryPage<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface InventoryApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
  patch<T>(
    path: string,
    body: unknown,
    config?: unknown,
  ): Promise<MaintenanceResult<T>>
}

export interface InventoryReserveRequest {
  owner_type: string
  owner_id: string
  spare_part_id: number
  warehouse_id: number
  requested_quantity: DecimalString
  allow_partial: boolean
  expected_balance_versions: Record<number, number>
  as_of: string
  location_id?: number | null
  lot_id?: number | null
  serial_item_id?: number | null
  expires_at?: string | null
  fefo_override_reason?: string | null
}

export interface InventoryReservationQuantityLineRequest {
  reservation_line_id: number
  quantity: DecimalString
}

export interface InventoryReservationReturnLineRequest
  extends InventoryReservationQuantityLineRequest {
  issue_transaction_id: number
}

export interface InventoryReservationIssueRequest {
  expected_version: number
  lines: InventoryReservationQuantityLineRequest[]
}

export interface InventoryReservationReleaseRequest {
  expected_version: number
  lines: InventoryReservationQuantityLineRequest[]
}

export interface InventoryReservationReturnRequest {
  expected_version: number
  lines: InventoryReservationReturnLineRequest[]
}

export interface InventoryExpectedVersionRequest {
  expected_version: number
}

export interface InventoryOperationExecuteRequest {
  expected_transaction_version: number
  confirmation_token: string
}

export interface InventoryReversePreviewRequest {
  expected_transaction_version: number
  reason: string
}

export interface InventoryTransferCreateLineRequest {
  spare_part_id: number
  source_balance_id: number
  lot_id?: number | null
  serial_item_id?: number | null
  quantity: DecimalString
  expected_source_version: number
}

export interface InventoryTransferCreateRequest {
  source_warehouse_id: number
  source_location_id: number
  target_warehouse_id: number
  target_location_id: number
  reference_type?: string | null
  reference_id?: string | null
  reason: string
  lines: InventoryTransferCreateLineRequest[]
}

export interface InventoryTransferExecuteRequest {
  transaction_id: number
  expected_transaction_version: number
  confirmation_token: string
}

export interface InventoryTransferReceiveLineRequest {
  transfer_line_id: number
  quantity: DecimalString
}

export interface InventoryTransferReceivePreviewRequest {
  expected_version: number
  lines: InventoryTransferReceiveLineRequest[]
}

export interface InventoryTransferLineRead {
  id: number
  transfer_id: number
  spare_part_id: number
  source_balance_id: number
  target_balance_id: number
  lot_id: number | null
  serial_item_id: number | null
  requested_quantity: DecimalString
  dispatched_quantity: DecimalString
  received_quantity: DecimalString
  expected_source_version: number
  expected_target_version: number
  version: number
}

export interface InventoryTransferRead {
  id: number
  tenant_id: string
  status: InventoryTransferStatus
  source_warehouse_id: number
  source_location_id: number
  target_warehouse_id: number
  target_location_id: number
  reference_type: string | null
  reference_id: string | null
  reason: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  dispatched_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  lines: InventoryTransferLineRead[]
}

export interface InventoryStocktakeLineRead {
  id: number
  stocktake_id: number
  balance_id: number
  spare_part_id: number
  lot_id: number | null
  serial_item_id: number | null
  system_quantity: DecimalString
  counted_quantity: DecimalString | null
  variance_quantity: DecimalString | null
  snapshot_balance_version: number
  confirmed_transaction_id: number | null
  resolution: string
  conflict_details: Record<string, unknown> | null
  version: number
}

export interface InventoryStocktakeRead {
  id: number
  tenant_id: string
  warehouse_id: number
  location_id: number
  status: InventoryStocktakeStatus
  snapshot_at: string
  actor_user_id: string
  actor_roles: string[]
  request_id: string
  version: number
  confirmed_at: string | null
  cancelled_at: string | null
  lines: InventoryStocktakeLineRead[]
}

export interface InventoryStocktakeCreateRequest {
  warehouse_id: number
  location_id: number
}

export interface InventoryStocktakeCountRequest {
  expected_version: number
  expected_line_version: number
  counted_quantity: DecimalString
}

export interface InventoryStocktakeConfirmExecuteRequest {
  transaction_id: number
  expected_transaction_version: number
  confirmation_token: string
}

export type InventoryStocktakeRebaseAction =
  | 'RECOUNT'
  | 'BASELINE_ACCEPT'

export interface InventoryStocktakeRebaseLineRequest {
  line_id: number
  action: InventoryStocktakeRebaseAction
}

export interface InventoryStocktakeRebaseRequest {
  expected_version: number
  lines: InventoryStocktakeRebaseLineRequest[]
}

export interface InventoryApi {
  listBalances(
    query?: InventoryBalanceListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryBalanceRead>>>
  getBalance(
    id: number,
  ): Promise<MaintenanceResult<InventoryBalanceRead>>

  listTransactions(
    query?: InventoryTransactionListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryTransactionRead>>>
  getTransaction(
    id: number,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>

  listReservations(
    query?: InventoryReservationListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryReservationRead>>>
  getReservation(
    id: number,
  ): Promise<MaintenanceResult<InventoryReservationRead>>

  listTransfers(
    query?: InventoryTransferListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryTransferRead>>>
  getTransfer(
    id: number,
  ): Promise<MaintenanceResult<InventoryTransferRead>>

  listStocktakes(
    query?: InventoryStocktakeListQuery,
  ): Promise<MaintenanceResult<InventoryPage<InventoryStocktakeRead>>>
  getStocktake(
    id: number,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>

  createReservation(
    request: InventoryReserveRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  issueReservation(
    id: number,
    request: InventoryReservationIssueRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  releaseReservation(
    id: number,
    request: InventoryReservationReleaseRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  returnReservation(
    id: number,
    request: InventoryReservationReturnRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>
  cancelReservation(
    id: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryReservationRead>>

  previewOperation(
    request: InventoryOperationPreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeOperation(
    transactionId: number,
    request: InventoryOperationExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>
  previewReverse(
    transactionId: number,
    request: InventoryReversePreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeReverse(
    transactionId: number,
    request: InventoryOperationExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransactionRead>>

  createTransfer(
    request: InventoryTransferCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  previewTransferDispatch(
    transferId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeTransferDispatch(
    transferId: number,
    request: InventoryTransferExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  previewTransferReceive(
    transferId: number,
    request: InventoryTransferReceivePreviewRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeTransferReceive(
    transferId: number,
    request: InventoryTransferExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>
  cancelTransfer(
    transferId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryTransferRead>>

  createStocktake(
    request: InventoryStocktakeCreateRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  startStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  updateStocktakeLine(
    stocktakeId: number,
    lineId: number,
    request: InventoryStocktakeCountRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  reviewStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  previewStocktakeConfirm(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryOperationPreviewRead>>
  executeStocktakeConfirm(
    stocktakeId: number,
    request: InventoryStocktakeConfirmExecuteRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  rebaseStocktake(
    stocktakeId: number,
    request: InventoryStocktakeRebaseRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
  cancelStocktake(
    stocktakeId: number,
    request: InventoryExpectedVersionRequest,
    idempotencyKey: string,
  ): Promise<MaintenanceResult<InventoryStocktakeRead>>
}

function listPath(
  base: string,
  values: Record<string, string | number | undefined>,
): string {
  const query = buildQuery(values)
  return query ? `${base}?${query}` : base
}

function idempotencyConfig(idempotencyKey: string): {
  headers: Record<string, string>
} {
  if (idempotencyKey.trim().length === 0) {
    throw new Error('Idempotency-Key must be non-empty')
  }

  return {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  }
}

function validateOperationPreviewRequest(
  request: InventoryOperationPreviewRequest,
): void {
  if (
    request.operation_type !== 'FREEZE'
    && request.operation_type !== 'UNFREEZE'
  ) {
    return
  }

  if (
    !Number.isInteger(request.expected_lot_version)
    || request.expected_lot_version <= 0
  ) {
    throw new Error('expected_lot_version must be a positive integer')
  }
}

async function inventoryPatch<T>(
  path: string,
  body: unknown,
  config?: unknown,
): Promise<MaintenanceResult<T>> {
  try {
    const { patch: requestPatch } = await import('@/utils/request')
    const response = await requestPatch<MaintenanceResponse<T>>(
      `/api/maintenance${path}`,
      body as object,
      config,
    )
    return unwrapMaintenanceResponse(response)
  } catch (error) {
    throw normalizeMaintenanceError(error)
  }
}

const defaultInventoryClient: InventoryApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  patch: inventoryPatch,
}

export function createInventoryApi(
  client: InventoryApiClient = defaultInventoryClient,
): InventoryApi {
  return {
    listBalances(query = {}) {
      return client.get<InventoryPage<InventoryBalanceRead>>(
        listPath('/v1/inventory/balances', {
          page: query.page,
          page_size: query.page_size,
          warehouse_id: query.warehouse_id,
          spare_part_id: query.spare_part_id,
          location_id: query.location_id,
          lot_id: query.lot_id,
          serial_item_id: query.serial_item_id,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        }),
      )
    },
    getBalance(id) {
      return client.get<InventoryBalanceRead>(
        `/v1/inventory/balances/${id}`,
      )
    },
    listTransactions(query = {}) {
      return client.get<InventoryPage<InventoryTransactionRead>>(
        listPath('/v1/inventory/transactions', {
          page: query.page,
          page_size: query.page_size,
          operation_type: query.operation_type,
          status: query.status,
          reference_type: query.reference_type,
          reference_id: query.reference_id,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        }),
      )
    },
    getTransaction(id) {
      return client.get<InventoryTransactionRead>(
        `/v1/inventory/transactions/${id}`,
      )
    },
    listReservations(query = {}) {
      return client.get<InventoryPage<InventoryReservationRead>>(
        listPath('/v1/inventory/reservations', {
          page: query.page,
          page_size: query.page_size,
          status: query.status,
          owner_type: query.owner_type,
          owner_id: query.owner_id,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        }),
      )
    },
    getReservation(id) {
      return client.get<InventoryReservationRead>(
        `/v1/inventory/reservations/${id}`,
      )
    },
    listTransfers(query = {}) {
      return client.get<InventoryPage<InventoryTransferRead>>(
        listPath('/v1/inventory/transfers', {
          page: query.page,
          page_size: query.page_size,
          status: query.status,
          source_warehouse_id: query.source_warehouse_id,
          source_location_id: query.source_location_id,
          target_warehouse_id: query.target_warehouse_id,
          target_location_id: query.target_location_id,
          reference_type: query.reference_type,
          reference_id: query.reference_id,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        }),
      )
    },
    getTransfer(id) {
      return client.get<InventoryTransferRead>(
        `/v1/inventory/transfers/${id}`,
      )
    },
    listStocktakes(query = {}) {
      return client.get<InventoryPage<InventoryStocktakeRead>>(
        listPath('/v1/inventory/stocktakes', {
          page: query.page,
          page_size: query.page_size,
          status: query.status,
          warehouse_id: query.warehouse_id,
          location_id: query.location_id,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        }),
      )
    },
    getStocktake(id) {
      return client.get<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${id}`,
      )
    },
    createReservation(request, idempotencyKey) {
      return client.post<InventoryReservationRead>(
        '/v1/inventory/reservations',
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    issueReservation(id, request, idempotencyKey) {
      return client.post<InventoryReservationRead>(
        `/v1/inventory/reservations/${id}/issue`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    releaseReservation(id, request, idempotencyKey) {
      return client.post<InventoryReservationRead>(
        `/v1/inventory/reservations/${id}/release`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    returnReservation(id, request, idempotencyKey) {
      return client.post<InventoryReservationRead>(
        `/v1/inventory/reservations/${id}/return`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    cancelReservation(id, request, idempotencyKey) {
      return client.post<InventoryReservationRead>(
        `/v1/inventory/reservations/${id}/cancel`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    async previewOperation(request, idempotencyKey) {
      validateOperationPreviewRequest(request)
      return client.post<InventoryOperationPreviewRead>(
        '/v1/inventory/operations/preview',
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    executeOperation(transactionId, request, idempotencyKey) {
      return client.post<InventoryTransactionRead>(
        `/v1/inventory/operations/${transactionId}/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    previewReverse(transactionId, request, idempotencyKey) {
      return client.post<InventoryOperationPreviewRead>(
        `/v1/inventory/operations/${transactionId}/reverse/preview`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    executeReverse(transactionId, request, idempotencyKey) {
      return client.post<InventoryTransactionRead>(
        `/v1/inventory/operations/${transactionId}/reverse/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    createTransfer(request, idempotencyKey) {
      return client.post<InventoryTransferRead>(
        '/v1/inventory/transfers',
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    previewTransferDispatch(transferId, request, idempotencyKey) {
      return client.post<InventoryOperationPreviewRead>(
        `/v1/inventory/transfers/${transferId}/dispatch/preview`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    executeTransferDispatch(transferId, request, idempotencyKey) {
      return client.post<InventoryTransferRead>(
        `/v1/inventory/transfers/${transferId}/dispatch/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    previewTransferReceive(transferId, request, idempotencyKey) {
      return client.post<InventoryOperationPreviewRead>(
        `/v1/inventory/transfers/${transferId}/receive/preview`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    executeTransferReceive(transferId, request, idempotencyKey) {
      return client.post<InventoryTransferRead>(
        `/v1/inventory/transfers/${transferId}/receive/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    cancelTransfer(transferId, request, idempotencyKey) {
      return client.post<InventoryTransferRead>(
        `/v1/inventory/transfers/${transferId}/cancel`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    createStocktake(request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        '/v1/inventory/stocktakes',
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    startStocktake(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/start`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    updateStocktakeLine(
      stocktakeId,
      lineId,
      request,
      idempotencyKey,
    ) {
      return client.patch<InventoryStocktakeRead>(
        (
          `/v1/inventory/stocktakes/${stocktakeId}`
          + `/lines/${lineId}`
        ),
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    reviewStocktake(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/review`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    previewStocktakeConfirm(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryOperationPreviewRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/confirm/preview`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    executeStocktakeConfirm(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/confirm/execute`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    rebaseStocktake(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/rebase`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
    cancelStocktake(stocktakeId, request, idempotencyKey) {
      return client.post<InventoryStocktakeRead>(
        `/v1/inventory/stocktakes/${stocktakeId}/cancel`,
        request,
        idempotencyConfig(idempotencyKey),
      )
    },
  }
}
