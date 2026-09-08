import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

const workflowUrl =
  new URL('../allocation-workflow.ts', import.meta.url)
const workflowPresent = existsSync(workflowUrl)

async function loadWorkflow(): Promise<Record<string, any>> {
  return import(workflowUrl.href)
}

function sourceUrl(relative: string): URL {
  return new URL(relative, import.meta.url)
}

function sourceExists(relative: string): boolean {
  return existsSync(sourceUrl(relative))
}

function source(relative: string): string {
  return readFileSync(sourceUrl(relative), 'utf8')
}

test('allocation workflow production helper is present', () => {
  assert.equal(
    workflowPresent,
    true,
    'TASK8_RED_WORKFLOW: Task 8 GREEN A must create allocation-workflow.ts',
  )
})

test(
  'allocation rule actions mirror contributor and publish capabilities',
  { skip: !workflowPresent },
  async () => {
    const { allocationRuleActions } = await loadWorkflow()

    assert.deepEqual(
      allocationRuleActions(
        'DRAFT',
        { canContribute: true, canPublishRules: false },
      ),
      ['simulate'],
    )

    assert.deepEqual(
      allocationRuleActions(
        'SIMULATED',
        { canContribute: true, canPublishRules: true },
      ),
      ['simulate', 'publish'],
    )

    assert.deepEqual(
      allocationRuleActions(
        'PUBLISHED',
        { canContribute: true, canPublishRules: true },
      ),
      ['retire'],
    )

    assert.deepEqual(
      allocationRuleActions(
        'PUBLISHED',
        { canContribute: true, canPublishRules: false },
      ),
      [],
    )

    assert.deepEqual(
      allocationRuleActions(
        'DRAFT',
        { canContribute: false, canPublishRules: true },
      ),
      [],
    )
  },
)

test(
  'allocation plan actions mirror the backend lifecycle',
  { skip: !workflowPresent },
  async () => {
    const { allocationPlanActions } = await loadWorkflow()
    const contributor = {
      canContribute: true,
      canPublishRules: false,
    }

    assert.deepEqual(
      allocationPlanActions('DRAFT', contributor),
      ['preview', 'edit-line', 'void'],
    )
    assert.deepEqual(
      allocationPlanActions('PREVIEWED', contributor),
      ['preview', 'edit-line', 'confirm', 'void'],
    )
    assert.deepEqual(
      allocationPlanActions('CONFIRMED', contributor),
      ['execute', 'void'],
    )
    assert.deepEqual(
      allocationPlanActions('PARTIALLY_COMPLETED', contributor),
      ['regenerate'],
    )
    assert.deepEqual(
      allocationPlanActions('FAILED', contributor),
      ['regenerate'],
    )

    for (const status of [
      'EXECUTING',
      'COMPLETED',
      'VOIDED',
    ] as const) {
      assert.deepEqual(
        allocationPlanActions(status, contributor),
        [],
      )
    }

    assert.deepEqual(
      allocationPlanActions(
        'DRAFT',
        { canContribute: false, canPublishRules: false },
      ),
      [],
    )
  },
)

test(
  'allocation source eligibility mirrors confirmed or current published demand lists',
  { skip: !workflowPresent },
  async () => {
    const {
      isAllocationPlanSourceEligible,
    } = await loadWorkflow()

    assert.equal(
      isAllocationPlanSourceEligible('CONFIRMED', false),
      true,
    )
    assert.equal(
      isAllocationPlanSourceEligible('PUBLISHED', true),
      true,
    )
    assert.equal(
      isAllocationPlanSourceEligible('PUBLISHED', false),
      false,
    )
    assert.equal(
      isAllocationPlanSourceEligible('DRAFT', true),
      false,
    )
  },
)

