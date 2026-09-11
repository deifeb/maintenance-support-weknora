import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/maintenance',
  workers: 1,
  fullyParallel: false,
  outputDir: process.env.E2E_PLAYWRIGHT_OUTPUT_DIR,
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
})
