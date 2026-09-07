import { readdir, readFile, stat } from 'node:fs/promises'
import { resolve } from 'node:path'
import { spawn } from 'node:child_process'

const root = process.cwd()

async function collectTestFiles(target) {
  const absolute = resolve(root, target)
  if ((await stat(absolute)).isFile()) return absolute.endsWith('.test.ts') ? [absolute] : []

  const entries = await readdir(absolute, { withFileTypes: true })
  const nested = await Promise.all(entries.map(async (entry) => collectTestFiles(
    `${target}/${entry.name}`,
  ).catch((error) => entry.isDirectory() ? Promise.reject(error) : [])))
  return nested.flat()
}

function run(command, args) {
  return new Promise((resolveRun, reject) => {
    const entry = command === 'tsx'
      ? 'node_modules/tsx/dist/cli.mjs'
      : 'node_modules/vitest/vitest.mjs'
    const child = spawn(process.execPath, [entry, ...args], { cwd: root, stdio: 'inherit' })
    child.on('error', reject)
    child.on('exit', (code, signal) => resolveRun(code === 0 && !signal))
  })
}

const requested = process.argv.slice(2)
const targets = requested.length > 0 ? requested : ['src']
const files = (await Promise.all(targets.map(collectTestFiles))).flat().sort()
const nodeTests = []
const vitestTests = []

for (const file of files) {
  const source = await readFile(file, 'utf8')
  if (/from ['"]vitest['"]/.test(source)) vitestTests.push(file)
  else nodeTests.push(file)
}

if (files.length === 0) {
  throw new Error(`No .test.ts files matched: ${targets.join(', ')}`)
}

const results = await Promise.all([
  nodeTests.length > 0 ? run('tsx', ['--tsconfig', 'tsconfig.app.json', '--test', ...nodeTests]) : true,
  vitestTests.length > 0 ? run('vitest', ['run', ...vitestTests]) : true,
])

process.exitCode = results.every(Boolean) ? 0 : 1