test(
  'allocation simulation terminal predicate stops only completed failed or cancelled',
  { skip: !workflowPresent },
  async () => {
    const {
      isAllocationSimulationTerminal,
    } = await loadWorkflow()

    assert.equal(
      isAllocationSimulationTerminal('PENDING'),
      false,
    )
    assert.equal(
      isAllocationSimulationTerminal('RUNNING'),
      false,
    )
    assert.equal(
      isAllocationSimulationTerminal('COMPLETED'),
      true,
    )
    assert.equal(
      isAllocationSimulationTerminal('FAILED'),
      true,
    )
    assert.equal(
      isAllocationSimulationTerminal('CANCELLED'),
      true,
    )
  },
)

test(
  'positive allocation route id accepts only positive integer identifiers',
  { skip: !workflowPresent },
  async () => {
    const {
      positiveAllocationRouteId,
    } = await loadWorkflow()

    assert.equal(positiveAllocationRouteId('17'), 17)
    assert.equal(positiveAllocationRouteId(['19']), 19)
    assert.equal(positiveAllocationRouteId(23), 23)

    for (const invalid of [
      '0',
      '-1',
      '1.5',
      '',
      'abc',
      undefined,
      null,
    ]) {
      assert.equal(
        positiveAllocationRouteId(invalid),
        null,
      )
    }
  },
)

test(
  'allocation rule metric validation sums weights exactly without floating point',
  { skip: !workflowPresent },
  async () => {
    const {
      validateAllocationRuleMetrics,
    } = await loadWorkflow()

    const valid = validateAllocationRuleMetrics([
      {
        metric: 'availability',
        weight: '0.600000',
        min: '0',
        max: '100',
      },
      {
        metric: 'criticality',
        weight: '0.400000',
        min: '0',
        max: '4',
      },
    ])

    assert.equal(valid.valid, true)
    assert.deepEqual(valid.errors, [])

    const wrongTotal = validateAllocationRuleMetrics([
      {
        metric: 'availability',
        weight: '0.600000',
        min: '0',
        max: '100',
      },
      {
        metric: 'criticality',
        weight: '0.399999',
        min: '0',
        max: '4',
      },
    ])

    assert.equal(wrongTotal.valid, false)
  },
)

test(
  'allocation rule metric validation rejects malformed weights duplicate metrics and invalid normalization order',
  { skip: !workflowPresent },
  async () => {
    const {
      validateAllocationRuleMetrics,
    } = await loadWorkflow()

    const invalidCases = [
      [
        {
          metric: 'availability',
          weight: '1.000001',
          min: '0',
          max: '100',
        },
      ],
      [
        {
          metric: 'availability',
          weight: '-0.1',
          min: '0',
          max: '100',
        },
      ],
      [
        {
          metric: 'availability',
          weight: '0.1234567',
          min: '0',
          max: '100',
        },
        {
          metric: 'criticality',
          weight: '0.8765433',
          min: '0',
          max: '4',
        },
      ],
      [
        {
          metric: 'availability',
          weight: '0.500000',
          min: '0',
          max: '100',
        },
        {
          metric: 'availability',
          weight: '0.500000',
          min: '0',
          max: '100',
        },
      ],
      [
        {
          metric: '   ',
          weight: '1.000000',
          min: '0',
          max: '100',
        },
      ],
      [
        {
          metric: 'availability',
          weight: '1.000000',
          min: '1',
          max: '1',
        },
      ],
      [
        {
          metric: 'availability',
          weight: '1.000000',
          min: '2',
          max: '1',
        },
      ],
    ]

    for (const rows of invalidCases) {
      const result =
        validateAllocationRuleMetrics(rows)

      assert.equal(
        result.valid,
        false,
        `expected invalid rows: ${JSON.stringify(rows)}`,
      )
      assert.ok(result.errors.length > 0)
    }

    const negativeBounds =
      validateAllocationRuleMetrics([
        {
          metric: 'temperature',
          weight: '1.000000',
          min: '-1000000000000000000000.0002',
          max: '-999999999999999999999.9999',
        },
      ])

    assert.equal(negativeBounds.valid, true)
  },
)

