import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

type StocktakeStatus =
  | 'DRAFT'
  | 'COUNTING'
  | 'REVIEWING'
  | 'CONFIRMED'
  | 'CONFLICTED'
  | 'CANCELLED'

type StocktakeUiAction =
  | 'start'
  | 'count'
  | 'review'
  | 'confirm'
  | 'rebase'
  | 'cancel'

type PermissionShape = {
  createStocktake: boolean
  confirmStocktake: boolean
}

type StocktakeActionsFn = (
  status: StocktakeStatus,
  permissions: PermissionShape,
) => StocktakeUiAction[]

const statuses: readonly StocktakeStatus[] = [
  'DRAFT',
  'COUNTING',
  'REVIEWING',
  'CONFIRMED',
  'CONFLICTED',
  'CANCELLED',
]

const viewer: PermissionShape = {
  createStocktake: false,
  confirmStocktake: false,
}
const contributor: PermissionShape = {
  createStocktake: true,
  confirmStocktake: false,
}
const admin: PermissionShape = {
  createStocktake: true,
  confirmStocktake: true,
}

function requiredUrl(relative: string): URL {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `required stocktake production source is missing: ${relative}`,
  )
  return url
}

function source(relative: string): string {
  return readFileSync(requiredUrl(relative), 'utf8')
}

async function workflowModule(): Promise<Record<string, unknown>> {
  return await import(requiredUrl('../inventory-workflow.ts').href)
}

async function stocktakeActions(): Promise<StocktakeActionsFn> {
  const candidate = (await workflowModule()).stocktakeActions
  assert.equal(
    typeof candidate,
    'function',
    'inventory workflow is missing stocktakeActions()',
  )
  return candidate as StocktakeActionsFn
}

function stocktakeWorkflowSource(): string {
  return source('../StocktakeWorkflow.vue')
}

test('stocktakeActions exposes the exact viewer, contributor, and admin lifecycle matrix', async () => {
  const actions = await stocktakeActions()

  for (const status of statuses) {
    assert.deepEqual(actions(status, viewer), [], `viewer ${status}`)
  }

  const contributorExpected: Record<StocktakeStatus, StocktakeUiAction[]> = {
    DRAFT: ['start', 'cancel'],
    COUNTING: ['count', 'review', 'cancel'],
    REVIEWING: ['cancel'],
    CONFLICTED: ['rebase', 'cancel'],
    CONFIRMED: [],
    CANCELLED: [],
  }
  const adminExpected: Record<StocktakeStatus, StocktakeUiAction[]> = {
    DRAFT: ['start', 'cancel'],
    COUNTING: ['count', 'review', 'cancel'],
    REVIEWING: ['confirm', 'cancel'],
    CONFLICTED: ['rebase', 'confirm', 'cancel'],
    CONFIRMED: [],
    CANCELLED: [],
  }

  for (const status of statuses) {
    assert.deepEqual(
      actions(status, contributor),
      contributorExpected[status],
      `contributor ${status}`,
    )
    assert.deepEqual(
      actions(status, admin),
      adminExpected[status],
      `admin ${status}`,
    )
  }
})

