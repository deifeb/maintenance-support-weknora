import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  maintenanceRouteRecords,
} from '../../../router/maintenance.ts'

function findMaintenanceRoute(name: string) {
  const parent = maintenanceRouteRecords[0]
  return [parent, ...(parent.children ?? [])].find(
    (route) => route.name === name,
  )
}

test('calculation workflow routes are authenticated and hidden from menu', () => {
  for (const name of [
    'maintenanceCalculationNew',
    'maintenanceCalculationProgress',
    'maintenanceCalculationComparison',
  ]) {
    const route = findMaintenanceRoute(name)
    assert.equal(route?.meta?.requiresAuth, true)
    assert.equal(route?.meta?.requiresInit, true)
    assert.equal(
      route?.meta?.hideInMaintenanceMenu,
      true,
    )
  }
})

test('calculation routes expose stable deep-link paths', () => {
  assert.equal(
    findMaintenanceRoute('maintenanceCalculationNew')?.path,
    'calculations/new',
  )
  assert.equal(
    findMaintenanceRoute(
      'maintenanceCalculationProgress',
    )?.path,
    'calculations/:groupId/progress',
  )
  assert.equal(
    findMaintenanceRoute(
      'maintenanceCalculationComparison',
    )?.path,
    'calculations/:groupId/comparison',
  )
})

test('calculation list uses server paging and terminal routing', () => {
  const source = readFileSync(
    new URL(
      '../calculations/CalculationList.vue',
      import.meta.url,
    ),
    'utf8',
  )

  assert.match(source, /calculationGroupStore\.list/)
  assert.match(
    source,
    /maintenanceCalculationProgress/,
  )
  assert.match(
    source,
    /maintenanceCalculationComparison/,
  )
})
