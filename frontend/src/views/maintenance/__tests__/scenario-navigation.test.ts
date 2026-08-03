import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { maintenanceRouteRecords } from '../../../router/maintenance.ts'
import {
  scenarioDraftActions,
  scenarioVersionActions,
} from '../scenarios/scenario-actions.ts'

function flattenMaintenanceRoutes() {
  const parent = maintenanceRouteRecords[0]
  return [parent, ...(parent.children ?? [])]
}

test('scenario detail routes are authenticated and hidden from menu', () => {
  const routes = flattenMaintenanceRoutes()
  for (const name of [
    'maintenanceScenarioNew',
    'maintenanceScenarioDetail',
    'maintenanceScenarioVersionDetail',
  ]) {
    const route = routes.find(
      (item) => item.name === name,
    )
    assert.equal(route?.meta?.requiresAuth, true)
    assert.equal(route?.meta?.requiresInit, true)
    assert.equal(
      route?.meta?.hideInMaintenanceMenu,
      true,
    )
  }
})

test('scenario routes expose stable deep-link paths', () => {
  const routes = flattenMaintenanceRoutes()
  const paths = Object.fromEntries(
    routes.map((route) => [
      String(route.name),
      route.path,
    ]),
  )

  assert.equal(
    paths.maintenanceScenarioNew,
    'scenarios/new',
  )
  assert.equal(
    paths.maintenanceScenarioDetail,
    'scenarios/:scenarioId',
  )
  assert.equal(
    paths.maintenanceScenarioVersionDetail,
    'scenarios/:scenarioId/versions/:versionId',
  )
})

test('contributor edits drafts but only admin publishes', () => {
  assert.deepEqual(
    scenarioDraftActions('contributor', 'READY'),
    ['materialize'],
  )
  assert.deepEqual(
    scenarioDraftActions('viewer', 'READY'),
    [],
  )
  assert.deepEqual(
    scenarioVersionActions('admin', 'DRAFT'),
    ['publish'],
  )
  assert.deepEqual(
    scenarioVersionActions('contributor', 'DRAFT'),
    ['edit'],
  )
  assert.deepEqual(
    scenarioVersionActions('viewer', 'DRAFT'),
    [],
  )
  assert.deepEqual(
    scenarioVersionActions('admin', 'PUBLISHED'),
    ['retire'],
  )
})

test('scenario list uses the shared stale-safe server table', () => {
  const source = readFileSync(
    new URL(
      '../scenarios/ScenarioList.vue',
      import.meta.url,
    ),
    'utf8',
  )

  assert.match(source, /createServerTableState/)
  assert.match(source, /scenarioApi\.listScenarios/)
  assert.match(source, /maintenanceScenarioNew/)
})
