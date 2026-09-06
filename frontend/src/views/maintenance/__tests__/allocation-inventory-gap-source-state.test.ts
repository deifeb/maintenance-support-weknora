import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function requiredPageSource(): string {
  const url = new URL(
    '../inventory-gap/InventoryGapPage.vue',
    import.meta.url,
  )

  assert.equal(
    existsSync(url),
    true,
    'InventoryGapPage.vue must exist',
  )

  return readFileSync(url, 'utf8')
}

function functionSlice(
  source: string,
  startToken: string,
  endToken: string,
): string {
  const start = source.indexOf(startToken)
  const end = source.indexOf(endToken, start + startToken.length)

  assert.notEqual(
    start,
    -1,
    `missing start token: ${startToken}`,
  )
  assert.notEqual(
    end,
    -1,
    `missing end token: ${endToken}`,
  )

  return source.slice(start, end)
}

test(
  'InventoryGapPage allocation source identity guard fails closed on stale DemandList current state',
  () => {
    const source = requiredPageSource()

    assert.match(
      source,
      /const\s+selectedAllocationSourceId\s*=\s*computed/,
    )
    assert.match(
      source,
      /const\s+allocationSourceMatchesInput\s*=\s*computed/,
    )
    assert.match(
      source,
      /selectedAllocationSourceId\.value\s*===\s*source\.id/,
    )

    const eligibility = functionSlice(
      source,
      'const allocationSourceEligible = computed',
      'const canCreateAllocationPlan = computed',
    )
    assert.match(
      eligibility,
      /allocationSourceMatchesInput\.value/,
    )

    const fetchPlans = functionSlice(
      source,
      'async function fetchPlans',
      'function refreshAllocationPlans',
    )
    assert.match(fetchPlans, /matchedSourceId/)
    assert.match(
      fetchPlans,
      /source_demand_list_id\s*:\s*matchedSourceId/,
    )
    assert.doesNotMatch(
      fetchPlans,
      /source_demand_list_id\s*:\s*source\?\s*\.id/,
    )

    const createPlan = functionSlice(
      source,
      'async function createPlan',
      'function openAllocationRules',
    )
    assert.match(
      createPlan,
      /const\s+selectedSourceId\s*=\s*selectedAllocationSourceId\.value/,
    )
    assert.match(
      createPlan,
      /source\.id\s*!==\s*selectedSourceId/,
    )
    assert.match(
      createPlan,
      /allocation\.createPlan/,
    )

    assert.doesNotMatch(
      source,
      /demandList\.current\s*=\s*null/,
    )
    assert.doesNotMatch(source, /demandList\.\$reset/)
    assert.doesNotMatch(source, /Idempotency-Key/)
    assert.doesNotMatch(source, /allocationApi\./)
    assert.doesNotMatch(source, /demandListApi\./)
  },
)
