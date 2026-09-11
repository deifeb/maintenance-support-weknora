import { expect, test } from '@playwright/test'
import { mkdir, readFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'

import { actorAliases, type ActorAlias } from './fixtures'

interface ActorManifestEntry {
  role: string
}

interface ActorManifest {
  actors: Partial<Record<ActorAlias, ActorManifestEntry>>
}

async function readActorManifest(): Promise<ActorManifest> {
  const manifestPath = process.env.E2E_ACTOR_MANIFEST_PATH
  if (!manifestPath) throw new Error('E2E_ACTOR_MANIFEST_PATH is required')
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8')) as ActorManifest
  for (const alias of actorAliases) {
    const actor = manifest.actors?.[alias]
    if (!actor?.role) throw new Error(`actor alias ${alias} is incomplete`)
  }
  return manifest
}

test('creates real browser storage states for maintenance actors', async ({ browser }) => {
  const password = process.env.E2E_TEST_PASSWORD
  if (!password) throw new Error('E2E_TEST_PASSWORD is required')
  const manifestPath = process.env.E2E_ACTOR_MANIFEST_PATH
  if (!manifestPath) throw new Error('E2E_ACTOR_MANIFEST_PATH is required')
  const manifest = await readActorManifest()
  const stateDir = join(dirname(manifestPath), 'auth-states')
  await mkdir(stateDir, { recursive: true })

  for (const alias of actorAliases) {
    const actor = manifest.actors[alias]
    if (!actor) throw new Error(`actor alias ${alias} is missing`)
    const context = await browser.newContext()
    const page = await context.newPage()
    try {
      await page.goto('/login')
      await page.locator('input[autocomplete="email"]').fill(`${alias}@example.test`)
      await page.locator('input[autocomplete="current-password"]').fill(password)
      await page.getByRole('button', { name: /登录|log in|sign in/i }).click()
      await page.goto('/platform/maintenance/')
      await expect(page).toHaveURL(/\/platform\/maintenance\//)
      await context.storageState({ path: join(stateDir, `${alias}.json`) })
    } finally {
      await context.close()
    }
  }
})
