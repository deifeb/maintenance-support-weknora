import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function requiredUrl(relative: string): URL {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `required inventory production source is missing: ${relative}`,
  )
  return url
}

function source(relative: string): string {
  return readFileSync(requiredUrl(relative), 'utf8')
}

test('inventory workflow helper exports the exact five workspace tabs', async () => {
  const helperUrl = requiredUrl('../inventory-workflow.ts')
  const module = await import(helperUrl.href)

  assert.deepEqual(
    module.INVENTORY_WORKSPACE_TABS,
    [
      'balances',
      'reservations',
      'transfers',
      'stocktakes',
      'transactions',
    ],
  )
})

test('InventoryGapPage wires all five server-backed list slices', () => {
  const pageSource = source(
    '../../../../views/maintenance/inventory-gap/InventoryGapPage.vue',
  )
  const requiredFetches = [
    'fetchBalances',
    'fetchReservations',
    'fetchTransfers',
    'fetchStocktakes',
    'fetchTransactions',
  ]
  const missing = requiredFetches.filter(
    (method) => !pageSource.includes(method),
  )

  assert.deepEqual(
    missing,
    [],
    `InventoryGapPage is missing server list wiring: ${missing.join(', ')}`,
  )
})

test('balance table renders only authoritative balance fields', () => {
  const balanceTableSource = source('../InventoryBalanceTable.vue')

  assert.doesNotMatch(
    balanceTableSource,
    /\bexpiry\b|\brisk\b|\bdemand[\s_-]*gap\b/i,
  )
})

const detailContracts = [
  {
    file: 'InventoryBalanceDetail.vue',
    loader: 'fetchBalanceDetail',
    evidence: ['lot_id', 'lot_version', 'lot_is_frozen'],
  },
  {
    file: 'InventoryReservationDetail.vue',
    loader: 'fetchReservationDetail',
    evidence: ['version', 'lines'],
  },
  {
    file: 'InventoryTransferDetail.vue',
    loader: 'fetchTransferDetail',
    evidence: ['version', 'lines'],
  },
  {
    file: 'InventoryStocktakeDetail.vue',
    loader: 'fetchStocktakeDetail',
    evidence: ['version', 'lines'],
  },
  {
    file: 'InventoryTransactionDetail.vue',
    loader: 'fetchTransactionDetail',
    evidence: ['entries', 'state_before_json', 'state_after_json'],
  },
] as const

for (const contract of detailContracts) {
  test(`${contract.file} is a Store-backed read-only evidence view`, () => {
    const detailSource = source(
      `../../../../views/maintenance/inventory-gap/${contract.file}`,
    )

    assert.match(detailSource, /useInventoryStore/)
    assert.match(
      detailSource,
      new RegExp(`\\b${contract.loader}\\b`),
      `${contract.file} must call Inventory Store loader ${contract.loader}`,
    )
    assert.doesNotMatch(detailSource, /@\/api\/maintenance\/inventory/)
    assert.doesNotMatch(detailSource, /@\/utils\/request/)

    for (const field of contract.evidence) {
      assert.match(
        detailSource,
        new RegExp(`\\b${field}\\b`),
        `${contract.file} must render public evidence ${field}`,
      )
    }

    if (contract.file === 'InventoryBalanceDetail.vue') {
      assert.doesNotMatch(detailSource, /\?\?\s*1\b/)
      assert.doesNotMatch(detailSource, /\?\?\s*false\b/)
    }
  })
}
