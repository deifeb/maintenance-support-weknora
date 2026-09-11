import { defineConfig } from '@playwright/test'
import { join } from 'node:path'

const artifactsDir = process.env.E2E_PLAYWRIGHT_OUTPUT_DIR ?? 'test-results'

export default defineConfig({
  testDir: './e2e/maintenance',
  workers: 1,
  fullyParallel: false,
  outputDir: join(artifactsDir, 'test-results'),
  reporter: [['html', { open: 'never', outputFolder: join(artifactsDir, 'playwright-report') }]],
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
