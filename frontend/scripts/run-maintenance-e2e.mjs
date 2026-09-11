import { spawn } from 'node:child_process'
import { register } from 'tsx/esm/api'

register()

const { MaintenanceE2ERuntime } = await import('../e2e/maintenance/runtime.ts')
const runtime = new MaintenanceE2ERuntime(process.env)
let failed = true

try {
  await runtime.start()
  const exitCode = await new Promise((resolveRun, rejectRun) => {
    const child = spawn('npx', ['playwright', 'test', '--config', 'playwright.config.ts', ...process.argv.slice(2)], {
      cwd: new URL('../', import.meta.url),
      env: { ...process.env, ...runtime.playwrightEnvironment() },
      stdio: 'inherit',
      windowsHide: true,
    })
    child.once('error', rejectRun)
    child.once('exit', (code) => resolveRun(code ?? 1))
  })
  failed = exitCode !== 0
  process.exitCode = exitCode
} catch {
  process.exitCode = 1
} finally {
  try {
    await runtime.stop({ failed })
  } catch {
    process.exitCode = 1
  }
}
