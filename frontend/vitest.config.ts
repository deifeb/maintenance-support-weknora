import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  test: {
    environment: 'jsdom',
    // Existing node:test suites continue to run through npm test.
    include: [
      'src/components/maintenance/report/__tests__/report-list-state.test.ts',
      'src/components/maintenance/report/__tests__/report-detail-state.test.ts',
    ],
  },
})
