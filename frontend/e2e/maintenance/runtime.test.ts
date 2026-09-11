import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  MaintenanceE2ERuntime,
  readRuntimeConfig,
  sanitizeCommandEnvironment,
  type RuntimeDependencies,
} from './runtime'

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

async function withRoot(run: (root: string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(join(tmpdir(), 'maintenance-e2e-runtime-'))
  try {
    await run(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

function testDependencies(events: string[]): RuntimeDependencies {
  return {
    runCommand: async (command, args) => {
      events.push(`${command} ${args[0]}`)
    },
    startProcess: (name) => {
      events.push(`start ${name}`)
      return { stop: async () => events.push(`stop ${name}`) }
    },
    waitForPostgres: async () => events.push('healthy postgres'),
    waitForHttp: async (name) => events.push(`healthy ${name}`),
  }
}

test('creates an isolated run directory below the E2E root', async () => {
  await withRoot(async (root) => {
    const runtime = new MaintenanceE2ERuntime({ E2E_ROOT_DIR: root })

    await runtime.prepare()

    assert.match(runtime.containerName, /^maintenance-e2e-/)
    assert.equal(runtime.runDir.startsWith(root), true)
    await Promise.all([
      stat(join(runtime.runDir, 'postgres-data')),
      stat(join(runtime.runDir, 'logs')),
      stat(runtime.artifactsDir),
      stat(join(runtime.runDir, 'maintenance.sqlite3')),
    ])

    await runtime.stop({ failed: false })
    await assert.rejects(stat(runtime.runDir))
  })
})

test('starts each dependency only after its prerequisite is healthy', async () => {
  await withRoot(async (root) => {
    const events: string[] = []
    const runtime = new MaintenanceE2ERuntime(
      { E2E_ROOT_DIR: root },
      testDependencies(events),
    )

    await runtime.start()

    assert.deepEqual(events, [
      'docker run',
      'healthy postgres',
      'start weknora',
      'healthy weknora',
      'start maintenance',
      'healthy maintenance',
      'start vite',
    ])
    await runtime.stop({ failed: false })
  })
})

test('stops services in reverse order and retains only redacted failure logs', async () => {
  await withRoot(async (root) => {
    const events: string[] = []
    const runtime = new MaintenanceE2ERuntime(
      { E2E_ROOT_DIR: root },
      testDependencies(events),
    )
    await runtime.start()
    await runtime.appendServiceLog('weknora', `DATABASE_URL=postgres://secret@127.0.0.1\n${runtime.runDir}`)

    await runtime.stop({ failed: true })

    assert.deepEqual(events.slice(-4), [
      'stop vite',
      'stop maintenance',
      'stop weknora',
      'docker rm',
    ])
    const retainedLog = await readFile(join(runtime.artifactsDir, 'logs', 'weknora.log'), 'utf8')
    assert.doesNotMatch(retainedLog, /postgres:\/\/secret|maintenance-e2e-runtime-/)
    await assert.rejects(stat(join(runtime.runDir, 'postgres-data')))
    await assert.rejects(stat(join(runtime.runDir, 'maintenance.sqlite3')))
  })
})
