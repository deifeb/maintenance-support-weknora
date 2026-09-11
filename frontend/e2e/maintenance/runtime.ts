export function sanitizeCommandEnvironment(env: NodeJS.ProcessEnv): Record<string, string> {
  const diagnosticKeys = new Set([
    'E2E_FRONTEND_PORT',
    'E2E_MAINTENANCE_PORT',
    'E2E_POSTGRES_IMAGE',
    'E2E_WEKNORA_PORT',
  ])

  return Object.fromEntries(Object.entries(env).filter(([key, value]) => (
    value !== undefined && diagnosticKeys.has(key)
  )))
}

export function readRuntimeConfig(env: NodeJS.ProcessEnv) {
  const rootDir = env.E2E_ROOT_DIR?.trim()
  if (!rootDir) throw new Error('E2E_ROOT_DIR is required')

  const port = (name: string, fallback: number) => {
    const value = Number(env[name] ?? fallback)
    if (!Number.isInteger(value) || value < 1024 || value > 65535) {
      throw new Error(`${name} must be between 1024 and 65535`)
    }
    return value
  }

  return {
    rootDir,
    frontendPort: port('E2E_FRONTEND_PORT', 5174),
    weknoraPort: port('E2E_WEKNORA_PORT', 8081),
    maintenancePort: port('E2E_MAINTENANCE_PORT', 8101),
    postgresImage: env.E2E_POSTGRES_IMAGE ?? 'postgres:17-alpine',
  }
}
