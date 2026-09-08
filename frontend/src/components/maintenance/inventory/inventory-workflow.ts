import type {
  InventoryBalanceRead,
  InventoryLotStatePreviewRequest,
  InventoryReservationStatus,
  InventoryStocktakeStatus,
  InventoryTransferStatus,
} from '@/api/maintenance/inventory'
import type { MaintenancePermissions } from '@/stores/maintenance/permissions'

export type InventoryWorkspaceTab =
  | 'balances'
  | 'reservations'
  | 'transfers'
  | 'stocktakes'
  | 'transactions'

export const INVENTORY_WORKSPACE_TABS = [
  'balances',
  'reservations',
  'transfers',
  'stocktakes',
  'transactions',
] as const satisfies readonly InventoryWorkspaceTab[]

export type ReservationUiAction =
  | 'issue'
  | 'release'
  | 'return'
  | 'cancel'

export type HighRiskAction =
  | 'adjust'
  | 'freeze'
  | 'unfreeze'
  | 'reverse'

export type LotFreezeUiState =
  | {
      available: false
      reason: 'NO_LOT' | 'LOT_CONCURRENCY_UNAVAILABLE'
    }
  | {
      available: true
      action: 'freeze' | 'unfreeze'
      balanceId: number
      balanceVersion: number
      lotId: number
      lotVersion: number
    }

export type TransferUiAction =
  | 'dispatch'
  | 'receive'
  | 'cancel'


export type StocktakeUiAction =
  | 'start'
  | 'count'
  | 'review'
  | 'confirm'
  | 'rebase'
  | 'cancel'

export const POSITIVE_DECIMAL_18_4 =
  /^(?:0|[1-9]\d{0,13})(?:\.\d{1,4})?$/

export const SIGNED_DECIMAL_18_4 =
  /^-?(?:0|[1-9]\d{0,13})(?:\.\d{1,4})?$/

export function isZeroDecimal18_4(value: string): boolean {
  return /^0(?:\.0{1,4})?$/.test(value)
}

export function isPositiveDecimal18_4(value: string): boolean {
  return POSITIVE_DECIMAL_18_4.test(value) && !isZeroDecimal18_4(value)
}

export function reservationActions(
  status: InventoryReservationStatus,
  permissions: Pick<
    MaintenancePermissions,
    'reserveInventory' | 'issueReturnInventory'
  >,
): ReservationUiAction[] {
  if (!permissions.reserveInventory && !permissions.issueReturnInventory) {
    return []
  }

  const actions: ReservationUiAction[] = []
  if (
    permissions.issueReturnInventory
    && (status === 'ACTIVE' || status === 'PARTIALLY_ISSUED')
  ) {
    actions.push('issue')
  }
  if (
    permissions.reserveInventory
    && (status === 'ACTIVE' || status === 'PARTIALLY_ISSUED')
  ) {
    actions.push('release')
  }
  if (
    permissions.issueReturnInventory
    && (status === 'PARTIALLY_ISSUED' || status === 'FULFILLED')
  ) {
    actions.push('return')
  }
  if (
    permissions.reserveInventory
    && (status === 'ACTIVE' || status === 'PARTIALLY_ISSUED')
  ) {
    actions.push('cancel')
  }
  return actions
}

export function requiresFefoOverrideReason(
  input: {
    lot_id?: number
    serial_item_id?: number
    location_id?: number
  },
): boolean {
  return input.lot_id !== undefined || input.serial_item_id !== undefined
}

export function canExecuteHighRisk(
  action: HighRiskAction,
  permissions: Pick<
    MaintenancePermissions,
    | 'confirmHighRisk'
    | 'adjustInventory'
    | 'freezeInventory'
    | 'reverseInventory'
  >,
): boolean {
  if (!permissions.confirmHighRisk) return false

  if (action === 'adjust') {
    return permissions.adjustInventory
  }

  if (action === 'freeze' || action === 'unfreeze') {
    return permissions.freezeInventory
  }

  return permissions.reverseInventory
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) > 0
}

export function lotFreezeUiState(
  balance: InventoryBalanceRead,
): LotFreezeUiState {
  if (balance.lot_id === null) {
    return { available: false, reason: 'NO_LOT' }
  }

  if (
    !isPositiveInteger(balance.id)
    || !isPositiveInteger(balance.version)
    || !isPositiveInteger(balance.lot_id)
    || !isPositiveInteger(balance.lot_version)
    || typeof balance.lot_is_frozen !== 'boolean'
  ) {
    return {
      available: false,
      reason: 'LOT_CONCURRENCY_UNAVAILABLE',
    }
  }

  return {
    available: true,
    action: balance.lot_is_frozen ? 'unfreeze' : 'freeze',
    balanceId: balance.id,
    balanceVersion: balance.version,
    lotId: balance.lot_id,
    lotVersion: balance.lot_version,
  }
}

export function buildLotStatePreviewRequest(
  balance: InventoryBalanceRead,
  reason: string,
): InventoryLotStatePreviewRequest | null {
  const state = lotFreezeUiState(balance)
  if (!state.available) return null

  return {
    operation_type: state.action === 'freeze' ? 'FREEZE' : 'UNFREEZE',
    balance_id: state.balanceId,
    expected_balance_version: state.balanceVersion,
    reason,
    deltas: null,
    lot_id: state.lotId,
    expected_lot_version: state.lotVersion,
  }
}

export function transferActions(
  status: InventoryTransferStatus,
  permissions: Pick<MaintenancePermissions, 'transferInventory'>,
): TransferUiAction[] {
  if (!permissions.transferInventory) return []

  if (status === 'DRAFT') {
    return ['dispatch', 'cancel']
  }

  if (status === 'DISPATCHED' || status === 'PARTIALLY_RECEIVED') {
    return ['receive']
  }

  return []
}


export function stocktakeActions(
  status: InventoryStocktakeStatus,
  permissions: MaintenancePermissions,
): StocktakeUiAction[] {
  if (status === 'CONFIRMED' || status === 'CANCELLED') return []

  const actions: StocktakeUiAction[] = []

  if (status === 'DRAFT' && permissions.createStocktake) {
    return ['start', 'cancel']
  }

  if (status === 'COUNTING' && permissions.createStocktake) {
    return ['count', 'review', 'cancel']
  }

  if (status === 'REVIEWING') {
    if (permissions.confirmStocktake) actions.push('confirm')
    if (permissions.createStocktake) actions.push('cancel')
    return actions
  }

  if (status === 'CONFLICTED') {
    if (permissions.createStocktake) actions.push('rebase')
    if (permissions.confirmStocktake) actions.push('confirm')
    if (permissions.createStocktake) actions.push('cancel')
    return actions
  }

  return []
}

export function positiveInventoryRouteId(
  value: unknown,
): number | null {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string' && typeof candidate !== 'number') {
    return null
  }
  const parsed = typeof candidate === 'number'
    ? candidate
    : Number(candidate)
  return Number.isInteger(parsed) && parsed > 0
    ? parsed
    : null
}
