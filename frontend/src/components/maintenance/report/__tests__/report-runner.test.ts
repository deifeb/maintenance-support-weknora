import assert from 'node:assert/strict'
import test from 'node:test'
import { spawnSync } from 'node:child_process'
// A subprocess must start a fresh test harness, not inherit Node's child context.
const { NODE_TEST_CONTEXT: _context, ...env } = process.env

test('test runner accepts and deduplicates explicit pre-existing mjs suites', () => {
  const file = 'src/stores/settingsStorage.test.mjs'
  const single = spawnSync(process.execPath, ['scripts/run-tests.mjs', file], { encoding: 'utf8', env })
  assert.equal(single.status, 0, single.stderr)
  assert.match(single.stdout, /tests \d+/)
  const repeated = spawnSync(process.execPath, ['scripts/run-tests.mjs', file, file], { encoding: 'utf8', env })
  assert.equal(repeated.status, 0, repeated.stderr)
  assert.equal(repeated.stdout.match(/tests \d+/)?.[0], single.stdout.match(/tests \d+/)?.[0])
  const directory = spawnSync(process.execPath, ['scripts/run-tests.mjs', 'src/stores'], { encoding: 'utf8', env })
  const overlap = spawnSync(process.execPath, ['scripts/run-tests.mjs', 'src/stores', file], { encoding: 'utf8', env })
  assert.equal(directory.status, 0, directory.stderr)
  assert.equal(overlap.status, 0, overlap.stderr)
  assert.equal(overlap.stdout.match(/tests \d+/)?.[0], directory.stdout.match(/tests \d+/)?.[0])
})

test('test runner propagates a failing Node suite and an unmatched target', () => {
  for (const target of ['scripts/fixtures/runner-failure.test.ts', 'package.json']) {
    const result = spawnSync(process.execPath, ['scripts/run-tests.mjs', target], { encoding: 'utf8', env })
    assert.equal(result.status, 1)
  }
})
