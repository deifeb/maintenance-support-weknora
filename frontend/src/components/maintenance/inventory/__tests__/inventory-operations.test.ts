import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

type HighRiskAction = 'adjust' | 'freeze' | 'unfreeze' | 'reverse'
type TransferStatus =
  | 'DRAFT'
  | 'DISPATCHED'
  | 'PARTIALLY_RECEIVED'
  | 'COMPLETED'
  | 'CANCELLED'
type TransferUiAction = 'dispatch' | 'receive' | 'cancel'

type PermissionShape = {
  confirmHighRisk: boolean
  adjustInventory: boolean
  freezeInventory: boolean
  reverseInventory: boolean
  transferInventory: boolean
}

type CanExecuteHighRiskFn = (
  action: HighRiskAction,
  permissions: PermissionShape,
) => boolean

type TransferActionsFn = (
  status: TransferStatus,
  permissions: PermissionShape,
) => TransferUiAction[]

type LotFreezeUiStateFn = (balance: Record<string, unknown>) => unknown
type BuildLotStatePreviewRequestFn = (
  balance: Record<string, unknown>,
  reason: string,
) => unknown

function requiredUrl(relative: string): URL {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `required inventory operation production source is missing: ${relative}`,
  )
  return url
}

function source(relative: string): string {
  return readFileSync(requiredUrl(relative), 'utf8')
}

async function workflowModule(): Promise<Record<string, unknown>> {
  return await import(requiredUrl('../inventory-workflow.ts').href)
}

async function workflowFunction<T extends (...args: never[]) => unknown>(
  name: string,
): Promise<T> {
  const candidate = (await workflowModule())[name]
  assert.equal(
    typeof candidate,
    'function',
    `inventory workflow is missing ${name}()`,
  )
  return candidate as T
}

function permissions(
  overrides: Partial<PermissionShape> = {},
): PermissionShape {
  return {
    confirmHighRisk: false,
    adjustInventory: false,
    freezeInventory: false,
    reverseInventory: false,
    transferInventory: false,
    ...overrides,
  }
}

function balance(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: 11,
    version: 5,
    lot_id: 71,
    lot_version: 9,
    lot_is_frozen: false,
    ...overrides,
  }
}

function functionSource(name: string): string {
  const workflowSource = source('../inventory-workflow.ts')
  const start = workflowSource.indexOf(`export function ${name}`)
  assert.notEqual(start, -1, `inventory workflow is missing ${name}() source`)
  const next = workflowSource.indexOf('\nexport function ', start + 1)
  return workflowSource.slice(start, next === -1 ? undefined : next)
}

test('canExecuteHighRisk requires confirmHighRisk and the action-specific authority', async () => {
  const canExecute = await workflowFunction<CanExecuteHighRiskFn>(
    'canExecuteHighRisk',
  )

  for (const action of [
    'adjust',
    'freeze',
    'unfreeze',
    'reverse',
  ] as const) {
    assert.equal(
      canExecute(action, permissions({
        adjustInventory: true,
        freezeInventory: true,
        reverseInventory: true,
      })),
      false,
      `${action} must fail closed without confirmHighRisk`,
    )
  }

  assert.equal(
    canExecute('adjust', permissions({
      confirmHighRisk: true,
      adjustInventory: true,
    })),
    true,
  )
  assert.equal(
    canExecute('adjust', permissions({ confirmHighRisk: true })),
    false,
  )

  for (const action of ['freeze', 'unfreeze'] as const) {
    assert.equal(
      canExecute(action, permissions({
        confirmHighRisk: true,
        freezeInventory: true,
      })),
      true,
    )
    assert.equal(
      canExecute(action, permissions({ confirmHighRisk: true })),
      false,
    )
  }

  assert.equal(
    canExecute('reverse', permissions({
      confirmHighRisk: true,
      reverseInventory: true,
    })),
    true,
  )
  assert.equal(
    canExecute('reverse', permissions({ confirmHighRisk: true })),
    false,
  )
})

test('lotFreezeUiState is the fail-closed single source of Freeze/Unfreeze UI state', async () => {
  const state = await workflowFunction<LotFreezeUiStateFn>('lotFreezeUiState')

  assert.deepEqual(
    state(balance({
      lot_id: null,
      lot_version: null,
      lot_is_frozen: null,
    })),
    { available: false, reason: 'NO_LOT' },
  )
  assert.deepEqual(
    state(balance({ lot_version: null, lot_is_frozen: null })),
    { available: false, reason: 'LOT_CONCURRENCY_UNAVAILABLE' },
  )
  assert.deepEqual(
    state(balance({ lot_version: 9, lot_is_frozen: null })),
    { available: false, reason: 'LOT_CONCURRENCY_UNAVAILABLE' },
  )
  assert.deepEqual(
    state(balance({ lot_is_frozen: false })),
    {
      available: true,
      action: 'freeze',
      balanceId: 11,
      balanceVersion: 5,
      lotId: 71,
      lotVersion: 9,
    },
  )
  assert.deepEqual(
    state(balance({ lot_id: 72, lot_version: 10, lot_is_frozen: true })),
    {
      available: true,
      action: 'unfreeze',
      balanceId: 11,
      balanceVersion: 5,
      lotId: 72,
      lotVersion: 10,
    },
  )
})

