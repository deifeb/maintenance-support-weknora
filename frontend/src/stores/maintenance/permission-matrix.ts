export type TenantRole = 'owner' | 'admin' | 'contributor' | 'viewer'

export interface MaintenancePermissions {
  view: boolean
  exportData: boolean
  editMasterData: boolean
  importMasterData: boolean
  runCalculation: boolean
  handleReview: boolean
  reserveInventory: boolean
  issueReturnInventory: boolean
  transferInventory: boolean
  adjustInventory: boolean
  confirmHighRisk: boolean
  freezeInventory: boolean
  reverseInventory: boolean
  createStocktake: boolean
  confirmStocktake: boolean
  publishRules: boolean
  editDemandList: boolean
  publishDemandList: boolean
}

export type MaintenanceAction = keyof MaintenancePermissions

const DENIED_PERMISSIONS: Readonly<MaintenancePermissions> = {
  view: false,
  exportData: false,
  editMasterData: false,
  importMasterData: false,
  runCalculation: false,
  handleReview: false,
  reserveInventory: false,
  issueReturnInventory: false,
  transferInventory: false,
  adjustInventory: false,
  confirmHighRisk: false,
  freezeInventory: false,
  reverseInventory: false,
  createStocktake: false,
  confirmStocktake: false,
  publishRules: false,
  editDemandList: false,
  publishDemandList: false,
}

const VIEWER_PERMISSIONS: Readonly<MaintenancePermissions> = {
  ...DENIED_PERMISSIONS,
  view: true,
  exportData: true,
}

const CONTRIBUTOR_PERMISSIONS: Readonly<MaintenancePermissions> = {
  ...VIEWER_PERMISSIONS,
  editMasterData: true,
  importMasterData: true,
  runCalculation: true,
  handleReview: true,
  reserveInventory: true,
  issueReturnInventory: true,
  createStocktake: true,
  editDemandList: true,
}

const ADMIN_PERMISSIONS: Readonly<MaintenancePermissions> = {
  ...CONTRIBUTOR_PERMISSIONS,
  transferInventory: true,
  adjustInventory: true,
  confirmHighRisk: true,
  freezeInventory: true,
  reverseInventory: true,
  confirmStocktake: true,
  publishRules: true,
  publishDemandList: true,
}

export function isTenantRole(value: unknown): value is TenantRole {
  return (
    value === 'owner'
    || value === 'admin'
    || value === 'contributor'
    || value === 'viewer'
  )
}

export function permissionsForRole(role: TenantRole): MaintenancePermissions {
  if (role === 'owner' || role === 'admin') {
    return { ...ADMIN_PERMISSIONS }
  }

  if (role === 'contributor') {
    return { ...CONTRIBUTOR_PERMISSIONS }
  }

  return { ...VIEWER_PERMISSIONS }
}

export function permissionsForAuth(
  role: unknown,
  hasRole: (minimum: TenantRole) => boolean,
): MaintenancePermissions {
  if (!isTenantRole(role) || !hasRole('viewer')) {
    return { ...DENIED_PERMISSIONS }
  }

  const rolePermissions = permissionsForRole(role)
  const canMaintain = hasRole('contributor')
  const canAdminister = hasRole('admin')

  return {
    view: rolePermissions.view,
    exportData: rolePermissions.exportData,
    editMasterData: rolePermissions.editMasterData && canMaintain,
    importMasterData: rolePermissions.importMasterData && canMaintain,
    runCalculation: rolePermissions.runCalculation && canMaintain,
    handleReview: rolePermissions.handleReview && canMaintain,
    reserveInventory: rolePermissions.reserveInventory && canMaintain,
    issueReturnInventory: rolePermissions.issueReturnInventory && canMaintain,
    transferInventory: rolePermissions.transferInventory && canAdminister,
    adjustInventory: rolePermissions.adjustInventory && canAdminister,
    confirmHighRisk: rolePermissions.confirmHighRisk && canAdminister,
    freezeInventory: rolePermissions.freezeInventory && canAdminister,
    reverseInventory: rolePermissions.reverseInventory && canAdminister,
    createStocktake: rolePermissions.createStocktake && canMaintain,
    confirmStocktake: rolePermissions.confirmStocktake && canAdminister,
    publishRules: rolePermissions.publishRules && canAdminister,
    editDemandList: rolePermissions.editDemandList && canMaintain,
    publishDemandList: (
      rolePermissions.publishDemandList
      && canAdminister
    ),
  }
}
