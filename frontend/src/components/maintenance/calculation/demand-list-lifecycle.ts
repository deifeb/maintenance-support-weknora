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
