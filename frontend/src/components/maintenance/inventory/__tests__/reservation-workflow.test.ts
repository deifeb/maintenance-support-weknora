import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const reservationStatuses = [
  'ACTIVE',
  'PARTIALLY_ISSUED',
  'FULFILLED',
  'RELEASED',
  'CANCELLED',
  'EXPIRED',
] as const

type ReservationStatus = typeof reservationStatuses[number]
type PermissionShape = {
  reserveInventory: boolean
  issueReturnInventory: boolean
}
type ReservationAction = 'issue' | 'release' | 'return' | 'cancel'
type ReservationActionsFn = (
  status: ReservationStatus,
  permissions: PermissionShape,
) => ReservationAction[]
type RequiresFefoOverrideReasonFn = (
  input: {
    lot_id?: number
    serial_item_id?: number
    location_id?: number
  },
) => boolean

function requiredUrl(relative: string): URL {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `required reservation production source is missing: ${relative}`,
  )
  return url
}

function source(relative: string): string {
  return readFileSync(requiredUrl(relative), 'utf8')
}

async function workflowModule(): Promise<Record<string, unknown>> {
  return await import(requiredUrl('../inventory-workflow.ts').href)
}

async function reservationActions(): Promise<ReservationActionsFn> {
  const candidate = (await workflowModule()).reservationActions
  assert.equal(
    typeof candidate,
    'function',
    'inventory workflow is missing reservationActions()',
  )
  return candidate as ReservationActionsFn
}

async function overrideReasonRequirement(): Promise<RequiresFefoOverrideReasonFn> {
  const candidate = (await workflowModule()).requiresFefoOverrideReason
  assert.equal(
    typeof candidate,
    'function',
    'inventory workflow is missing requiresFefoOverrideReason()',
  )
  return candidate as RequiresFefoOverrideReasonFn
}

const viewer: PermissionShape = {
  reserveInventory: false,
  issueReturnInventory: false,
}
const contributor: PermissionShape = {
  reserveInventory: true,
  issueReturnInventory: true,
}
const admin: PermissionShape = {
  reserveInventory: true,
  issueReturnInventory: true,
}

const lifecycleExpected: Record<ReservationStatus, ReservationAction[]> = {
  ACTIVE: ['issue', 'release', 'cancel'],
  PARTIALLY_ISSUED: ['issue', 'release', 'return', 'cancel'],
  FULFILLED: ['return'],
  RELEASED: [],
  CANCELLED: [],
  EXPIRED: [],
}

test('reservationActions hides every lifecycle command from viewer', async () => {
  const actions = await reservationActions()
  for (const status of reservationStatuses) {
    assert.deepEqual(actions(status, viewer), [], `viewer ${status}`)
  }
})

for (const [role, permissions] of [
  ['contributor', contributor],
  ['admin', admin],
] as const) {
  test(`reservationActions exposes the exact ${role} lifecycle matrix`, async () => {
    const actions = await reservationActions()
    for (const status of reservationStatuses) {
      assert.deepEqual(
        actions(status, permissions),
        lifecycleExpected[status],
        `${role} ${status}`,
      )
    }
  })
}

test('requiresFefoOverrideReason only treats lot/serial constraints as FEFO overrides', async () => {
  const requiresReason = await overrideReasonRequirement()

  assert.equal(requiresReason({}), false)
  assert.equal(requiresReason({ location_id: 9 }), false)
  assert.equal(requiresReason({ lot_id: 71 }), true)
  assert.equal(requiresReason({ serial_item_id: 81 }), true)
  assert.equal(requiresReason({ lot_id: 71, serial_item_id: 81 }), true)
})

