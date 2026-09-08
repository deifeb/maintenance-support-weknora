import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const chatDir = join(here, '..')

const componentFiles = [
  'MaintenanceBusinessCardHost.vue',
  'ScenarioDraftCard.vue',
  'CalculationCard.vue',
  'ModelComparisonCard.vue',
  'InventoryGapCard.vue',
  'ReviewFindingCard.vue',
  'ReportCard.vue',
]

const forbiddenMutationSignals = [
  /from\s+['"]@\/api\/maintenance/i,
  /\bpost\s*\(/i,
  /\bput\s*\(/i,
  /\bpatch\s*\(/i,
  /\bdelete\s*\(/i,
  /\bcreate[A-Z]\w*\s*\(/,
  /\bupdate[A-Z]\w*\s*\(/,
  /\bexecute[A-Z]\w*\s*\(/,
  /\bapprove[A-Z]\w*\s*\(/,
  /\breject[A-Z]\w*\s*\(/,
]

test('host and all six display-only maintenance card components exist', () => {
  for (const file of componentFiles) {
    assert.equal(
      existsSync(join(chatDir, file)),
      true,
      `${file} must exist`,
    )
  }
})

test('host consumes normalized render items and hides itself when there are zero cards', () => {
  const hostPath = join(chatDir, 'MaintenanceBusinessCardHost.vue')
  assert.equal(existsSync(hostPath), true, 'host must exist before source contract can be checked')

  const source = readFileSync(hostPath, 'utf8')

  assert.match(source, /buildMaintenanceCardRenderItems/)
  assert.match(source, /v-if\s*=\s*["'][^"']*renderItems\.length[^"']*["']/)
  assert.match(source, /<component\b/)
})

test('display-only card components do not import or invoke maintenance mutation APIs', () => {
  for (const file of componentFiles.filter((name) => name !== 'MaintenanceBusinessCardHost.vue')) {
    const path = join(chatDir, file)
    assert.equal(existsSync(path), true, `${file} must exist before source contract can be checked`)
    const source = readFileSync(path, 'utf8')

    for (const pattern of forbiddenMutationSignals) {
      assert.doesNotMatch(
        source,
        pattern,
        `${file} contains forbidden mutation signal ${pattern}`,
      )
    }
  }
})