test('typed API and Store preserve PATCH plus idempotent stocktake count transport', () => {
  const apiSource = source('../../../../api/maintenance/inventory.ts')
  const storeSource = source('../../../../stores/maintenance/inventory.ts')

  assert.match(
    apiSource,
    /updateStocktakeLine\([\s\S]{0,900}return client\.patch<InventoryStocktakeRead>/,
    'stocktake line count must use the typed PATCH API',
  )
  assert.match(
    apiSource,
    /`\/v1\/inventory\/stocktakes\/\$\{stocktakeId\}`[\s\S]{0,220}`\/lines\/\$\{lineId\}`[\s\S]{0,320}idempotencyConfig\(idempotencyKey\)/,
    'PATCH transport must keep explicit Idempotency-Key configuration',
  )
  assert.match(
    storeSource,
    /async function updateStocktakeLine\([\s\S]{0,900}'stocktake\.count'[\s\S]{0,500}api\.updateStocktakeLine\(id, lineId, request, key\)/,
    'Store must own the logical stocktake count write and idempotency key',
  )
})

test('StocktakeWorkflow sends exact string count with authoritative stocktake and line versions', () => {
  const workflowSource = stocktakeWorkflowSource()

  assert.match(workflowSource, /updateStocktakeLine/)
  assert.match(workflowSource, /expected_version\s*:\s*(?:stocktake(?:\.value)?|props\.stocktake)\.version/)
  assert.match(workflowSource, /expected_line_version\s*:\s*line\.version/)
  assert.match(workflowSource, /counted_quantity\s*:\s*line\.(?:countedQuantity|counted_quantity|countInput)/)
  assert.doesNotMatch(
    workflowSource,
    /counted_quantity\s*:\s*(?:Number|parseFloat|parseInt)\s*\(/,
    'counted_quantity must remain an exact decimal string',
  )
  assert.match(
    workflowSource,
    /['"]12\.5000['"]|inputmode=['"]decimal['"]|isPositiveDecimal18_4|SIGNED_DECIMAL_18_4/,
    'count UI must preserve exact decimal string semantics',
  )
})

test('StocktakeWorkflow disables resolved lines and rebases unresolved CONFLICTED lines only', () => {
  const workflowSource = stocktakeWorkflowSource()

  assert.match(workflowSource, /ADJUSTED/)
  assert.match(workflowSource, /CONFLICTED/)
  assert.match(
    workflowSource,
    /resolution\s*===?\s*['"]CONFLICTED['"]|['"]CONFLICTED['"]\s*===?\s*[^\n]*resolution/,
    'rebase eligibility must be derived from unresolved CONFLICTED resolution',
  )
  assert.match(
    workflowSource,
    /disabled[\s\S]{0,500}resolution|resolution[\s\S]{0,500}disabled/,
    'already adjusted/resolved lines must render disabled',
  )
  assert.match(workflowSource, /rebaseStocktake/)
  assert.match(workflowSource, /lines\s*:\s*[^\n]*selected|selected[^\n]*\.map|filter\([^)]*CONFLICTED/)
  assert.doesNotMatch(
    workflowSource,
    /lines\s*:\s*(?:stocktake(?:\.value)?|props\.stocktake)\.lines\s*\.map/,
    'rebase payload must never blindly include every stocktake line',
  )
})

test('StocktakeWorkflow rebase payload uses backend RECOUNT or BASELINE_ACCEPT enums only', () => {
  const workflowSource = stocktakeWorkflowSource()

  assert.match(workflowSource, /RECOUNT/)
  assert.match(workflowSource, /BASELINE_ACCEPT/)
  assert.match(workflowSource, /line_id\s*:\s*line\.id/)
  assert.match(workflowSource, /action\s*:\s*line\.(?:rebaseAction|rebase_action|action)/)
  assert.doesNotMatch(
    workflowSource,
    /action\s*:\s*t\s*\(/,
    'localized labels must never be submitted as backend rebase actions',
  )
})

test('Store stocktake confirm owns preview authority and fresh execute idempotency lifecycle', () => {
  const storeSource = source('../../../../stores/maintenance/inventory.ts')

  assert.match(
    storeSource,
    /function previewStocktakeConfirm\([\s\S]{0,700}runPreview\([\s\S]{0,160}'stocktake\.confirm\.preview'[\s\S]{0,260}api\.previewStocktakeConfirm\(id, request, key\)/,
  )
  assert.match(
    storeSource,
    /async function executeStocktakeConfirm\(\)[\s\S]{0,300}currentPreview\(['"]stocktake\.confirm\.preview['"]\)[\s\S]{0,500}transaction_id:\s*preview\.transactionId[\s\S]{0,240}expected_transaction_version:\s*preview\.transactionVersion[\s\S]{0,240}confirmation_token:\s*preview\.confirmationToken/,
    'execute must derive transaction/version/token exclusively from Store preview state',
  )
  assert.match(
    storeSource,
    /runCommand\([\s\S]{0,180}'stocktake\.confirm\.execute'[\s\S]{0,500}api\.executeStocktakeConfirm\([\s\S]{0,220}key/,
    'confirm execute must be a separate logical write with its own idempotency key',
  )
  assert.doesNotMatch(
    storeSource,
    /function executeStocktakeConfirm\([^)]*(?:token|transaction)/,
    'executeStocktakeConfirm must not accept caller-supplied confirmation authority',
  )
})

test('StocktakeWorkflow confirms through Store preview then zero-authority execute', () => {
  const workflowSource = stocktakeWorkflowSource()

  const previewAt = workflowSource.indexOf('previewStocktakeConfirm')
  const executeAt = workflowSource.indexOf('executeStocktakeConfirm')
  assert.notEqual(previewAt, -1, 'missing previewStocktakeConfirm() call')
  assert.notEqual(executeAt, -1, 'missing executeStocktakeConfirm() call')
  assert.ok(previewAt < executeAt, 'confirm preview must precede confirm execute')
  assert.match(
    workflowSource,
    /previewStocktakeConfirm\([^,]+,\s*\{\s*expected_version\s*:\s*(?:stocktake(?:\.value)?|props\.stocktake)\.version\s*\}/s,
    'confirm preview must use the current authoritative stocktake version',
  )
  assert.match(
    workflowSource,
    /executeStocktakeConfirm\(\s*\)/,
    'confirm execute must accept no caller token/version/transaction authority',
  )
  assert.doesNotMatch(
    workflowSource,
    /confirmation_token|confirmationToken\s*:/,
    'StocktakeWorkflow must never own or submit a confirmation token',
  )
})
