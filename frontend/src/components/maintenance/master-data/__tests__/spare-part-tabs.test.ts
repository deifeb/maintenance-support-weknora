import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import * as overviewModel from '../SparePartOverview'
import { SPARE_PART_TABS } from '../SparePartOverview'
import {
  createLazyDetailTabs,
} from '../../../../composables/maintenance/useLazyDetailTabs'

test('spare part detail exposes approved information architecture', () => {
  assert.deepEqual(
    SPARE_PART_TABS.map((tab) => tab.key),
    [
      'overview',
      'applicability',
      'inventory',
      'lotsSerials',
      'substitutions',
      'kitRules',
      'reliability',
      'supply',
      'evidence',
      'audit',
    ],
  )
})

test('only currently supported tabs declare loaders', () => {
  assert.deepEqual(
    SPARE_PART_TABS
      .filter((tab) => tab.availability === 'available')
      .map((tab) => tab.key),
    ['overview', 'inventory', 'reliability', 'supply'],
  )
})

test('a loaded tab is retained and not requested twice', async () => {
  let calls = 0
  const tabs = createLazyDetailTabs({
    overview: async () => {
      calls += 1
      return { id: 1 }
    },
  })

  await tabs.activate('overview')
  await tabs.activate('overview')

  assert.equal(calls, 1)
  assert.equal(tabs.state('overview').status, 'loaded')
  assert.deepEqual(tabs.state('overview').data, { id: 1 })
})

test('error state is retained and retry is explicit', async () => {
  let calls = 0
  const tabs = createLazyDetailTabs({
    inventory: async () => {
      calls += 1
      if (calls === 1) {
        throw new Error('temporary')
      }
      return ['ok']
    },
  })

  await tabs.activate('inventory')
  assert.equal(tabs.state('inventory').status, 'error')

  await tabs.retry('inventory')
  assert.equal(tabs.state('inventory').status, 'loaded')
  assert.equal(calls, 2)
})

test('unavailable tabs do not call a network loader', async () => {
  const tabs = createLazyDetailTabs(
    {},
    ['applicability'],
  )

  await tabs.activate('applicability')

  assert.equal(tabs.state('applicability').status, 'unavailable')
})

test('invalidate clears only the selected loaded tab', async () => {
  let calls = 0
  const tabs = createLazyDetailTabs({
    overview: async () => {
      calls += 1
      return { id: calls }
    },
    inventory: async () => ['kept'],
  })

  await tabs.activate('overview')
  await tabs.activate('inventory')
  tabs.invalidate('overview')

  assert.equal(tabs.state('overview').status, 'idle')
  assert.equal(tabs.state('inventory').status, 'loaded')

  await tabs.activate('overview')
  assert.equal(calls, 2)
})

test('reset prevents an old request from overwriting a new record', async () => {
  let resolveOld!: (value: unknown) => void
  const oldPromise = new Promise<unknown>((resolve) => {
    resolveOld = resolve
  })

  const tabs = createLazyDetailTabs({
    overview: async () => oldPromise,
  })

  const pending = tabs.activate('overview')
  tabs.reset()
  resolveOld({ id: 1 })
  await pending

  assert.equal(tabs.state('overview').status, 'idle')
  assert.equal(tabs.state('overview').data, null)
})


test(
  'available spare-part presenters aggregate decimals and expose populated reliability parameters',
  () => {
    const helpers = overviewModel as Record<string, unknown>

    assert.equal(typeof helpers.numeric, 'function')
    assert.equal(typeof helpers.summarizeInventory, 'function')
    assert.equal(typeof helpers.reliabilityParameterEntries, 'function')

    const numeric = helpers.numeric as (
      value: number | string | null,
    ) => number
    const summarizeInventory = helpers.summarizeInventory as (
      rows: Array<Record<string, unknown>>,
    ) => Record<string, number>
    const reliabilityParameterEntries =
      helpers.reliabilityParameterEntries as (
        row: Record<string, unknown>,
      ) => Array<{ key: string; value: unknown }>

    assert.equal(numeric(null), 0)
    assert.equal(numeric('2.5'), 2.5)
    assert.equal(numeric('not-a-number'), 0)

    assert.deepEqual(
      summarizeInventory([
        {
          on_hand_quantity: '10.5',
          available_quantity: '8.25',
          reserved_quantity: '2',
          damaged_quantity: null,
          quarantined_quantity: 'not-a-number',
          in_transit_quantity: 1,
        },
        {
          on_hand_quantity: 2,
          available_quantity: 1,
          reserved_quantity: 0,
          damaged_quantity: '0.5',
          quarantined_quantity: 0,
          in_transit_quantity: '3',
        },
      ]),
      {
        onHand: 12.5,
        available: 9.25,
        reserved: 2,
        damaged: 0.5,
        quarantined: 0,
        inTransit: 4,
      },
    )

    assert.deepEqual(
      reliabilityParameterEntries({
        failure_rate: '0.01',
        mtbf_hours: null,
      }).map(({ key, value }) => ({ key, value })),
      [
        {
          key: 'failure_rate',
          value: '0.01',
        },
      ],
    )
  },
)

