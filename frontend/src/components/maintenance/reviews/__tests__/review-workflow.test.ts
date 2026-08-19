import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function requiredSource(relative: string): string {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `TASK7_RED_WORKFLOW: required Task 7 production source is missing: ${relative}`,
  )
  return readFileSync(url, 'utf8')
}

test('ReviewSummary renders only formal review status and authoritative finding counts', () => {
  const source = requiredSource('../ReviewSummary.vue')

  for (const field of [
    'status',
    'total_finding_count',
    'blocking_finding_count',
    'pending_finding_count',
    'pending_blocking_finding_count',
  ]) {
    assert.match(
      source,
      new RegExp(`\\b${field}\\b`),
      `TASK7_RED_WORKFLOW: ReviewSummary must render ${field}`,
    )
  }

  assert.doesNotMatch(
    source,
    /AIReviewRun|ai[-_/]?review|\/ai\/reviews/i,
    'TASK7_RED_WORKFLOW: ReviewSummary must not render AI review authority',
  )
})

test('FindingTable supports formal finding filters, selection, severity, blocking and decision state', () => {
  const source = requiredSource('../FindingTable.vue')

  for (const field of [
    'finding_key',
    'rule_code',
    'severity',
    'blocking',
    'requires_admin_acceptance',
    'decision_status',
  ]) {
    assert.match(
      source,
      new RegExp(`\\b${field}\\b`),
      `TASK7_RED_WORKFLOW: FindingTable must expose ${field}`,
    )
  }

  assert.match(
    source,
    /filter|filtered/i,
    'TASK7_RED_WORKFLOW: FindingTable needs finding filters',
  )
  assert.match(
    source,
    /select|selected|selection/i,
    'TASK7_RED_WORKFLOW: FindingTable needs finding selection for batch decisions',
  )
})

test('FindingDecisionDialog exposes exact formal actions and validates EDIT_ACCEPTED quantity plus reason', () => {
  const source = requiredSource('../FindingDecisionDialog.vue')

  for (const action of ['ACCEPTED', 'REJECTED', 'EDIT_ACCEPTED']) {
    assert.match(
      source,
      new RegExp(`\\b${action}\\b`),
      `TASK7_RED_WORKFLOW: decision dialog must expose ${action}`,
    )
  }

  assert.match(source, /final_quantity/)
  assert.match(source, /reason/)
  assert.match(
    source,
    /trim\s*\(\s*\)/,
    'TASK7_RED_WORKFLOW: EDIT_ACCEPTED reason must be trimmed/non-empty',
  )
  assert.match(
    source,
    />\s*0|<=\s*0|positive/i,
    'TASK7_RED_WORKFLOW: EDIT_ACCEPTED final quantity must be validated as positive',
  )
})

test('high-risk acceptance and derive controls are permission-gated, not role-invented in the component', () => {
  const detail = requiredSource('../../../../views/maintenance/reviews/ReviewDetail.vue')
  const dialog = requiredSource('../FindingDecisionDialog.vue')
  const combined = `${detail}\n${dialog}`

  assert.match(
    combined,
    /requires_admin_acceptance/,
    'TASK7_RED_WORKFLOW: UI must respect backend high-risk acceptance flag',
  )
  assert.match(
    combined,
    /confirmHighRisk/,
    'TASK7_RED_WORKFLOW: high-risk accept/edit controls must use permission matrix capability',
  )
  assert.match(
    detail,
    /finalizeReview/,
    'TASK7_RED_WORKFLOW: derive/finalize affordance must use finalizeReview permission',
  )
  assert.doesNotMatch(
    combined,
    /role\s*===\s*['"](?:admin|owner)['"]|role\s*!==\s*['"](?:admin|owner)['"]/,
    'TASK7_RED_WORKFLOW: components must not invent direct role checks beside the permission matrix',
  )
})

test('ReviewDetail consumes Task 6 store commands, preserves structured conflicts, confirms derive, and navigates to the derived demand list', () => {
  const source = requiredSource('../../../../views/maintenance/reviews/ReviewDetail.vue')

  for (const contract of [
    /useDemandReviewStore/,
    /fetchReviewDetail/,
    /decideFinding/,
    /batchDecide/,
    /deriveReview/,
    /commandState/,
    /conflicted/,
    /expected_version|expectedVersion/,
    /actual_version|actualVersion/,
    /derived_demand_list_id/,
    /maintenanceDemandListDetail/,
  ]) {
    assert.match(
      source,
      contract,
      `TASK7_RED_WORKFLOW: ReviewDetail is missing ${contract}`,
    )
  }

  assert.match(
    source,
    /DialogPlugin|confirm|confirmation/i,
    'TASK7_RED_WORKFLOW: derive must require an explicit confirmation UI',
  )
  assert.match(
    source,
    /retry|reload|refresh/i,
    'TASK7_RED_WORKFLOW: structured conflict UI must offer a recovery action',
  )
})

test('formal review workspace never imports or calls AI review authority', () => {
  const sources = [
    requiredSource('../../../../views/maintenance/reviews/ReviewDetail.vue'),
    requiredSource('../ReviewSummary.vue'),
    requiredSource('../FindingTable.vue'),
    requiredSource('../FindingDecisionDialog.vue'),
  ].join('\n')

  assert.doesNotMatch(
    sources,
    /AIReviewRun|useAIReview|ai[-_/]?review|\/api\/v1\/ai\/reviews|\/ai\/reviews\/demand-lists/i,
    'TASK7_RED_WORKFLOW: formal review workspace must remain authority-separated from AI review',
  )
})
