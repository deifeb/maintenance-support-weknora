import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function requiredPageSource(): string {
  const url = new URL(
    '../inventory-gap/AllocationPlanDetail.vue',
    import.meta.url,
  )

  assert.equal(
    existsSync(url),
    true,
    'AllocationPlanDetail.vue must exist',
  )

  return readFileSync(url, 'utf8')
}

function sourceSlice(
  source: string,
  startToken: string,
  endToken: string,
): string {
  const start = source.indexOf(startToken)
  const end = source.indexOf(
    endToken,
    start + startToken.length,
  )

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
  'AllocationPlanDetail fails closed when Store plan identity does not match the current route',
  () => {
    const source = requiredPageSource()

    assert.doesNotMatch(
      source,
      /const\s+current\s*=\s*computed\(\(\)\s*=>\s*allocationStore\.planDetail\.item\s*\)/,
      'current must not expose a stale Store plan without checking route identity',
    )

    const currentBlock = sourceSlice(
      source,
      'const current = computed',
      'const canContribute = computed',
    )

    assert.match(
      currentBlock,
      /const\s+planId\s*=\s*routeId\.value/,
    )
    assert.match(
      currentBlock,
      /const\s+item\s*=\s*allocationStore\.planDetail\.item/,
    )
    assert.match(
      currentBlock,
      /planId\s*!==\s*null/,
    )
    assert.match(
      currentBlock,
      /item\s*!==\s*null/,
    )
    assert.match(
      currentBlock,
      /item\.id\s*===\s*planId/,
    )
    assert.match(
      currentBlock,
      /\?\s*item\s*:\s*null/,
    )

    const actionsBlock = sourceSlice(
      source,
      'const availableActions = computed',
      'const conflictEvidence = computed',
    )
    assert.match(actionsBlock, /current\.value/)

    for (const functionName of [
      'saveLineEdit',
      'previewPlan',
      'confirmPlan',
      'executePlan',
      'voidPlan',
      'regeneratePlan',
    ]) {
      const startToken = `async function ${functionName}`
      const start = source.indexOf(startToken)
      assert.notEqual(
        start,
        -1,
        `missing action function: ${functionName}`,
      )

      const following = source.slice(start, start + 900)
      assert.match(
        following,
        /const\s+plan\s*=\s*current\.value/,
        `${functionName} must derive its target from route-guarded current`,
      )
    }

    assert.doesNotMatch(
      source,
      /allocationStore\.planDetail\.item\s*=/,
    )
    assert.doesNotMatch(
      source,
      /allocationStore\.dispose\s*\(/,
    )
    assert.doesNotMatch(
      source,
      /allocationStore\.\$reset\s*\(/,
    )
  },
)
