import assert from 'node:assert/strict'
import test from 'node:test'

import { maintenanceRouteRecords } from '../../../router/maintenance.ts'

const expectedDetailRoutes = [
  {
    name: 'maintenanceInventoryBalanceDetail',
    path: 'inventory-gap/balances/:balanceId',
  },
  {
    name: 'maintenanceInventoryTransactionDetail',
    path: 'inventory-gap/transactions/:transactionId',
  },
  {
    name: 'maintenanceInventoryReservationDetail',
    path: 'inventory-gap/reservations/:reservationId',
  },
  {
    name: 'maintenanceInventoryTransferDetail',
    path: 'inventory-gap/transfers/:transferId',
  },
  {
    name: 'maintenanceInventoryStocktakeDetail',
    path: 'inventory-gap/stocktakes/:stocktakeId',
  },
] as const

const maintenanceParent = maintenanceRouteRecords[0]
const maintenanceChildren = maintenanceParent?.children ?? []

for (const expected of expectedDetailRoutes) {
  test(`${expected.name} uses the frozen hidden authenticated route contract`, () => {
    const route = maintenanceChildren.find(
      (child) => child.name === expected.name,
    )

    assert.ok(route, `missing inventory detail route ${expected.name}`)
    assert.equal(route.path, expected.path)
    assert.equal(route.meta?.requiresAuth, true)
    assert.equal(route.meta?.requiresInit, true)
    assert.equal(route.meta?.hideInMaintenanceMenu, true)
    assert.equal(route.meta?.hidden, undefined)
  })
}

test('maintenance menu exposes only the single Inventory Gap top-level entry', () => {
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
  for (const detail of expectedDetailRoutes) {
    assert.equal(
      maintenanceMenuChildren.some((child) => child.name === detail.name),
      false,
    )
  }
})
