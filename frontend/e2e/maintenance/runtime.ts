const diagnosticPortKeys = [
  'E2E_FRONTEND_PORT',
  'E2E_MAINTENANCE_PORT',
  'E2E_WEKNORA_PORT',
] as const

const sensitiveValue = /(TOKEN|SECRET|PASSWORD|API_KEY|BEARER)/i
const dockerImageReference = /^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?\/)*[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[a-z0-9][a-z0-9._-]*)?$/

function isPort(value: string): boolean {
  const port = Number(value)
  return /^\d+$/.test(value) && Number.isInteger(port) && port >= 1024 && port <= 65535
}

function isSafeDockerImage(value: string): boolean {
  return dockerImageReference.test(value) && !sensitiveValue.test(value)
}

export function sanitizeCommandEnvironment(env: NodeJS.ProcessEnv): Record<string, string> {
  return Object.fromEntries(diagnosticPortKeys.flatMap((key) => {
    const value = env[key]
    return value !== undefined && isPort(value) ? [[key, value]] : []
  }))
}

export function readRuntimeConfig(env: NodeJS.ProcessEnv) {
  const rootDir = env.E2E_ROOT_DIR?.trim()
  if (!rootDir) throw new Error('E2E_ROOT_DIR is required')

  const port = (name: string, fallback: number) => {
    const rawValue = env[name] ?? String(fallback)
    if (!isPort(rawValue)) {
      throw new Error(`${name} must be between 1024 and 65535`)
    }
    return Number(rawValue)
  }

  const postgresImage = env.E2E_POSTGRES_IMAGE?.trim() ?? 'postgres:17-alpine'
  if (!isSafeDockerImage(postgresImage)) {
    throw new Error('E2E_POSTGRES_IMAGE must be a safe Docker image reference')
  }

  return {
    rootDir,
    frontendPort: port('E2E_FRONTEND_PORT', 5174),
    weknoraPort: port('E2E_WEKNORA_PORT', 8081),
    maintenancePort: port('E2E_MAINTENANCE_PORT', 8101),
    postgresImage,
  }
}
