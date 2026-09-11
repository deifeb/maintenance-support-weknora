import { randomBytes, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const diagnosticPortKeys = ['E2E_FRONTEND_PORT', 'E2E_MAINTENANCE_PORT', 'E2E_WEKNORA_PORT'] as const
const sensitiveValue = /(TOKEN|SECRET|PASSWORD|API_KEY|BEARER)/i
const dockerImageReference = /^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?\/)*[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-z0-9][a-z0-9._-]*)?$/
const serviceNames = ['weknora', 'maintenance', 'vite'] as const

type ServiceName = (typeof serviceNames)[number]
type HealthTarget = 'postgres' | ServiceName | 'all'

interface RuntimeConfig {
  rootDir: string
  frontendPort: number
  weknoraPort: number
  maintenancePort: number
  postgresImage: string
}

interface ProcessOptions {
  cwd: string
  env: NodeJS.ProcessEnv
}

export interface ManagedProcess {
  stop(): Promise<void>
}

export interface RuntimeDependencies {
  runCommand(command: string, args: string[], options?: ProcessOptions): Promise<void>
  startProcess(name: ServiceName, command: string, args: string[], options: ProcessOptions): ManagedProcess
  waitForPostgres(containerName: string, username: string, database: string): Promise<void>
  waitForHttp(name: ServiceName, url: string): Promise<void>
}

function isPort(value: string): boolean {
  const port = Number(value)
  return /^\d+$/.test(value) && Number.isInteger(port) && port >= 1024 && port <= 65535
}

function isSafeDockerImage(value: string): boolean {
  return dockerImageReference.test(value) && !sensitiveValue.test(value)
}

function executable(command: string): string {
  return process.platform === 'win32' ? `${command}.cmd` : command
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds))
}

async function findAvailablePort(): Promise<number> {
  return new Promise((resolvePort, rejectPort) => {
    const server = createServer()
    server.once('error', rejectPort)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (address === null || typeof address === 'string') {
        rejectPort(new Error('Unable to reserve an E2E Postgres port'))
        return
      }
      server.close((error) => error ? rejectPort(error) : resolvePort(address.port))
    })
  })
}

function commandFailure(command: string): Error {
  return new Error(`${command} exited unsuccessfully`)
}

async function runCommand(command: string, args: string[], options?: ProcessOptions): Promise<void> {
  await new Promise<void>((resolveCommand, rejectCommand) => {
    const child = spawn(command, args, { cwd: options?.cwd, env: options?.env, stdio: 'ignore', windowsHide: true })
    child.once('error', () => rejectCommand(commandFailure(command)))
    child.once('exit', (code) => code === 0 ? resolveCommand() : rejectCommand(commandFailure(command)))
  })
}

async function stopChild(child: ReturnType<typeof spawn>): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null) return
  await new Promise<void>((resolveStop) => {
    const timeout = setTimeout(() => {
      if (child.exitCode === null) child.kill('SIGKILL')
    }, 5_000)
    child.once('exit', () => {
      clearTimeout(timeout)
      resolveStop()
    })
    child.kill('SIGTERM')
  })
}

export function sanitizeCommandEnvironment(env: NodeJS.ProcessEnv): Record<string, string> {
  return Object.fromEntries(diagnosticPortKeys.flatMap((key) => {
    const value = env[key]
    return value !== undefined && isPort(value) ? [[key, value]] : []
  }))
}

export function readRuntimeConfig(env: NodeJS.ProcessEnv): RuntimeConfig {
  const rootDir = env.E2E_ROOT_DIR?.trim()
  if (!rootDir) throw new Error('E2E_ROOT_DIR is required')
  const port = (name: string, fallback: number) => {
    const rawValue = env[name] ?? String(fallback)
    if (!isPort(rawValue)) throw new Error(`${name} must be between 1024 and 65535`)
    return Number(rawValue)
  }
  const postgresImage = env.E2E_POSTGRES_IMAGE?.trim() ?? 'postgres:17-alpine'
  if (!isSafeDockerImage(postgresImage)) throw new Error('E2E_POSTGRES_IMAGE must be a safe Docker image reference')
  return {
    rootDir,
    frontendPort: port('E2E_FRONTEND_PORT', 5174),
    weknoraPort: port('E2E_WEKNORA_PORT', 8081),
    maintenancePort: port('E2E_MAINTENANCE_PORT', 8101),
    postgresImage,
  }
}

export class MaintenanceE2ERuntime {
  readonly artifactsDir: string
  readonly baseURL: string
  readonly containerName: string
  readonly runDir: string

