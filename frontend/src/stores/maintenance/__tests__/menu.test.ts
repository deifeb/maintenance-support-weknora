import test from 'node:test'
import assert from 'node:assert/strict'
import { maintenanceRouteRecords } from '../../../router/maintenance'
import { maintenanceMenuChildren } from '../menu-definition'

const expectedPaths = [
  'maintenance/dashboard',
  'maintenance/master-data',
  'maintenance/scenarios',
  'maintenance/calculations',
  'maintenance/inventory-gap',
  'maintenance/reviews',
  'maintenance/reports',
]

const expectedRouteNames = [
  'maintenanceDashboard',
  'maintenanceMasterData',
  'maintenanceScenarios',
  'maintenanceCalculations',
  'maintenanceInventoryGap',
  'maintenanceReviews',
  'maintenanceReports',
]

test('maintenance menu has exactly seven ordered entries', () => {
  assert.deepEqual(
    maintenanceMenuChildren.map((item) => item.path),
    expectedPaths,
  )
})

test('maintenance routes expose stable names and dashboard redirect', () => {
  const parent = maintenanceRouteRecords[0]

  assert.equal(maintenanceRouteRecords.length, 1)
  assert.equal(parent.path, 'maintenance')
  assert.equal(parent.name, 'maintenance')
  assert.equal(parent.redirect, '/platform/maintenance/dashboard')
  assert.deepEqual(
    parent.children?.map((route) => route.name),
    expectedRouteNames,
  )
})

test('all maintenance routes require authentication and initialization', () => {
  const parent = maintenanceRouteRecords[0]
  const records = [parent, ...(parent.children ?? [])]

  assert.ok(
    records.every(
      (route) => (
        route.meta?.requiresAuth === true
        && route.meta?.requiresInit === true
      ),
    ),
  )
})

test('maintenance menu and route definitions stay aligned', () => {
  const routeNames = maintenanceRouteRecords[0].children?.map(
    (route) => route.name,
  )

  assert.deepEqual(
    maintenanceMenuChildren.map((item) => item.routeName),
    routeNames,
  )
  assert.ok(
    maintenanceMenuChildren.every(
      (item) => item.titleKey.startsWith('maintenance.pages.'),
    ),
  )
})
