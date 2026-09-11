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

test('rejects a non-decimal port', () => {
  assert.throws(
    () => readRuntimeConfig({ E2E_ROOT_DIR: 'C:/e2e', E2E_FRONTEND_PORT: '0x400' }),
    /E2E_FRONTEND_PORT must be between 1024 and 65535/,
  )
})

test('rejects an unsafe Postgres image', () => {
  assert.throws(
    () => readRuntimeConfig({ E2E_ROOT_DIR: 'C:/e2e', E2E_POSTGRES_IMAGE: 'https://registry/e2e' }),
    /E2E_POSTGRES_IMAGE must be a safe Docker image reference/,
  )
})

test('only retains allowlisted diagnostic environment values', () => {
  assert.deepEqual(
    sanitizeCommandEnvironment({
      E2E_ROOT_DIR: 'C:/e2e',
      E2E_FRONTEND_PORT: '5174',
      E2E_MAINTENANCE_PORT: '8101',
      E2E_POSTGRES_IMAGE: 'postgres:17-alpine',
      E2E_WEKNORA_PORT: '8081',
      ACCESS_TOKEN: 'hidden',
      DATABASE_URL: 'postgresql://user:password@localhost:5432/e2e',
      DB_PASSWORD: 'hidden',
      E2E_API_KEY: 'hidden',
      SIGNING_SECRET: 'hidden',
      TEMP_PATH: 'C:/e2e/run-123',
    }),
    {
      E2E_FRONTEND_PORT: '5174',
      E2E_MAINTENANCE_PORT: '8101',
      E2E_WEKNORA_PORT: '8081',
    },
  )
})

test('omits unsafe diagnostic values', () => {
  assert.deepEqual(
    sanitizeCommandEnvironment({
      E2E_FRONTEND_PORT: 'https://example.test',
      E2E_MAINTENANCE_PORT: '/tmp/e2e',
      E2E_POSTGRES_IMAGE: 'registry/secret-token',
      E2E_WEKNORA_PORT: 'C:/e2e',
    }),
    {},
  )
})