  private readonly config: RuntimeConfig
  private readonly dependencies: RuntimeDependencies
  private readonly databaseName = 'weknora_e2e'
  private readonly databaseUser = 'weknora_e2e'
  private readonly databasePassword = randomBytes(32).toString('base64url')
  private readonly signingSecret = randomBytes(48).toString('base64url')
  private readonly processes = new Map<ServiceName, ManagedProcess>()
  private postgresPort?: number
  private prepared = false
  private postgresStarted = false

  constructor(env: NodeJS.ProcessEnv, dependencies?: Partial<RuntimeDependencies>) {
    this.config = readRuntimeConfig(env)
    const runId = randomUUID()
    this.runDir = resolve(this.config.rootDir, `maintenance-e2e-${runId}`)
    this.containerName = `maintenance-e2e-${runId}`
    this.artifactsDir = join(this.runDir, 'artifacts')
    this.baseURL = `http://127.0.0.1:${this.config.frontendPort}`
    this.dependencies = {
      runCommand,
      startProcess: this.startChildProcess.bind(this),
      waitForPostgres: this.waitForPostgres.bind(this),
      waitForHttp: this.waitForHttp.bind(this),
      ...dependencies,
    }
  }

  async prepare(): Promise<void> {
    if (this.prepared) return
    await mkdir(join(this.runDir, 'postgres-data'), { recursive: true })
    await mkdir(join(this.runDir, 'logs'), { recursive: true })
    await mkdir(this.artifactsDir, { recursive: true })
    await writeFile(join(this.runDir, 'maintenance.sqlite3'), '')
    this.prepared = true
  }

