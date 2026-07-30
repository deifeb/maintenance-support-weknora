import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  AVAILABLE_MASTER_DATA_RESOURCES,
  MASTER_DATA_RESOURCE_LIST,
  visibleMasterDataTransferActions,
} from '../../../components/maintenance/master-data/MasterDataRegistry.ts'
import { maintenanceRouteRecords } from '../../../router/maintenance.ts'
import { maintenanceMenuChildren } from '../../../stores/maintenance/menu-definition.ts'
import { permissionsForRole } from '../../../stores/maintenance/permission-matrix.ts'

const viewer = permissionsForRole('viewer')
const contributor = permissionsForRole('contributor')
const admin = permissionsForRole('admin')

function actionKeys(
  resource: typeof AVAILABLE_MASTER_DATA_RESOURCES[number],
  permissions: typeof viewer,
): string[] {
  const actions = resource.actions(permissions).map((action) => action.key)
  if (resource.availability === 'available'
    && resource.operations.create
    && permissions[resource.writeCapability]) {
    actions.push('create')
  }
  return actions
}

test('visible Maintenance menu entries agree with route records while detail routes stay hidden', () => {
  const children = maintenanceRouteRecords[0].children ?? []
  const visibleRouteNames = children
    .filter((route) => route.meta?.hideInMaintenanceMenu !== true)
    .map((route) => route.name)

  assert.deepEqual(
    maintenanceMenuChildren.map((entry) => entry.routeName),
    visibleRouteNames,
  )

  assert.deepEqual(
    children
      .filter((route) => route.meta?.hideInMaintenanceMenu === true)
      .map((route) => route.name),
    ['maintenanceConfigurationDetail', 'maintenanceSparePartDetail'],
  )
})

test('every Maintenance route requires authenticated initialized access', () => {
  const parent = maintenanceRouteRecords[0]
  const routes = [parent, ...(parent.children ?? [])]

  assert.ok(routes.every((route) => (
    route.meta?.requiresAuth === true
    && route.meta?.requiresInit === true
  )))
})

test('viewer on an available resource can view rows and transfer templates or exports only', () => {
  const resource = AVAILABLE_MASTER_DATA_RESOURCES.find(
    ({ key }) => key === 'parts',
  )
  assert.ok(resource)

  assert.deepEqual(actionKeys(resource, viewer), ['view'])
  assert.deepEqual(
    visibleMasterDataTransferActions(resource, viewer),
    ['template', 'export'],
  )
})

test('contributor has standard available-resource create edit deactivate import and export capabilities', () => {
  const resource = AVAILABLE_MASTER_DATA_RESOURCES.find(
    ({ key }) => key === 'parts',
  )
  assert.ok(resource)

  assert.deepEqual(actionKeys(resource, contributor), [
    'view',
    'edit',
    'deactivate',
    'create',
  ])
  assert.deepEqual(
    visibleMasterDataTransferActions(resource, contributor),
    ['template', 'export', 'import'],
  )
})

test('admin includes contributor behavior while inventory edits use adjustInventory and imports use editMasterData', () => {
  const standard = AVAILABLE_MASTER_DATA_RESOURCES.find(
    ({ key }) => key === 'parts',
  )
  const inventory = AVAILABLE_MASTER_DATA_RESOURCES.find(
    ({ key }) => key === 'inventorySummaries',
  )
  assert.ok(standard)
  assert.ok(inventory)

  assert.deepEqual(actionKeys(standard, admin), actionKeys(standard, contributor))
  assert.equal(inventory.writeCapability, 'adjustInventory')
  assert.deepEqual(actionKeys(inventory, contributor), ['view'])
  assert.deepEqual(actionKeys(inventory, admin), ['view', 'edit', 'create'])
  assert.deepEqual(
    visibleMasterDataTransferActions(inventory, contributor),
    ['template', 'export', 'import'],
  )
  assert.deepEqual(
    visibleMasterDataTransferActions(inventory, admin),
    ['template', 'export', 'import'],
  )
})

test('planned resources expose neither row writes nor transfer actions', () => {
  const planned = MASTER_DATA_RESOURCE_LIST.filter(
    (resource) => resource.availability === 'planned',
  )
  assert.ok(planned.length > 0)

  for (const resource of planned) {
    assert.deepEqual(actionKeys(resource, admin), ['view'])
    assert.deepEqual(visibleMasterDataTransferActions(resource, admin), [])
  }
})

test('browser-facing transfer code contains no tenant selector, Maintenance base URL, or internal signing secret', () => {
  const transferSources = [
    new URL('../../../api/maintenance/imports.ts', import.meta.url),
    new URL('../master-data/master-data-transfer-actions.ts', import.meta.url),
    new URL('../master-data/MasterDataListPage.vue', import.meta.url),
  ].map((url) => readFileSync(url, 'utf8')).join('\n')
  const clientSource = readFileSync(
    new URL('../../../api/maintenance/client.ts', import.meta.url),
    'utf8',
  )

  assert.doesNotMatch(transferSources, /tenant[_-]?id/i)
  assert.doesNotMatch(clientSource, /https?:\/\/[^'"\s]+:8100/i)
  assert.doesNotMatch(
    `${transferSources}\n${clientSource}`,
    /INTERNAL_JWT_SECRET|WEKNORA_MAINTENANCE_SIGNING_SECRET/,
  )
})
