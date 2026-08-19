import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { maintenanceRouteRecords } from '../../../router/maintenance.ts'

const here = dirname(fileURLToPath(import.meta.url))
const reviewListPath = resolve(here, '../reviews/ReviewList.vue')
const zhLocalePath = resolve(here, '../../../i18n/locales/zh-CN.ts')
const enLocalePath = resolve(here, '../../../i18n/locales/en-US.ts')

const maintenanceParent = maintenanceRouteRecords[0]
const maintenanceChildren = maintenanceParent?.children ?? []

function requiredSource(path: string, label: string): string {
  assert.equal(
    existsSync(path),
    true,
    `TASK7_RED_NAVIGATION: missing ${label}`,
  )
  return readFileSync(path, 'utf8')
}

test('formal review detail uses the frozen hidden authenticated route contract', () => {
  const route = maintenanceChildren.find(
    (child) => child.name === 'maintenanceReviewDetail',
  )

  assert.ok(
    route,
    'TASK7_RED_NAVIGATION: missing hidden formal review detail route',
  )
  assert.equal(route.path, 'reviews/:reviewId')
  assert.equal(route.meta?.requiresAuth, true)
  assert.equal(route.meta?.requiresInit, true)
  assert.equal(route.meta?.hideInMaintenanceMenu, true)
  assert.equal(route.meta?.hidden, undefined)
})

test('maintenance menu keeps only Review List as the visible reviews entry', () => {
  const menuChildren = maintenanceChildren.filter(
    (child) => !child.meta?.hideInMaintenanceMenu,
  )
  const reviewMenuChildren = menuChildren.filter(
    (child) => String(child.path).startsWith('reviews'),
  )

  assert.deepEqual(
    reviewMenuChildren.map((child) => child.name),
    ['maintenanceReviews'],
    'TASK7_RED_NAVIGATION: hidden Review Detail must not become a menu item',
  )
})

test('Review List replaces the placeholder with formal demand-review state and counts', () => {
  const source = requiredSource(reviewListPath, 'ReviewList.vue')

  assert.doesNotMatch(
    source,
    /maintenance-placeholder|maintenance\.placeholder/,
    'TASK7_RED_NAVIGATION: ReviewList is still the pre-Task-7 placeholder',
  )
  assert.match(
    source,
    /useDemandReviewStore/,
    'TASK7_RED_NAVIGATION: ReviewList must consume the formal demand-review store',
  )
  assert.match(source, /fetchReviews/)
  assert.match(source, /runReview/)

  for (const field of [
    'status',
    'total_finding_count',
    'blocking_finding_count',
    'pending_finding_count',
    'pending_blocking_finding_count',
  ]) {
    assert.match(
      source,
      new RegExp(`\\b${field}\\b`),
      `TASK7_RED_NAVIGATION: ReviewList must render formal review field ${field}`,
    )
  }

  assert.doesNotMatch(
    source,
    /AIReviewRun|ai[-_/]?review|\/api\/v1\/ai\/reviews|\/ai\/reviews\/demand-lists/i,
    'TASK7_RED_NAVIGATION: AI review authority must not be mixed into formal Review List',
  )
})

test('Review List runs only from published-list identity and source version, never browser authority payloads', () => {
  const source = requiredSource(reviewListPath, 'ReviewList.vue')

  assert.match(
    source,
    /source_demand_list_id|demandListId/,
    'TASK7_RED_NAVIGATION: ReviewList needs an authoritative source demand-list identity',
  )
  assert.match(
    source,
    /source_demand_list_version|expected_source_version/,
    'TASK7_RED_NAVIGATION: run must carry expected_source_version from the published list',
  )
  assert.match(
    source,
    /PUBLISHED|published/,
    'TASK7_RED_NAVIGATION: run affordance must be tied to a published/current demand list',
  )
  assert.doesNotMatch(
    source,
    /tenant_id\s*:/,
    'TASK7_RED_NAVIGATION: browser must not submit tenant authority for formal review run',
  )
})

test('Task 7 introduces structured bilingual review workspace copy', () => {
  const zh = requiredSource(zhLocalePath, 'zh-CN.ts')
  const en = requiredSource(enLocalePath, 'en-US.ts')

  assert.match(
    zh,
    /(?:review|reviews)\s*:\s*\{/,
    'TASK7_RED_NAVIGATION: zh-CN needs a structured formal-review locale section',
  )
  assert.match(
    en,
    /(?:review|reviews)\s*:\s*\{/,
    'TASK7_RED_NAVIGATION: en-US needs a structured formal-review locale section',
  )
})
