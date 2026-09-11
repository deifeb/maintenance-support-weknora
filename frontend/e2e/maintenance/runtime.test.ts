import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  MaintenanceE2ERuntime,
  readRuntimeConfig,
  runtimeCommand,
  runtimeExecutable,
  sanitizeCommandEnvironment,
  startManagedProcess,
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

function testDependencies(
  events: string[],
  failMigration = false,
  failCommand?: (command: string, args: string[]) => boolean,
): RuntimeDependencies {
  return {
    runCommand: async (command, args) => {
      events.push(command === runtimeExecutable('python') ? commandEvent(command, args) : `${command} ${args[0]}`)
      if (failCommand?.(command, args)) throw new Error('command failed')
    },
    startProcess: async (name, command, args) => {
      events.push(`start ${name}: ${commandEvent(command, args)}`)
      return { stop: async () => events.push(`stop ${name}`) }
    },
    waitForPostgres: async () => events.push('healthy postgres'),
    waitForWeKnoraMigrations: async () => {
      events.push('migrated weknora')
      if (failMigration) throw new Error('migration check failed')
    },
    waitForHttp: async (name) => events.push(`healthy ${name}`),
  }
}

function commandEvent(command: string, args: string[]): string {
  return [command, ...args].join(' ')
}

function runtimeCommandEvent(command: string, args: string[]): string {
  const invocation = runtimeCommand(command, args)
  return commandEvent(invocation.command, invocation.args)
}

test('wraps Windows npm command scripts in cmd.exe while preserving native executables', () => {
  assert.deepEqual(
    runtimeCommand('npm', ['run', 'dev'], 'win32'),
    { command: 'cmd.exe', args: ['/d', '/s', '/c', 'npm.cmd', 'run', 'dev'] },
  )
  assert.deepEqual(
    runtimeCommand('npx', ['playwright', 'test'], 'win32'),
    { command: 'cmd.exe', args: ['/d', '/s', '/c', 'npx.cmd', 'playwright', 'test'] },
  )
  assert.equal(runtimeExecutable('python', 'win32'), 'python.exe')
  assert.equal(runtimeExecutable('go', 'win32'), 'go.exe')
  assert.deepEqual(runtimeCommand('npm', ['run', 'dev'], 'linux'), { command: 'npm', args: ['run', 'dev'] })
})

test('rejects an asynchronous missing child executable', async () => {
  await withRoot(async (root) => {
    await assert.rejects(
      startManagedProcess('definitely-missing-e2e-command', [], { cwd: root, env: process.env }, join(root, 'missing.log')),
      /definitely-missing-e2e-command exited unsuccessfully/,
    )
  })
})

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
      `start weknora: ${commandEvent(runtimeExecutable('go'), ['run', './cmd/server'])}`,
      'migrated weknora',
      'healthy weknora',
      `${runtimeExecutable('python')} -m alembic upgrade head`,
      `start maintenance: ${commandEvent(runtimeExecutable('python'), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8101'])}`,
      'healthy maintenance',
      `start vite: ${runtimeCommandEvent('npm', ['run', 'dev', '--', '--port', '5174', '--strictPort'])}`,
    ])
    await runtime.stop({ failed: false })
  })
})

test('aborts before WeKnora health acceptance when its migration check fails', async () => {
  await withRoot(async (root) => {
    const events: string[] = []
    const runtime = new MaintenanceE2ERuntime(
      { E2E_ROOT_DIR: root },
      testDependencies(events, true),
    )

    await assert.rejects(runtime.start(), /migration check failed/)
    assert.deepEqual(events, [
      'docker run',
      'healthy postgres',
      `start weknora: ${commandEvent(runtimeExecutable('go'), ['run', './cmd/server'])}`,
      'migrated weknora',
    ])
    await runtime.stop({ failed: false })
  })
})

test('aborts before Maintenance starts when its Alembic migration fails', async () => {
  await withRoot(async (root) => {
    const events: string[] = []
    const runtime = new MaintenanceE2ERuntime(
      { E2E_ROOT_DIR: root },
      testDependencies(events, false, (command, args) => command === 'python.exe' && args[1] === 'alembic'),
    )

    await assert.rejects(runtime.start(), /command failed/)
    assert.deepEqual(events, [
      'docker run',
      'healthy postgres',
      `start weknora: ${commandEvent(runtimeExecutable('go'), ['run', './cmd/server'])}`,
      'migrated weknora',
      'healthy weknora',
      `${runtimeExecutable('python')} -m alembic upgrade head`,
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
    const reportDir = join(runtime.artifactsDir, 'playwright-report')
    await mkdir(reportDir, { recursive: true })
    await writeFile(join(reportDir, 'index.html'), 'failure report')
    await runtime.appendServiceLog('weknora', [
      'DATABASE_URL=postgres://secret@127.0.0.1',
      'JWT=header.payload.signature',
      'Authorization: Bearer bearer-secret',
      'Authorization=Bearer assignment-secret',
      'HTTP_AUTHORIZATION: Bearer http-assignment-secret',
      'TOKEN=Bearer token-assignment-secret',
      'access_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.signature',
      runtime.runDir,
    ].join('\n'))

    await runtime.stop({ failed: true })

    assert.deepEqual(events.slice(-4), [
      'stop vite',
      'stop maintenance',
      'stop weknora',
      'docker rm',
    ])
    const retainedLog = await readFile(join(runtime.artifactsDir, 'logs', 'weknora.log'), 'utf8')
    assert.doesNotMatch(retainedLog, /postgres:\/\/secret|maintenance-e2e-runtime-|header\.payload\.signature|bearer-secret|assignment-secret|http-assignment-secret|token-assignment-secret|eyJhbGci/)
    assert.equal(await readFile(join(reportDir, 'index.html'), 'utf8'), 'failure report')
    await assert.rejects(stat(join(runtime.runDir, 'postgres-data')))
    await assert.rejects(stat(join(runtime.runDir, 'maintenance.sqlite3')))
  })
})
