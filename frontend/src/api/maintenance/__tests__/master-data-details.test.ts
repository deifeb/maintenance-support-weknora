import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createMasterDataDetailsApi,
  type DetailApiClient,
} from '../master-data-details.ts'

function recordingClient() {
  const calls: Array<{
    method: 'GET' | 'POST' | 'PUT'
    path: string
    body?: unknown
  }> = []

  const result = {
    data: {},
    meta: {
      request_id: 'r-1',
      tenant_id: 't-1',
    },
  }

  const client: DetailApiClient = {
    get: async (path) => {
      calls.push({ method: 'GET', path })
      return result as never
    },
    post: async (path, body) => {
      calls.push({ method: 'POST', path, body })
      return result as never
    },
    put: async (path, body) => {
      calls.push({ method: 'PUT', path, body })
      return result as never
    },
  }

  return {
    client,
    calls,
  }
}

test('configuration detail uses existing actor-scoped endpoints', async () => {
  const { client, calls } = recordingClient()
  const api = createMasterDataDetailsApi(client)

  await api.getConfigurationTree(12)
  await api.updateConfigurationVersion(12, {
    version_name: 'V2',
  })
  await api.cloneConfigurationVersion(12, {
    version_code: 'V2-DRAFT',
    version_name: 'V2 Draft',
    effective_date: null,
    is_default: false,
  })

  assert.deepEqual(calls, [
    {
      method: 'GET',
      path: '/v1/master-data/configuration-versions/12/tree',
    },
    {
      method: 'PUT',
      path: '/v1/master-data/configuration-versions/12',
      body: {
        version_name: 'V2',
      },
    },
    {
      method: 'POST',
      path: '/v1/master-data/configuration-versions/12/clone',
      body: {
        version_code: 'V2-DRAFT',
        version_name: 'V2 Draft',
        effective_date: null,
        is_default: false,
      },
    },
  ])
})

test('configuration item writes use explicit item endpoints', async () => {
  const { client, calls } = recordingClient()
  const api = createMasterDataDetailsApi(client)

  await api.createConfigurationItem({
    configuration_version_id: 12,
    item_code: 'ROOT',
    parent_item_id: null,
    part_id: 5,
    spare_part_id: null,
    install_quantity: 1,
    position_code: null,
    position_name: null,
    criticality_level: 'MEDIUM',
    replacement_ratio: 1,
    maintenance_level: null,
    is_mandatory: true,
    sort_order: 0,
    notes: null,
  })
  await api.updateConfigurationItem(31, {
    sort_order: 2,
  })

  assert.deepEqual(calls, [
    {
      method: 'POST',
      path: '/v1/master-data/configuration-items',
      body: {
        configuration_version_id: 12,
        item_code: 'ROOT',
        parent_item_id: null,
        part_id: 5,
        spare_part_id: null,
        install_quantity: 1,
        position_code: null,
        position_name: null,
        criticality_level: 'MEDIUM',
        replacement_ratio: 1,
        maintenance_level: null,
        is_mandatory: true,
        sort_order: 0,
        notes: null,
      },
    },
    {
      method: 'PUT',
      path: '/v1/master-data/configuration-items/31',
      body: {
        sort_order: 2,
      },
    },
  ])
})

test('spare-part loaders use only existing filtered endpoints', async () => {
  const { client, calls } = recordingClient()
  const api = createMasterDataDetailsApi(client)

  await api.getSparePart(41)
  await api.listSparePartInventory(41)
  await api.listSparePartReliability(41)
  await api.listSparePartSupply(41)

  assert.deepEqual(
    calls.map((call) => call.path),
    [
      '/v1/master-data/spare-parts/41',
      '/v1/master-data/inventories?page=1&page_size=200&include_inactive=true&sort_by=id&sort_order=asc&spare_part_id=41',
      '/v1/master-data/reliability-profiles?page=1&page_size=200&include_inactive=true&sort_by=id&sort_order=asc&spare_part_id=41',
      '/v1/master-data/supplier-offers?page=1&page_size=200&include_inactive=true&sort_by=id&sort_order=asc&spare_part_id=41',
    ],
  )
})
