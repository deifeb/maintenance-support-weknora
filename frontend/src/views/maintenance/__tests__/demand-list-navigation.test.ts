import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  maintenanceCalculationLocales,
} from '../../../i18n/locales/maintenance-calculation.ts'
import { maintenanceRouteRecords } from '../../../router/maintenance.ts'

function flattenMaintenanceRoutes() {
  const parent = maintenanceRouteRecords[0]
  return [parent, ...(parent.children ?? [])]
}

function source(
  relative: string,
): string {
  return readFileSync(
    new URL(relative, import.meta.url),
    'utf8',
  )
}

function keyPaths(
  value: unknown,
  prefix = '',
): string[] {
  if (
    value === null
    || typeof value !== 'object'
    || Array.isArray(value)
  ) {
    return [prefix]
  }

  return Object.entries(
    value as Record<string, unknown>,
  ).flatMap(([key, child]) => {
    const next = prefix ? `${prefix}.${key}` : key
    return keyPaths(child, next)
  }).sort()
}

test('demand-list route is authenticated, initialized, hidden, and stable', () => {
  const route = flattenMaintenanceRoutes().find(
    (item) => item.name === 'maintenanceDemandListDetail',
  )

  assert.equal(
    route?.path,
    'calculations/demand-lists/:listId',
  )
  assert.equal(route?.meta?.requiresAuth, true)
  assert.equal(route?.meta?.requiresInit, true)
  assert.equal(
    route?.meta?.hideInMaintenanceMenu,
    true,
  )
})

test('comparison uses the conservative gate and routes with the created aggregate id', () => {
  const comparison = source(
    '../calculations/CalculationComparison.vue',
  )

  assert.match(
    comparison,
    /canOfferDemandListGeneration/,
  )
  assert.match(
    comparison,
    /useDemandListStore/,
  )
  assert.match(
    comparison,
    /demandListStore\.create/,
  )
  assert.match(
    comparison,
    /params:\s*\{\s*listId:\s*created\.id\s*\}/s,
  )
  assert.doesNotMatch(
    comparison,
    /tenant[_-]?id/i,
  )
  assert.doesNotMatch(comparison, /function requestKey/)
})

test('lifecycle action component is presentation-only', () => {
  const actions = source(
    '../../../components/maintenance/calculation/DemandListLifecycleActions.vue',
  )

  assert.match(actions, /demandListActions/)
  assert.match(actions, /emit\('select', action\)/)
  assert.doesNotMatch(actions, /useDemandListStore/)
  assert.doesNotMatch(
    actions,
    /useMaintenancePermissionsStore/,
  )
  assert.doesNotMatch(actions, /useRouter|useRoute/)
  assert.doesNotMatch(actions, /DialogPlugin|MessagePlugin/)
  assert.doesNotMatch(
    actions,
    /viewer|contributor|admin|owner/,
  )
})

test('detail validates route ids and disposes stale requests', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /positiveInteger/)
  assert.match(detail, /invalidRoute/)
  assert.match(detail, /store\.load\(targetId\)/)
  assert.match(detail, /watch\(/)
  assert.match(detail, /onBeforeUnmount\(store\.dispose\)/)
  assert.match(detail, /maintenanceCalculations/)
})

test('detail item editing preserves decimal strings', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /canEditDemandListItem/)
  assert.match(detail, /type="text"/)
  assert.match(detail, /inputmode="decimal"/)
  assert.match(
    detail,
    /store\.updateItem\(\s*selectedItem\.value\.id,\s*quantity,\s*reason/s,
  )
  assert.doesNotMatch(
    detail,
    /Number\(\s*editQuantity/,
  )
  assert.doesNotMatch(
    detail,
    /parseFloat\(\s*editQuantity/,
  )
  assert.doesNotMatch(
    detail,
    /parseInt\(\s*editQuantity/,
  )
})

test('detail owns explicit lifecycle confirmations and exact confirmation note forwarding', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(detail, /DemandListLifecycleActions/)
  assert.match(detail, /DialogPlugin\.confirm/)
  assert.match(detail, /confirmationNote/)
  assert.match(
    detail,
    /store\.confirm\(\s*note\s*\)/s,
  )
  assert.match(detail, /store\.submit/)
  assert.match(detail, /store\.publish/)
  assert.match(detail, /store\.voidList/)
  assert.doesNotMatch(
    detail,
    /confirmation_note/,
  )
  assert.doesNotMatch(detail, /function requestKey/)
  assert.doesNotMatch(detail, /requestKey\(/)
})

test('derive routes to the aggregate id returned by the store', () => {
  const detail = source(
    '../calculations/DemandListDetail.vue',
  )

  assert.match(
    detail,
    /const derived = await store\.derive/,
  )
  assert.match(
    detail,
    /params:\s*\{\s*listId:\s*derived\.id\s*\}/s,
  )
})

test('demand-list locale shapes match in all calculation locales', () => {
  const demandLists = Object.values(
    maintenanceCalculationLocales,
  ).map((locale) => (
    (
      locale as unknown as Record<string, unknown>
    ).demandList
  ))

  for (const demandList of demandLists) {
    assert.notEqual(
      demandList,
      undefined,
    )
  }

  const expected = keyPaths(demandLists[0])

  for (const demandList of demandLists) {
    assert.deepEqual(
      keyPaths(demandList),
      expected,
    )
  }
})