test(
  'allocation conflict display preserves structured server evidence',
  { skip: !workflowPresent },
  async () => {
    const {
      allocationConflictDisplay,
    } = await loadWorkflow()

    const error = {
      status: 409,
      code: 'ALLOCATION_INVENTORY_CONFLICT',
      message: 'inventory changed',
      request_id: 'request-20',
      retryable: false,
      details: {
        fact: 'balance',
        expected_version: 7,
        actual_version: 8,
        suggested_action: 'regenerate',
        regenerate:
          '/api/v1/allocations/plans/3/regenerate',
      },
    }

    const display = allocationConflictDisplay(error)

    assert.deepEqual(display, {
      code: 'ALLOCATION_INVENTORY_CONFLICT',
      message: 'inventory changed',
      requestId: 'request-20',
      retryable: false,
      expectedVersion: 7,
      actualVersion: 8,
      suggestedAction: 'regenerate',
      fact: 'balance',
      regenerate:
        '/api/v1/allocations/plans/3/regenerate',
    })

    assert.equal(error.details.expected_version, 7)
  },
)

test(
  'allocation workflow source never converts business decimals through floating point',
  { skip: !workflowPresent },
  () => {
    const workflowSource = source(
      '../allocation-workflow.ts',
    )

    assert.doesNotMatch(
      workflowSource,
      /\bparseFloat\s*\(/,
    )
    assert.doesNotMatch(
      workflowSource,
      /\bNumber\s*\(\s*(?:weight|quantity|min|max)\b/i,
    )
    assert.doesNotMatch(
      workflowSource,
      /(?:weight|quantity|min|max)\s*=\s*\+\s*/i,
    )
    assert.match(
      workflowSource,
      /\bBigInt\s*\(/,
      'weights must use exact integer/BigInt arithmetic',
    )
  },
)

const ruleEditorPath = '../RuleEditor.vue'
const ruleEditorPresent =
  workflowPresent && sourceExists(ruleEditorPath)

test(
  'RuleEditor keeps allocation draft construction exact and tenant-free',
  { skip: !ruleEditorPresent },
  () => {
    const editor = source(ruleEditorPath)

    for (const token of [
      'exclude_frozen',
      'exclude_expired',
      'require_available',
      'lineage_id',
      'change_reason',
      'weights',
      'normalization',
    ]) {
      assert.match(editor, new RegExp(`\\b${token}\\b`))
    }

    assert.match(editor, /JSON\.parse/)
    assert.doesNotMatch(editor, /\btenant_id\b|\btenantId\b/)
    assert.doesNotMatch(editor, /\bparseFloat\s*\(/)
  },
)

const ruleListPath =
  '../../../../views/maintenance/inventory-gap/AllocationRuleList.vue'
const ruleListPresent =
  workflowPresent && sourceExists(ruleListPath)

test(
  'AllocationRuleList delegates writes and polling to Task 7 state authorities',
  { skip: !ruleListPresent },
  () => {
    const page = source(ruleListPath)

    for (const token of [
      'useAllocationStore',
      'useMaintenancePermissionsStore',
      'useAllocationSimulationPolling',
      'fetchRules',
      'createRule',
      'simulateRule',
      'publishRule',
      'retireRule',
    ]) {
      assert.match(page, new RegExp(`\\b${token}\\b`))
    }

    assert.doesNotMatch(page, /\ballocationApi\s*\./)
    assert.doesNotMatch(page, /\bIdempotency-Key\b/)
    assert.doesNotMatch(
      page,
      /\bEventSource\b|useResumableSSE|fetch-event-source/,
    )
  },
)

const planDetailPath =
  '../../../../views/maintenance/inventory-gap/AllocationPlanDetail.vue'
const planDetailPresent =
  workflowPresent && sourceExists(planDetailPath)

test(
  'AllocationPlanDetail refreshes authoritative parent state after a successful line edit',
  { skip: !planDetailPresent },
  () => {
    const page = source(planDetailPath)

    assert.match(page, /\buseAllocationStore\b/)
    assert.match(
      page,
      /await\s+allocationStore\.editPlanLine[\s\S]{0,1200}?await\s+allocationStore\.fetchPlanDetail/,
      'successful line edit must be followed by an authoritative plan GET',
    )
    assert.match(page, /\bpreviewPlan\b/)
    assert.match(page, /\bconfirmPlan\b/)
    assert.match(page, /\bexecutePlan\b/)
    assert.match(page, /\bvoidPlan\b/)
    assert.match(page, /\bregeneratePlan\b/)
    assert.doesNotMatch(
      page,
      /@\/api\/maintenance\/inventory|\breserveForAllocation\b|\bcreateReservation\b/,
    )
    assert.doesNotMatch(page, /\bIdempotency-Key\b/)
  },
)

const planTablePath = '../AllocationPlanTable.vue'
const planTablePresent =
  workflowPresent && sourceExists(planTablePath)

test(
  'AllocationPlanTable renders authoritative gaps risks identities and line versions',
  { skip: !planTablePresent },
  () => {
    const table = source(planTablePath)

    for (const token of [
      'demand_quantity',
      'allocated_quantity',
      'gap_quantity',
      'recommended_balance_id',
      'recommended_lot_id',
      'recommended_serial_item_id',
      'expected_balance_version',
      'risks',
      'manual_override',
      'reservation_id',
      'result',
      'version',
    ]) {
      assert.match(table, new RegExp(`\\b${token}\\b`))
    }

    assert.match(table, /\bedit\b/)
    assert.doesNotMatch(table, /\bparseFloat\s*\(/)
  },
)

const executionSummaryPath =
  '../PlanExecutionSummary.vue'
const executionSummaryPresent =
  workflowPresent && sourceExists(executionSummaryPath)

test(
  'PlanExecutionSummary renders server outcomes conflicts and regenerate recovery',
  { skip: !executionSummaryPresent },
  () => {
    const summary = source(executionSummaryPath)

    for (const token of [
      'execution_id',
      'execution_as_of',
      'line_results',
      'outcome',
      'reservation_id',
      'error_code',
      'cause_code',
      'retryable',
      'suggested_action',
      'details',
      'regenerate',
    ]) {
      assert.match(summary, new RegExp(`\\b${token}\\b`))
    }
  },
)

const inventoryGapPath =
  '../../../../views/maintenance/inventory-gap/InventoryGapPage.vue'
const inventoryGapAllocationReady =
  workflowPresent && sourceExists(inventoryGapPath)

test(
  'InventoryGapPage preserves five inventory tabs and adds Store-backed allocation assurance entry points',
  { skip: !inventoryGapAllocationReady },
  () => {
    const page = source(inventoryGapPath)

    assert.match(page, /\bINVENTORY_WORKSPACE_TABS\b/)
    assert.match(page, /\buseAllocationStore\b/)
    assert.match(page, /\buseDemandListStore\b/)
    assert.match(page, /\bfetchPlans\b/)
    assert.match(page, /\bcreatePlan\b/)
    assert.match(page, /\bmaintenanceAllocationRules\b/)
    assert.match(page, /\bmaintenanceAllocationPlanDetail\b/)
    assert.doesNotMatch(page, /\bIdempotency-Key\b/)
  },
)

const simulationComparisonPath =
  '../SimulationComparison.vue'
const simulationComparisonPresent =
  workflowPresent && sourceExists(simulationComparisonPath)

test(
  'SimulationComparison renders only public simulation summary evidence',
  { skip: !simulationComparisonPresent },
  () => {
    const comparison = source(
      simulationComparisonPath,
    )

    for (const token of [
      'status',
      'progress',
      'total_rows',
      'demand_item_count',
      'high_priority_regression',
      'blockers',
      'completed_at',
      'error_code',
      'error_summary',
    ]) {
      assert.match(
        comparison,
        new RegExp(`\\b${token}\\b`),
      )
    }

    assert.doesNotMatch(
      comparison,
      /\bbaseline_rank\b|\bcandidate_rank\b|\bcandidate_score\b/,
    )
  },
)
