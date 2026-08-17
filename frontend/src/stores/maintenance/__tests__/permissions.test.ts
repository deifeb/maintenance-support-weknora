import test from 'node:test'
import assert from 'node:assert/strict'
import {
  permissionsForAuth,
  permissionsForRole,
  type MaintenancePermissions,
  type TenantRole,
} from '../permission-matrix'

const denied: MaintenancePermissions = {
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

const viewer: MaintenancePermissions = {
  ...denied,
  view: true,
  exportData: true,
}

const contributor: MaintenancePermissions = {
  ...viewer,
  editMasterData: true,
  importMasterData: true,
  runCalculation: true,
  handleReview: true,
  reserveInventory: true,
  issueReturnInventory: true,
  createStocktake: true,
  editDemandList: true,
}

const admin: MaintenancePermissions = {
  ...contributor,
  transferInventory: true,
  adjustInventory: true,
  confirmHighRisk: true,
  freezeInventory: true,
  reverseInventory: true,
  confirmStocktake: true,
  publishRules: true,
  publishDemandList: true,
}

function inventoryGapPermissions(
  permissions: MaintenancePermissions,
) {
  return {
    reserveInventory: permissions.reserveInventory,
    issueReturnInventory: permissions.issueReturnInventory,
    transferInventory: permissions.transferInventory,
    adjustInventory: permissions.adjustInventory,
    confirmHighRisk: permissions.confirmHighRisk,
    freezeInventory: permissions.freezeInventory,
    reverseInventory: permissions.reverseInventory,
    createStocktake: permissions.createStocktake,
    confirmStocktake: permissions.confirmStocktake,
  }
}

test('viewer is read only', () => {
  assert.deepEqual(permissionsForRole('viewer'), viewer)
})

test('contributor can maintain ordinary workflows', () => {
  assert.deepEqual(permissionsForRole('contributor'), contributor)
})

test('owner and admin map to maintenance admin', () => {
  for (const role of ['owner', 'admin'] as const) {
    assert.deepEqual(permissionsForRole(role), admin)
  }
})

test('inventory gap permissions keep viewer read only', () => {
  assert.deepEqual(
    inventoryGapPermissions(permissionsForRole('viewer')),
    {
      reserveInventory: false,
      issueReturnInventory: false,
      transferInventory: false,
      adjustInventory: false,
      confirmHighRisk: false,
      freezeInventory: false,
      reverseInventory: false,
      createStocktake: false,
      confirmStocktake: false,
    },
  )
})

test('inventory gap contributor can create stocktakes only at contributor authority', () => {
  assert.deepEqual(
    inventoryGapPermissions(permissionsForRole('contributor')),
    {
      reserveInventory: true,
      issueReturnInventory: true,
      transferInventory: false,
      adjustInventory: false,
      confirmHighRisk: false,
      freezeInventory: false,
      reverseInventory: false,
      createStocktake: true,
      confirmStocktake: false,
    },
  )
})

test('inventory gap admin and owner receive high-risk authority', () => {
  const expected = {
    reserveInventory: true,
    issueReturnInventory: true,
    transferInventory: true,
    adjustInventory: true,
    confirmHighRisk: true,
    freezeInventory: true,
    reverseInventory: true,
    createStocktake: true,
    confirmStocktake: true,
  }

  for (const role of ['owner', 'admin'] as const) {
    assert.deepEqual(
      inventoryGapPermissions(permissionsForRole(role)),
      expected,
    )
  }
})

test('unknown or unavailable tenant roles fail closed', () => {
  const hasEveryRole = (_minimum: TenantRole) => true

  assert.deepEqual(
    permissionsForAuth('', hasEveryRole),
    denied,
  )
  assert.deepEqual(
    permissionsForAuth(undefined, hasEveryRole),
    denied,
  )
})

test('auth hierarchy can reduce a recognized role to read only', () => {
  const viewerOnly = (minimum: TenantRole) => minimum === 'viewer'

  assert.deepEqual(
    permissionsForAuth('contributor', viewerOnly),
    viewer,
  )
})

test('auth hierarchy removes demand-list admin authority', () => {
  const contributorOnly = (
    minimum: TenantRole,
  ): boolean => (
    minimum === 'viewer'
    || minimum === 'contributor'
  )

  assert.deepEqual(
    permissionsForAuth('admin', contributorOnly),
    contributor,
  )
})