test(
  'available spare-part components remain presentational and expose approved fields',
  () => {
    const contracts = [
      {
        file: '../SparePartOverview.vue',
        fields: [
          'code',
          'name',
          'specification',
          'category',
          'unit',
          'manufacturer',
          'material_code',
          'national_standard',
          'shelf_life_months',
          'is_serialized',
          'is_repairable',
          'is_critical',
          'default_service_level',
          'description',
          'is_active',
          'updated_at',
        ],
      },
      {
        file: '../SparePartInventory.vue',
        fields: [
          'on_hand_quantity',
          'available_quantity',
          'reserved_quantity',
          'damaged_quantity',
          'quarantined_quantity',
          'in_transit_quantity',
          'warehouse_id',
          'reorder_point',
          'safety_stock',
          'last_counted_at',
        ],
      },
      {
        file: '../SparePartReliability.vue',
        fields: [
          'profile_code',
          'model_type',
          'data_source_type',
          'data_source_reference',
          'sample_size',
          'confidence_level',
          'valid_from',
          'valid_to',
          'is_active',
        ],
      },
      {
        file: '../SparePartSupply.vue',
        fields: [
          'offer_code',
          'supplier_id',
          'unit_price',
          'currency',
          'lead_time_days',
          'minimum_order_quantity',
          'order_multiple',
          'maximum_supply_quantity',
          'warranty_months',
          'quality_level',
          'is_preferred',
          'valid_from',
          'valid_to',
          'is_active',
        ],
      },
    ]

    for (const contract of contracts) {
      const source = readFileSync(
        fileURLToPath(new URL(contract.file, import.meta.url)),
        'utf8',
      )

      assert.match(source, /defineProps/)
      for (const field of contract.fields) {
        assert.match(source, new RegExp(field))
      }

      for (const forbidden of [
        'masterDataDetailsApi',
        'maintenanceGet',
        'maintenancePost',
        'maintenancePut',
        '/v1/',
        'tenant_id',
      ]) {
        assert.equal(source.includes(forbidden), false)
      }
    }

    const inventorySource = readFileSync(
      fileURLToPath(
        new URL('../SparePartInventory.vue', import.meta.url),
      ),
      'utf8',
    )

    for (const forbiddenAction of [
      '调整库存',
      '调拨',
      '领用',
      '退库',
    ]) {
      assert.equal(inventorySource.includes(forbiddenAction), false)
    }
  },
)


