import type {
  AllocationPlanStatus,
  AllocationRuleStatus,
  AllocationSimulationStatus,
} from '@/api/maintenance/allocations'
import type { DemandListStatus } from '@/api/maintenance/demand-lists'

export interface AllocationWorkflowCapabilities {
  canContribute: boolean
  canPublishRules: boolean
}

export type AllocationRuleUiAction =
  | 'simulate'
  | 'publish'
  | 'retire'

export type AllocationPlanUiAction =
  | 'preview'
  | 'edit-line'
  | 'confirm'
  | 'execute'
  | 'void'
  | 'regenerate'

export interface AllocationRuleMetricInput {
  metric: string
  weight: string
  min: string
  max: string
}

export interface AllocationRuleMetricValidation {
  valid: boolean
  errors: string[]
}

export interface AllocationConflictDisplay {
  code: unknown
  message: unknown
  requestId: unknown
  retryable: unknown
  expectedVersion: unknown
  actualVersion: unknown
  suggestedAction: unknown
  fact: unknown
  regenerate: unknown
}

const WEIGHT_SCALE = 1_000_000n
const WEIGHT_PATTERN =
  /^(0|1)(?:\.(\d{1,6}))?$/
const EXACT_DECIMAL_PATTERN =
  /^(-?)(\d+)(?:\.(\d+))?$/

interface ExactDecimal {
  units: bigint
  scale: number
}

export function allocationRuleActions(
  status: AllocationRuleStatus,
  capabilities: AllocationWorkflowCapabilities,
): AllocationRuleUiAction[] {
  if (!capabilities.canContribute) return []

  if (status === 'DRAFT') {
    return ['simulate']
  }

  if (status === 'SIMULATED') {
    return capabilities.canPublishRules
      ? ['simulate', 'publish']
      : ['simulate']
  }

  if (status === 'PUBLISHED') {
    return capabilities.canPublishRules
      ? ['retire']
      : []
  }

  return []
}

export function allocationPlanActions(
  status: AllocationPlanStatus,
  capabilities: AllocationWorkflowCapabilities,
): AllocationPlanUiAction[] {
  if (!capabilities.canContribute) return []

  if (status === 'DRAFT') {
    return ['preview', 'edit-line', 'void']
  }

  if (status === 'PREVIEWED') {
    return ['preview', 'edit-line', 'confirm', 'void']
  }

  if (status === 'CONFIRMED') {
    return ['execute', 'void']
  }

  if (
    status === 'PARTIALLY_COMPLETED'
    || status === 'FAILED'
  ) {
    return ['regenerate']
  }

  return []
}

export function isAllocationPlanSourceEligible(
  status: DemandListStatus,
  isCurrentPublished: boolean,
): boolean {
  return (
    status === 'CONFIRMED'
    || (
      status === 'PUBLISHED'
      && isCurrentPublished
    )
  )
}

export function isAllocationSimulationTerminal(
  status: AllocationSimulationStatus,
): boolean {
  return (
    status === 'COMPLETED'
    || status === 'FAILED'
    || status === 'CANCELLED'
  )
}

export function positiveAllocationRouteId(
  value: unknown,
): number | null {
  const candidate = Array.isArray(value)
    ? value[0]
    : value

  if (
    typeof candidate !== 'string'
    && typeof candidate !== 'number'
  ) {
    return null
  }

  const parsed = typeof candidate === 'number'
    ? candidate
    : Number(candidate)

  return Number.isInteger(parsed) && parsed > 0
    ? parsed
    : null
}

function parseWeightUnits(
  value: string,
): bigint | null {
  const match = WEIGHT_PATTERN.exec(value)
  if (!match) return null

  const whole = match[1]
  const fraction = (match[2] ?? '').padEnd(6, '0')

  if (
    whole === '1'
    && /[1-9]/.test(fraction)
  ) {
    return null
  }

  return (
    BigInt(whole) * WEIGHT_SCALE
    + BigInt(fraction)
  )
}

function parseExactDecimal(
  value: string,
): ExactDecimal | null {
  const match = EXACT_DECIMAL_PATTERN.exec(value)
  if (!match) return null

  const fraction = match[3] ?? ''
  const magnitude = BigInt(
    `${match[2]}${fraction}`,
  )

  return {
    units: match[1] === '-'
      ? -magnitude
      : magnitude,
    scale: fraction.length,
  }
}

function scaleExactDecimal(
  value: ExactDecimal,
  targetScale: number,
): bigint {
  return (
    value.units
    * 10n ** BigInt(targetScale - value.scale)
  )
}

function compareExactDecimal(
  left: ExactDecimal,
  right: ExactDecimal,
): number {
  const scale = left.scale > right.scale
    ? left.scale
    : right.scale
  const leftUnits = scaleExactDecimal(left, scale)
  const rightUnits = scaleExactDecimal(right, scale)

  if (leftUnits < rightUnits) return -1
  if (leftUnits > rightUnits) return 1
  return 0
}

export function validateAllocationRuleMetrics(
  rows: readonly AllocationRuleMetricInput[],
): AllocationRuleMetricValidation {
  const errors: string[] = []
  const metrics = new Set<string>()
  let weightTotal = 0n

  if (rows.length === 0) {
    errors.push('metrics-required')
  }

  rows.forEach((row, index) => {
    const metric = row.metric.trim()

    if (!metric) {
      errors.push(`metric-required:${index}`)
    } else if (metrics.has(metric)) {
      errors.push(`metric-duplicate:${metric}`)
    } else {
      metrics.add(metric)
    }

    const weightUnits = parseWeightUnits(row.weight)
    if (weightUnits === null) {
      errors.push(`weight-invalid:${index}`)
    } else {
      weightTotal += weightUnits
    }

    const minValue = parseExactDecimal(row.min)
    const maxValue = parseExactDecimal(row.max)

    if (minValue === null || maxValue === null) {
      errors.push(`normalization-invalid:${index}`)
    } else if (
      compareExactDecimal(minValue, maxValue) >= 0
    ) {
      errors.push(`normalization-order:${index}`)
    }
  })

  if (weightTotal !== WEIGHT_SCALE) {
    errors.push('weight-total')
  }

  return {
    valid: errors.length === 0,
    errors,
  }
}

function asRecord(
  value: unknown,
): Record<string, unknown> {
  return (
    typeof value === 'object'
    && value !== null
    && !Array.isArray(value)
  )
    ? value as Record<string, unknown>
    : {}
}

function evidenceValue(
  record: Record<string, unknown>,
  key: string,
): unknown {
  return Object.prototype.hasOwnProperty.call(record, key)
    ? record[key]
    : null
}

export function allocationConflictDisplay(
  error: unknown,
): AllocationConflictDisplay {
  const payload = asRecord(error)
  const details = asRecord(payload.details)

  return {
    code: evidenceValue(payload, 'code'),
    message: evidenceValue(payload, 'message'),
    requestId: evidenceValue(payload, 'request_id'),
    retryable: evidenceValue(payload, 'retryable'),
    expectedVersion: evidenceValue(
      details,
      'expected_version',
    ),
    actualVersion: evidenceValue(
      details,
      'actual_version',
    ),
    suggestedAction: evidenceValue(
      details,
      'suggested_action',
    ),
    fact: evidenceValue(details, 'fact'),
    regenerate: evidenceValue(
      details,
      'regenerate',
    ),
  }
}
