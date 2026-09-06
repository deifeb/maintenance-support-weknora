import assert from 'node:assert/strict'
import test from 'node:test'

import { maintenanceRouteRecords } from '../../../router/maintenance.ts'

const expectedAllocationRoutes = [
  {
    name: 'maintenanceAllocationRules',
    path: 'inventory-gap/rules',
  },
  {
    name: 'maintenanceAllocationPlanDetail',
    path: 'inventory-gap/allocations/:planId',
  },
] as const

const maintenanceParent = maintenanceRouteRecords[0]
const maintenanceChildren = maintenanceParent?.children ?? []

for (const expected of expectedAllocationRoutes) {
  test(`${expected.name} uses the hidden authenticated allocation route contract`, () => {
    const route = maintenanceChildren.find(
      (child) => child.name === expected.name,
    )

    assert.ok(route, `TASK8_RED_ROUTE: missing allocation route ${expected.name}`)
    assert.equal(route.path, expected.path)
    assert.equal(route.meta?.requiresAuth, true)
    assert.equal(route.meta?.requiresInit, true)
    assert.equal(route.meta?.hideInMaintenanceMenu, true)
    assert.equal(route.meta?.hidden, undefined)
  })
}

test('maintenance menu still exposes only the single Inventory Gap top-level entry', () => {
  const maintenanceMenuChildren = maintenanceChildren.filter(
    (child) => !child.meta?.hideInMaintenanceMenu,
  )
  const inventoryMenuChildren = maintenanceMenuChildren.filter(
    (child) => String(child.path).startsWith('inventory-gap'),
  )

  assert.deepEqual(
    inventoryMenuChildren.map((child) => child.name),
    ['maintenanceInventoryGap'],
  )

  for (const expected of expectedAllocationRoutes) {
    assert.equal(
      maintenanceMenuChildren.some(
        (child) => child.name === expected.name,
      ),
      false,
    )
  }
})
