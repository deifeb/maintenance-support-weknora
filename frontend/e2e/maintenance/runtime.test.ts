import assert from 'node:assert/strict'
import test from 'node:test'

import { readRuntimeConfig, sanitizeCommandEnvironment } from './runtime'

test('requires a root directory', () => {
  assert.throws(() => readRuntimeConfig({}), /E2E_ROOT_DIR is required/)
})

test('rejects an invalid port', () => {
  assert.throws(
    () => readRuntimeConfig({ E2E_ROOT_DIR: 'C:/e2e', E2E_FRONTEND_PORT: '70000' }),
    /E2E_FRONTEND_PORT must be between 1024 and 65535/,
  )
})

test('redacts diagnostic environment values', () => {
  assert.deepEqual(
    sanitizeCommandEnvironment({
      E2E_ROOT_DIR: 'C:/e2e',
      ACCESS_TOKEN: 'hidden',
      DB_PASSWORD: 'hidden',
      E2E_API_KEY: 'hidden',
      SIGNING_SECRET: 'hidden',
    }),
    { E2E_ROOT_DIR: 'C:/e2e' },
  )
})