  async start(): Promise<void> {
    await this.prepare()
    this.postgresPort = await findAvailablePort()
    await this.dependencies.runCommand('docker', [
      'run', '--detach', '--rm', '--name', this.containerName,
      '--publish', `127.0.0.1:${this.postgresPort}:5432`,
      '--mount', `type=bind,src=${join(this.runDir, 'postgres-data')},dst=/var/lib/postgresql/data`,
      '--env', `POSTGRES_DB=${this.databaseName}`,
      '--env', `POSTGRES_USER=${this.databaseUser}`,
      '--env', `POSTGRES_PASSWORD=${this.databasePassword}`,
      this.config.postgresImage,
    ])
    this.postgresStarted = true
    await this.waitForHealthy('postgres')
    this.processes.set('weknora', this.dependencies.startProcess(
      'weknora', 'go', ['run', './cmd/server'], { cwd: repositoryRoot(), env: this.weknoraEnvironment() },
    ))
    await this.waitForHealthy('weknora')
    this.processes.set('maintenance', this.dependencies.startProcess(
      'maintenance', executable('python'), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(this.config.maintenancePort)],
      { cwd: join(repositoryRoot(), 'extensions', 'maintenance-api'), env: this.maintenanceEnvironment() },
    ))
    await this.waitForHealthy('maintenance')
    this.processes.set('vite', this.dependencies.startProcess(
      'vite', executable('npm'), ['run', 'dev', '--', '--port', String(this.config.frontendPort), '--strictPort'],
      { cwd: join(repositoryRoot(), 'frontend'), env: this.viteEnvironment() },
    ))
  }

  async waitForHealthy(target: HealthTarget = 'all'): Promise<void> {
    if ((target === 'postgres' || target === 'all') && this.postgresStarted) {
      await this.dependencies.waitForPostgres(this.containerName, this.databaseUser, this.databaseName)
    }
    if ((target === 'weknora' || target === 'all') && this.processes.has('weknora')) {
      await this.dependencies.waitForHttp('weknora', `http://127.0.0.1:${this.config.weknoraPort}/health`)
    }
    if ((target === 'maintenance' || target === 'all') && this.processes.has('maintenance')) {
      await this.dependencies.waitForHttp('maintenance', `http://127.0.0.1:${this.config.maintenancePort}/health`)
    }
  }

  playwrightEnvironment(): NodeJS.ProcessEnv {
    return { E2E_BASE_URL: this.baseURL, E2E_PLAYWRIGHT_OUTPUT_DIR: this.artifactsDir }
  }

  async appendServiceLog(service: ServiceName, content: string): Promise<void> {
    await this.prepare()
    await writeFile(join(this.runDir, 'logs', `${service}.raw.log`), content, { flag: 'a' })
  }

  async stop({ failed }: { failed: boolean }): Promise<void> {
    const failures: unknown[] = []
    for (const name of [...serviceNames].reverse()) {
      const managedProcess = this.processes.get(name)
      if (!managedProcess) continue
      try {
        await managedProcess.stop()
      } catch (error) {
        failures.push(error)
      }
    }
    this.processes.clear()
    if (this.postgresStarted) {
      try {
        await this.dependencies.runCommand('docker', ['rm', '--force', this.containerName])
      } catch (error) {
        failures.push(error)
      }
      this.postgresStarted = false
    }
    try {
      if (failed) await this.retainRedactedArtifacts()
      await rm(join(this.runDir, 'postgres-data'), { recursive: true, force: true })
      await rm(join(this.runDir, 'maintenance.sqlite3'), { force: true })
      await rm(join(this.runDir, 'logs'), { recursive: true, force: true })
      if (!failed) await rm(this.runDir, { recursive: true, force: true })
    } catch (error) {
      failures.push(error)
    }
    if (failures.length > 0) throw new Error('Maintenance E2E cleanup failed')
  }

  private async retainRedactedArtifacts(): Promise<void> {
    const source = join(this.runDir, 'logs')
    const target = join(this.artifactsDir, 'logs')
    await mkdir(target, { recursive: true })
    for (const name of serviceNames) {
      try {
        const content = await readFile(join(source, `${name}.raw.log`), 'utf8')
        await writeFile(join(target, `${name}.log`), this.redactDiagnostic(content))
      } catch (error: unknown) {
        if (!(error instanceof Error) || !('code' in error) || error.code !== 'ENOENT') throw error
      }
    }
  }

  private redactDiagnostic(content: string): string {
    return content
      .replace(/\b[a-z][a-z0-9+.-]*:\/\/[^\s'"`]+/gi, '[redacted-url]')
      .replace(/\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|DATABASE_URL)[A-Z0-9_]*)\s*[=:]\s*\S+/gi, '$1=[redacted]')
      .replace(new RegExp(escapeRegularExpression(this.runDir), 'g'), '[run-directory]')
      .replace(/(?:[A-Za-z]:[\\/][^\s'"`]+|\/(?:tmp|private\/tmp|var\/folders)\/[^\s'"`]+)/g, '[temporary-path]')
  }

  private weknoraEnvironment(): NodeJS.ProcessEnv {
    return {
      ...process.env,
      DB_DRIVER: 'postgres', DB_HOST: '127.0.0.1', DB_PORT: String(this.postgresPort),
      DB_USER: this.databaseUser, DB_PASSWORD: this.databasePassword, DB_NAME: this.databaseName,
      SERVER_PORT: String(this.config.weknoraPort),
      WEKNORA_MAINTENANCE_ENABLED: 'true',
      WEKNORA_MAINTENANCE_BASE_URL: `http://127.0.0.1:${this.config.maintenancePort}`,
      WEKNORA_MAINTENANCE_SIGNING_SECRET: this.signingSecret,
      WEKNORA_MAINTENANCE_ISSUER: 'weknora', WEKNORA_MAINTENANCE_AUDIENCE: 'maintenance-api',
    }
  }

  private maintenanceEnvironment(): NodeJS.ProcessEnv {
    const databasePath = join(this.runDir, 'maintenance.sqlite3').replaceAll('\\', '/')
    return {
      ...process.env,
      DATABASE_URL: `sqlite:///${databasePath}`,
      INTERNAL_JWT_SECRET: this.signingSecret,
      INTERNAL_JWT_ISSUER: 'weknora', INTERNAL_JWT_AUDIENCE: 'maintenance-api',
    }
  }

  private viteEnvironment(): NodeJS.ProcessEnv {
    return { ...process.env, VITE_DEV_PROXY_TARGET: `http://127.0.0.1:${this.config.weknoraPort}` }
  }

  private startChildProcess(name: ServiceName, command: string, args: string[], options: ProcessOptions): ManagedProcess {
    const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
    const output = createWriteStream(join(this.runDir, 'logs', `${name}.raw.log`), { flags: 'a' })
    child.stdout.pipe(output)
    child.stderr.pipe(output)
    return { stop: () => stopChild(child) }
  }

  private async waitForPostgres(containerName: string, username: string, database: string): Promise<void> {
    await this.waitFor(() => this.dependencies.runCommand(
      'docker', ['exec', containerName, 'pg_isready', '--username', username, '--dbname', database],
    ))
  }

  private async waitForHttp(_name: ServiceName, url: string): Promise<void> {
    await this.waitFor(async () => {
      const response = await fetch(url)
      if (!response.ok) throw new Error('health check was unsuccessful')
    })
  }

  private async waitFor(check: () => Promise<void>): Promise<void> {
    const deadline = Date.now() + 60_000
    while (Date.now() < deadline) {
      try {
        await check()
        return
      } catch {
        await sleep(250)
      }
    }
    throw new Error('E2E service did not become healthy')
  }
}

function repositoryRoot(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
}

function escapeRegularExpression(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