test(
  'unavailable spare-part tabs explain missing contracts without guessed requests',
  () => {
    const sharedSource = readFileSync(
      fileURLToPath(
        new URL('../SparePartUnavailablePanel.vue', import.meta.url),
      ),
      'utf8',
    )

    for (const copy of [
      '当前接口未开放',
      '当前 Maintenance API 路由表未提供该备件的',
      '本页签不构造替代数据，也不会发起猜测请求。',
    ]) {
      assert.equal(sharedSource.includes(copy), true)
    }

    const contracts = [
      {
        file: '../SparePartApplicability.vue',
        domain: '适用性',
        reason:
          '当前没有按 spare_part_id 查询配置适用关系的端点。',
      },
      {
        file: '../SparePartLotsSerials.vue',
        domain: '批次/序列号',
        reason:
          '当前 master-data router 未注册 lots 或 serial-items 端点。',
      },
      {
        file: '../SparePartSubstitutions.vue',
        domain: '替代关系',
        reason:
          '当前 master-data router 未注册 substitutions 端点。',
      },
      {
        file: '../SparePartKitRules.vue',
        domain: '套件规则',
        reason:
          '当前 master-data router 未注册 kit-rules 端点。',
      },
      {
        file: '../SparePartEvidence.vue',
        domain: '证据',
        reason:
          'SparePartRead 当前没有证据引用集合或证据查询端点。',
      },
      {
        file: '../SparePartAudit.vue',
        domain: '审计',
        reason:
          '当前 API v1 router 未注册备件审计时间线端点。',
      },
    ]

    const forbiddenRequestPaths = [
      "'/applicability",
      '"/applicability',
      "'/lots",
      '"/lots',
      "'/serial-items",
      '"/serial-items',
      "'/substitutions",
      '"/substitutions',
      "'/kit-rules",
      '"/kit-rules',
      "'/evidence",
      '"/evidence',
      "'/audit",
      '"/audit',
    ]

    for (const contract of contracts) {
      const source = readFileSync(
        fileURLToPath(new URL(contract.file, import.meta.url)),
        'utf8',
      )

      assert.equal(
        source.includes('SparePartUnavailablePanel'),
        true,
      )
      assert.equal(source.includes(contract.domain), true)
      assert.equal(source.includes(contract.reason), true)

      for (const forbidden of [
        'masterDataDetailsApi',
        'maintenanceGet',
        'maintenancePost',
        'maintenancePut',
        'maintenancePatch',
        'maintenanceDelete',
        'tenant_id',
        ...forbiddenRequestPaths,
      ]) {
        assert.equal(source.includes(forbidden), false)
      }
    }
  },
)


test(
  'spare-part detail shell validates ids, loads tabs independently, and refreshes only overview after edit',
  () => {
    const source = readFileSync(
      fileURLToPath(
        new URL(
          '../../../../views/maintenance/master-data/SparePartDetail.vue',
          import.meta.url,
        ),
      ),
      'utf8',
    )

    for (const contract of [
      'function positiveInteger',
      'route.params.sparePartId',
      'Number.isInteger(parsed)',
      'parsed > 0',
      'createLazyDetailTabs',
      'masterDataDetailsApi.getSparePart',
      'masterDataDetailsApi.listSparePartInventory',
      'masterDataDetailsApi.listSparePartReliability',
      'masterDataDetailsApi.listSparePartSupply',
      "tabs.activate('overview')",
      'tabs.activate(tab)',
      'tabs.retry(tab)',
      'tabs.reset()',
      "activeTab.value = 'overview'",
      'MaintenanceErrorState',
      'SparePartOverview',
      'SparePartApplicability',
      'SparePartInventory',
      'SparePartLotsSerials',
      'SparePartSubstitutions',
      'SparePartKitRules',
      'SparePartReliability',
      'SparePartSupply',
      'SparePartEvidence',
      'SparePartAudit',
      'MasterDataEditorDrawer',
      'MASTER_DATA_RESOURCES.spareParts',
      'permissionsStore.permissions.editMasterData',
      'serializeMasterDataForm',
      'masterDataApi.update',
      "tabs.invalidate('overview')",
      "name: 'maintenanceMasterData'",
      "resource: 'spareParts'",
    ]) {
      assert.equal(
        source.includes(contract),
        true,
        `missing detail-shell contract: ${contract}`,
      )
    }

    assert.equal(source.includes("tabs.invalidate('inventory')"), false)
    assert.equal(source.includes("tabs.invalidate('reliability')"), false)
    assert.equal(source.includes("tabs.invalidate('supply')"), false)

    for (const forbidden of [
      'tenant_id',
      '/v1/master-data/applicability',
      '/v1/master-data/lots',
      '/v1/master-data/serial-items',
      '/v1/master-data/substitutions',
      '/v1/master-data/kit-rules',
      '/v1/evidence',
      '/v1/audit',
    ]) {
      assert.equal(source.includes(forbidden), false)
    }

    const invalidRouteGuard = source.indexOf(
      'if (sparePartId.value === null)',
    )
    const firstLoaderActivation = source.indexOf(
      "tabs.activate('overview')",
    )

    assert.notEqual(invalidRouteGuard, -1)
    assert.notEqual(firstLoaderActivation, -1)
    assert.equal(invalidRouteGuard < firstLoaderActivation, true)
  },
)