test('ReservationDialog delegates FEFO choice to backend and requires trimmed override reason', () => {
  const reservationSource = source('../ReservationDialog.vue')

  assert.doesNotMatch(
    reservationSource,
    /sort\(.*expiry|expiry.*sort|selectFefo|rankFefo/i,
  )
  assert.match(reservationSource, /collectReservationBalanceVersions/)
  assert.match(reservationSource, /requiresFefoOverrideReason/)
  assert.match(reservationSource, /fefo_override_reason/)
  assert.match(
    reservationSource,
    /fefo_override_reason[^\n]{0,240}trim\(\)|trim\(\)[^\n]{0,240}fefo_override_reason/s,
    'lot/serial override validation must require a trimmed non-empty reason',
  )
})

test('ReservationDialog collects expected balance versions immediately before createReservation', () => {
  const reservationSource = source('../ReservationDialog.vue')
  const collectAt = reservationSource.indexOf('collectReservationBalanceVersions')
  const createAt = reservationSource.indexOf('createReservation')

  assert.notEqual(collectAt, -1, 'missing collectReservationBalanceVersions() call')
  assert.notEqual(createAt, -1, 'missing createReservation() call')
  assert.ok(
    collectAt < createAt,
    'collectReservationBalanceVersions() must run before createReservation()',
  )
  assert.match(
    reservationSource,
    /collectReservationBalanceVersions[\s\S]{0,1600}expected_balance_versions[\s\S]{0,1600}createReservation/,
    'collected server balance versions must be passed into reservation create request',
  )
})

test('FEFOAllocationEvidence renders only backend-returned reservation line evidence', () => {
  const evidenceSource = source('../FEFOAllocationEvidence.vue')

  assert.match(evidenceSource, /reservation\.lines|\blines\b/)
  for (const field of [
    'balance_id',
    'lot_id',
    'serial_item_id',
    'reserved_quantity',
    'fefo_rank',
    'fefo_override_reason',
  ]) {
    assert.match(
      evidenceSource,
      new RegExp(`\\b${field}\\b`),
      `FEFO evidence must render backend reservation-line field ${field}`,
    )
  }

  assert.doesNotMatch(evidenceSource, /server recommendation/i)
  assert.doesNotMatch(
    evidenceSource,
    /\bexpiry\b|\bavailable_quantity\b|\bon_hand_quantity\b|\bcandidate/i,
    'FEFO evidence must not present client/pre-submit candidates as server evidence',
  )
})

test('reservation return queries ISSUE transactions with the exact server filter contract', () => {
  const reservationSource = source('../ReservationDialog.vue')

  for (const contract of [
    /operation_type\s*:\s*['"]ISSUE['"]/,
    /reference_type\s*:\s*['"]INVENTORY_RESERVATION['"]/,
    /reference_id\s*:\s*String\(\s*(?:reservation(?:\.value)?|props\.reservation)\.id\s*\)/,
    /sort_by\s*:\s*['"]id['"]/,
    /sort_order\s*:\s*['"]desc['"]/,
    /page\s*:\s*1\b/,
    /page_size\s*:\s*100\b/,
  ]) {
    assert.match(reservationSource, contract)
  }
})

test('reservation return traverses every ISSUE transaction page and never invents issue_transaction_id', () => {
  const reservationSource = source('../ReservationDialog.vue')

  assert.match(reservationSource, /fetchTransactions/)
  assert.match(reservationSource, /transactions/)
  assert.match(reservationSource, /\.pages\b|\bpages\b/)
  assert.match(
    reservationSource,
    /while\s*\(|for\s*\(|do\s*\{/,
    'return lookup must iterate server pages when more than 100 matches exist',
  )
  assert.match(
    reservationSource,
    /page\s*(?:\+=\s*1|\+\+|=\s*page\s*\+\s*1)/,
    'return lookup must advance page number',
  )
  assert.match(
    reservationSource,
    /issue_transaction_id/,
    'return payload must carry the user-selected issue transaction id',
  )
  assert.doesNotMatch(
    reservationSource,
    /issue_transaction_id\s*:\s*(?:reservation|line)\.id/,
    'issue_transaction_id must never be guessed from reservation/line ids',
  )
})
