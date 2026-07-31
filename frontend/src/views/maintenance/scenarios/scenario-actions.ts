import {
  permissionsForRole,
  type TenantRole,
} from '../../../stores/maintenance/permission-matrix'
import type {
  ScenarioVersionStatus,
} from '../../../api/maintenance/scenarios'

export type ScenarioDraftAction = 'materialize'
export type ScenarioVersionAction =
  | 'edit'
  | 'publish'
  | 'retire'

export function scenarioDraftActions(
  role: TenantRole,
  status: 'READY' | 'BLOCKED',
): ScenarioDraftAction[] {
  const permissions = permissionsForRole(role)
  if (
    status === 'READY'
    && permissions.editMasterData
  ) {
    return ['materialize']
  }
  return []
}

export function scenarioVersionActions(
  role: TenantRole,
  status: ScenarioVersionStatus,
): ScenarioVersionAction[] {
  const permissions = permissionsForRole(role)
  if (status === 'DRAFT') {
    if (
      permissions.confirmHighRisk
      && permissions.publishRules
    ) {
      return ['publish']
    }
    return permissions.editMasterData
      ? ['edit']
      : []
  }
  if (
    status === 'PUBLISHED'
    && permissions.confirmHighRisk
    && permissions.publishRules
  ) {
    return ['retire']
  }
  return []
}
