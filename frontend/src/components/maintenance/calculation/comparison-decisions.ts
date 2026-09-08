import type {
  ComparisonCandidateCell,
} from '../../../api/maintenance/calculation-groups'

export interface CandidateCellPresentation {
  label: string
  selectable: boolean
  warningCount: number
}

export interface DecisionDraft {
  selectedCandidateKey: string
  systemCandidateKey: string
  finalQuantity: string
  originalQuantity: string
  reason: string
}

export interface DecisionValidation {
  valid: boolean
  reasonRequired: boolean
  quantityValid: boolean
}

function canonicalDecimal(value: string): string | null {
  const match = value.trim().match(
    /^(\d+)(?:\.(\d*))?$/,
  )
  if (!match) return null
  const integer = (
    (match[1] ?? '').replace(/^0+(?=\d)/, '')
    || '0'
  )
  const fraction = (match[2] ?? '').replace(/0+$/, '')
  return fraction ? `${integer}.${fraction}` : integer
}

export function presentCandidateCell(
  cell: ComparisonCandidateCell,
): CandidateCellPresentation {
  const selectable = (
    cell.status === 'SUCCEEDED'
    && cell.recommended_quantity !== null
  )
  return {
    label: selectable
      ? cell.recommended_quantity!
      : 'NO_RESULT',
    selectable,
    warningCount: cell.warnings.length,
  }
}

export function validateDecision(
  draft: DecisionDraft,
): DecisionValidation {
  const quantity = canonicalDecimal(
    draft.finalQuantity,
  )
  const original = canonicalDecimal(
    draft.originalQuantity,
  )
  const quantityValid = quantity !== null
  const reasonRequired = (
    draft.selectedCandidateKey
    !== draft.systemCandidateKey
    || quantity !== original
  )
  return {
    valid: (
      quantityValid
      && (!reasonRequired || draft.reason.trim().length > 0)
    ),
    reasonRequired,
    quantityValid,
  }
}