test('buildLotStatePreviewRequest emits the exact authoritative FREEZE/UNFREEZE payload and never defaults lot concurrency', async () => {
  const build = await workflowFunction<BuildLotStatePreviewRequestFn>(
    'buildLotStatePreviewRequest',
  )

  assert.deepEqual(
    build(balance({ lot_is_frozen: false }), 'quality hold'),
    {
      operation_type: 'FREEZE',
      balance_id: 11,
      expected_balance_version: 5,
      reason: 'quality hold',
      deltas: null,
      lot_id: 71,
      expected_lot_version: 9,
    },
  )
  assert.deepEqual(
    build(
      balance({ lot_id: 72, lot_version: 10, lot_is_frozen: true }),
      'release hold',
    ),
    {
      operation_type: 'UNFREEZE',
      balance_id: 11,
      expected_balance_version: 5,
      reason: 'release hold',
      deltas: null,
      lot_id: 72,
      expected_lot_version: 10,
    },
  )
  assert.equal(build(balance({ lot_version: null }), 'hold'), null)
  assert.equal(build(balance({ lot_is_frozen: null }), 'hold'), null)

  const buildSource = functionSource('buildLotStatePreviewRequest')
  assert.doesNotMatch(buildSource, /expected_lot_version\s*:\s*[^\n]*\?\?\s*1/)
  assert.doesNotMatch(buildSource, /serial_item_id/)
})

test('InventoryOperationPreviewDialog renders metadata-only preview evidence', () => {
  const previewSource = source('../InventoryOperationPreviewDialog.vue')

  for (const contract of [
    /commandSummary|command-summary/,
    /transactionId|transaction_id/,
    /operationType|operation_type/,
    /transactionVersion|transaction_version/,
    /confirmationExpiresAt|confirmation_expires_at/,
  ]) {
    assert.match(previewSource, contract)
  }

  assert.doesNotMatch(
    previewSource,
    /preview\.(?:before|after|warnings|risks)\b/,
    'metadata-only preview must not bind nonexistent rich preview fields',
  )
})

test('high-risk UI uses Store preview/execute lifecycle and never accepts a caller-supplied confirmation token', () => {
  const previewSource = source('../InventoryOperationPreviewDialog.vue')
  const balanceDetailSource = source('../../../../views/maintenance/inventory-gap/InventoryBalanceDetail.vue')
  const transactionDetailSource = source('../../../../views/maintenance/inventory-gap/InventoryTransactionDetail.vue')
  const combined = `${previewSource}\n${balanceDetailSource}\n${transactionDetailSource}`

  assert.match(combined, /previewOperation/)
  assert.match(combined, /executeOperation/)
  assert.match(combined, /previewReverse/)
  assert.match(combined, /executeReverse/)
  assert.doesNotMatch(
    combined,
    /v-model[^\n>]*confirmation(?:Token|_token)|<input[^>]*confirmation(?:Token|_token)/i,
    'confirmation token must come only from Store preview state',
  )
})

test('transferActions exposes only the frozen two-stage admin lifecycle', async () => {
  const actions = await workflowFunction<TransferActionsFn>('transferActions')
  const admin = permissions({ transferInventory: true })
  const viewer = permissions()
  const contributor = permissions()

  assert.deepEqual(actions('DRAFT', admin), ['dispatch', 'cancel'])
  assert.deepEqual(actions('DISPATCHED', admin), ['receive'])
  assert.deepEqual(actions('PARTIALLY_RECEIVED', admin), ['receive'])
  assert.deepEqual(actions('COMPLETED', admin), [])
  assert.deepEqual(actions('CANCELLED', admin), [])

  for (const role of [viewer, contributor]) {
    for (const status of [
      'DRAFT',
      'DISPATCHED',
      'PARTIALLY_RECEIVED',
      'COMPLETED',
      'CANCELLED',
    ] as const) {
      assert.deepEqual(actions(status, role), [])
    }
  }
})

test('TransferWorkflow captures authoritative source balance versions when creating a transfer', () => {
  const transferSource = source('../TransferWorkflow.vue')

  assert.match(transferSource, /createTransfer/)
  assert.match(transferSource, /expected_source_version/)
  assert.match(
    transferSource,
    /expected_source_version\s*:\s*[^,\n]*\.version/,
    'transfer create must copy the authoritative source balance version',
  )
  assert.match(transferSource, /quantity/)
})

test('TransferWorkflow dispatches only through Store preview then execute', () => {
  const transferSource = source('../TransferWorkflow.vue')
  const previewAt = transferSource.indexOf('previewTransferDispatch')
  const executeAt = transferSource.indexOf('executeTransferDispatch')

  assert.notEqual(previewAt, -1, 'missing previewTransferDispatch()')
  assert.notEqual(executeAt, -1, 'missing executeTransferDispatch()')
  assert.ok(previewAt < executeAt, 'dispatch preview must precede dispatch execute')
  assert.match(transferSource, /expected_version\s*:\s*[^,\n]*\.version/)
  assert.doesNotMatch(
    transferSource,
    /confirmation_token\s*:\s*(?:form|input|token|confirmation)/i,
    'dispatch execute must consume Store preview authority, not caller token text',
  )
})

test('TransferWorkflow receives explicit positive line quantities, keeps partial transfers receivable, and relies on authoritative Store refresh', () => {
  const transferSource = source('../TransferWorkflow.vue')

  assert.match(transferSource, /PARTIALLY_RECEIVED/)
  assert.match(transferSource, /previewTransferReceive/)
  assert.match(transferSource, /executeTransferReceive/)
  assert.match(transferSource, /isPositiveDecimal18_4|POSITIVE_DECIMAL_18_4/)
  assert.match(transferSource, /transfer_line_id/)
  assert.match(transferSource, /quantity/)
  assert.match(transferSource, /fetchTransferDetail|executeTransferReceive/)
  assert.match(transferSource, /fetchBalances|executeTransferReceive/)
})
