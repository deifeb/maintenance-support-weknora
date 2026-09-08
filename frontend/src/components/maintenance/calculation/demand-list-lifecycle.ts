import type {
  CalculationGroupStatus,
} from '../../../api/maintenance/calculation-groups'
import type {
  DemandListStatus,
} from '../../../api/maintenance/demand-lists'
import type {
  MaintenancePermissions,
} from '../../../stores/maintenance/permission-matrix'

export type DemandListAction =
  | 'edit'
  | 'submit'
  | 'confirm'
  | 'publish'
  | 'derive'
  | 'void'

export interface DemandListGenerationComparison {
  group_status: CalculationGroupStatus
  rows: ReadonlyArray<{
    decision: unknown | null
    candidates: Readonly<Record<
      string,
      {
        status: 'SUCCEEDED' | 'NO_RESULT'
      }
    >>
  }>
}

const TERMINAL_GROUP_STATUSES:
ReadonlySet<CalculationGroupStatus> = new Set([
  'COMPLETED',
  'PARTIALLY_COMPLETED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
])

export function canOfferDemandListGeneration(
  comparison: DemandListGenerationComparison | null,
  permissions: MaintenancePermissions,
): boolean {
  if (
    !permissions.editDemandList
    || comparison === null
    || !TERMINAL_GROUP_STATUSES.has(
      comparison.group_status,
    )
    || comparison.rows.length === 0
  ) {
    return false
  }

  return comparison.rows.every((row) => (
    row.decision !== null
    && Object.values(row.candidates).some(
      (cell) => cell.status === 'SUCCEEDED',
    )
  ))
}

export function demandListActions(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): DemandListAction[] {
  if (status === 'DRAFT') {
    return permissions.editDemandList
      ? ['edit', 'submit']
      : []
  }

  if (!permissions.publishDemandList) {
    return []
  }

  if (status === 'PENDING_CONFIRMATION') {
    return ['confirm']
  }

  if (status === 'CONFIRMED') {
    return ['publish']
  }

  if (status === 'PUBLISHED') {
    return ['derive', 'void']
  }

  return []
}

export function canEditDemandListItem(
  status: DemandListStatus,
  permissions: MaintenancePermissions,
): boolean {
  return (
    status === 'DRAFT'
    && permissions.editDemandList
  )
}
