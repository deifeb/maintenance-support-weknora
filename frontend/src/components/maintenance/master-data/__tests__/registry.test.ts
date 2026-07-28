import assert from 'node:assert/strict'
import test from 'node:test'

import { permissionsForRole } from '../../../../stores/maintenance/permission-matrix.ts'
import {
  AVAILABLE_MASTER_DATA_RESOURCES,
  MASTER_DATA_RESOURCE_KEYS,
  MASTER_DATA_RESOURCES,
  serializeMasterDataForm,
} from '../MasterDataRegistry.ts'
import { createMasterDataApi } from '../../../../api/maintenance/master-data.ts'

const expectedResourceKeys = [
  'equipmentModels',
  'configurations',
  'parts',
  'spareParts',
  'reliabilityProfiles',
  'warehouses',
  'inventorySummaries',
  'suppliers',
  'supplierOffers',
  'failureModes',
  'maintenanceActivities',
  'substitutions',
  'kitRules',
  'lots',
  'serialItems',
]

test('registry defines every planned master data resource', () => {
  assert.deepEqual(MASTER_DATA_RESOURCE_KEYS, expectedResourceKeys)
  assert.equal(Object.keys(MASTER_DATA_RESOURCES).length, 15)
})

test('standard resources expose endpoint, key and editable fields', () => {
  const spare = MASTER_DATA_RESOURCES.spareParts

  assert.equal(spare.endpoint, '/v1/master-data/spare-parts')
  assert.equal(spare.rowKey, 'id')
  assert.ok(spare.columns.some((column) => column.key === 'code'))
  assert.ok(spare.form.some((field) => field.key === 'criticality'))
})

test('available registry entries match current backend master data routes', () => {
  assert.deepEqual(
    AVAILABLE_MASTER_DATA_RESOURCES.map((resource) => resource.key),
    [
      'equipmentModels',
      'configurations',
      'parts',
      'spareParts',
      'reliabilityProfiles',
      'warehouses',
      'inventorySummaries',
      'suppliers',
      'supplierOffers',
    ],
  )
  assert.ok(
    AVAILABLE_MASTER_DATA_RESOURCES.every(
      (resource) => resource.endpoint.startsWith('/v1/master-data/'),
    ),
  )
})

test('planned resources never expose write operations', () => {
  const planned = MASTER_DATA_RESOURCE_KEYS
    .map((key) => MASTER_DATA_RESOURCES[key])
    .filter((resource) => resource.availability === 'planned')

  assert.equal(planned.length, 6)
  for (const resource of planned) {
    assert.deepEqual(resource.operations, {
      list: false,
      create: false,
      update: false,
      deactivate: false,
    })
  }
})

test('viewer actions never include writes', () => {
  const permissions = permissionsForRole('viewer')

  for (const resource of Object.values(MASTER_DATA_RESOURCES)) {
    assert.equal(
      resource.actions(permissions).some((action) => action.kind !== 'view'),
      false,
    )
  }
})

test('contributor actions follow backend resource capabilities', () => {
  const permissions = permissionsForRole('contributor')

  assert.deepEqual(
    MASTER_DATA_RESOURCES.spareParts
      .actions(permissions)
      .map((action) => action.kind),
    ['view', 'edit', 'deactivate'],
  )
  assert.deepEqual(
    MASTER_DATA_RESOURCES.configurations
      .actions(permissions)
      .map((action) => action.kind),
    ['view', 'edit'],
  )
  assert.deepEqual(
    MASTER_DATA_RESOURCES.failureModes
      .actions(permissions)
      .map((action) => action.kind),
    ['view'],
  )
})

test('inventory writes require adjust inventory capability', () => {
  const contributor = permissionsForRole('contributor')
  const admin = permissionsForRole('admin')
  const inventory = MASTER_DATA_RESOURCES.inventorySummaries

  assert.equal(contributor.editMasterData, true)
  assert.equal(contributor.adjustInventory, false)
  assert.deepEqual(
    inventory.actions(contributor).map((action) => action.kind),
    ['view'],
  )
  assert.equal(inventory.writeCapability, 'adjustInventory')
  assert.deepEqual(
    inventory.actions(admin).map((action) => action.kind),
    ['view', 'edit'],
  )
})

test('form serialization maps UI aliases and omits create-only fields on edit', () => {
  const resource = MASTER_DATA_RESOURCES.spareParts
  const values = {
    code: 'SP-001',
    name: 'Bearing',
    criticality: true,
    is_active: true,
  }

  assert.deepEqual(
    serializeMasterDataForm(resource, values, 'create'),
    {
      code: 'SP-001',
      name: 'Bearing',
      is_critical: true,
      is_active: true,
    },
  )
  assert.deepEqual(
    serializeMasterDataForm(resource, values, 'edit'),
    {
      name: 'Bearing',
      is_critical: true,
      is_active: true,
    },
  )
})

test('master data API builds the backend paging query once', async () => {
  const calls: string[] = []
  const api = createMasterDataApi({
    async get<T>(path: string) {
      calls.push(path)
      return {
        data: {
          items: [],
          page: 2,
          page_size: 50,
          total: 0,
          pages: 0,
        } as T,
        meta: {
          request_id: 'req-1',
          tenant_id: 'tenant-1',
        },
      }
    },
    async post<T>() {
      throw new Error('not used') as never
    },
    async put<T>() {
      throw new Error('not used') as never
    },
    async patch<T>() {
      throw new Error('not used') as never
    },
  })

  await api.list(MASTER_DATA_RESOURCES.parts, {
    page: 2,
    page_size: 50,
    keyword: 'pump',
    include_inactive: true,
    sort_by: 'name',
    sort_order: 'desc',
  })

  assert.deepEqual(calls, [
    '/v1/master-data/parts?page=2&page_size=50&keyword=pump&include_inactive=true&sort_by=name&sort_order=desc',
  ])
})
