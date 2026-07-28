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
  const menuRoutes = (parent.children ?? [])
    .filter((route) => route.meta?.hideInMaintenanceMenu !== true)
    .map((route) => route.name)

  assert.deepEqual(menuRoutes, expectedRouteNames)
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
  const menuRoutes = (maintenanceRouteRecords[0].children ?? [])
    .filter((route) => route.meta?.hideInMaintenanceMenu !== true)
    .map((route) => route.name)

  assert.deepEqual(
    maintenanceMenuChildren.map((item) => item.routeName),
    menuRoutes,
  )
  assert.ok(
    maintenanceMenuChildren.every(
      (item) => item.titleKey.startsWith('maintenance.pages.'),
    ),
  )
})

test('configuration detail route is authenticated and hidden from menu alignment', () => {
  const children = maintenanceRouteRecords[0].children ?? []
  const detail = children.find(
    (route) => route.name === 'maintenanceConfigurationDetail',
  )

  assert.equal(
    detail?.path,
    'master-data/configurations/:configurationId',
  )
  assert.equal(detail?.meta?.requiresAuth, true)
  assert.equal(detail?.meta?.requiresInit, true)
  assert.equal(detail?.meta?.hideInMaintenanceMenu, true)
})
