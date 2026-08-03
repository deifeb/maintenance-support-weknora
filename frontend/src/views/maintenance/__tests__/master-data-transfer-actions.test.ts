import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  createMasterDataTransferActions,
  createXlsxDownloadTrigger,
  type MasterDataTransferApi,
} from '../master-data/master-data-transfer-actions.ts'

const error = {
  code: 'EXPORT_FAILED',
  message: 'Export failed',
  retryable: true,
}

function createHarness(overrides: {
  resourceKey?: string
  transferKey?: string
  generation?: number
  query?: Record<string, unknown>
  api?: Partial<MasterDataTransferApi>
} = {}) {
  let resourceKey = overrides.resourceKey ?? 'parts'
  let generation = overrides.generation ?? 4
  const downloads: Array<{ blob: Blob; filename: string }> = []
  const errors: unknown[] = []
  const busy: boolean[] = []
  let refreshes = 0
  const api: MasterDataTransferApi = {
    downloadTemplate: async () => new Blob(['template']),
    exportResource: async () => new Blob(['export']),
    ...overrides.api,
  }
  const actions = createMasterDataTransferActions({
    api,
    getResource: () => ({
      key: resourceKey,
      transfer: { exportKey: overrides.transferKey ?? 'parts', importable: true },
    }),
    getQuery: () => ({
      keyword: 'applied keyword',
      include_inactive: true,
      sort_by: 'code',
      sort_order: 'desc',
      ...overrides.query,
    }),
    getGeneration: () => generation,
    download: (blob, filename) => downloads.push({ blob, filename }),
    onBusyChange: (value) => busy.push(value),
    onError: (value) => errors.push(value),
    normalizeError: () => error,
    refresh: async () => { refreshes += 1 },
  })
  return {
    actions,
    api,
    busy,
    downloads,
    errors,
    get refreshes() { return refreshes },
    setGeneration(value: number) { generation = value },
    setResource(value: string) { resourceKey = value },
  }
}

test('export forwards exactly the applied server-table query and never tenant data', async () => {
  const calls: Array<{ key: string; query: unknown }> = []
  const harness = createHarness({
    query: { tenant_id: 'must-not-leave-browser' },
    api: {
      exportResource: async (key, query) => {
        calls.push({ key, query })
        return new Blob(['export'])
      },
    },
  })

  await harness.actions.exportCurrentResults()

  assert.deepEqual(calls, [{
    key: 'parts',
    query: {
      keyword: 'applied keyword',
      include_inactive: true,
      sort_by: 'code',
      sort_order: 'desc',
    },
  }])
  assert.deepEqual(harness.downloads.map(({ filename }) => filename), [
    'parts-export.xlsx',
  ])
})

test('template and export are mutually exclusive while a transfer is in flight', async () => {
  let resolveTemplate: ((blob: Blob) => void) | undefined
  const template = new Promise<Blob>((resolve) => { resolveTemplate = resolve })
  let exports = 0
  const harness = createHarness({
    api: {
      downloadTemplate: async () => template,
      exportResource: async () => {
        exports += 1
        return new Blob(['export'])
      },
    },
  })

  const downloading = harness.actions.downloadTemplate()
  await Promise.resolve()
  await harness.actions.exportCurrentResults()
  resolveTemplate?.(new Blob(['template']))
  await downloading

  assert.equal(exports, 0)
  assert.deepEqual(harness.busy, [true, false])
})

test('export download filenames are sanitized before the injected download trigger runs', async () => {
  const harness = createHarness({ transferKey: 'parts / active' })

  await harness.actions.exportCurrentResults()

  assert.deepEqual(harness.downloads.map(({ filename }) => filename), [
    'parts-active-export.xlsx',
  ])
})

test('transfer errors are normalized and reported to the page error path', async () => {
  const harness = createHarness({
    api: {
      exportResource: async () => { throw new Error('network down') },
    },
  })

  await harness.actions.exportCurrentResults()

  assert.deepEqual(harness.errors, [error])
  assert.deepEqual(harness.busy, [true, false])
})

test('a pending export cannot download into a newer resource after it resolves', async () => {
  let resolveExport: ((blob: Blob) => void) | undefined
  const pendingExport = new Promise<Blob>((resolve) => { resolveExport = resolve })
  const harness = createHarness({
    api: { exportResource: async () => pendingExport },
  })

  const exporting = harness.actions.exportCurrentResults()
  await Promise.resolve()
  harness.setGeneration(5)
  harness.setResource('suppliers')
  resolveExport?.(new Blob(['old parts export']))
  await exporting

  assert.deepEqual(harness.downloads, [])
  assert.deepEqual(harness.errors, [])
  assert.deepEqual(harness.busy, [true, false])
})

test('a rejected stale export cannot surface an error in a newer resource', async () => {
  let rejectExport: ((reason?: unknown) => void) | undefined
  const pendingExport = new Promise<Blob>((_resolve, reject) => { rejectExport = reject })
  const harness = createHarness({
    api: { exportResource: async () => pendingExport },
  })

  const exporting = harness.actions.exportCurrentResults()
  await Promise.resolve()
  harness.setGeneration(5)
  harness.setResource('suppliers')
  rejectExport?.(new Error('old parts export failed'))
  await exporting

  assert.deepEqual(harness.downloads, [])
  assert.deepEqual(harness.errors, [])
  assert.deepEqual(harness.busy, [true, false])
})

test('completion refreshes only the resource and generation that opened the dialog', async () => {
  const harness = createHarness()

  await harness.actions.handleCompleted({ resourceKey: 'parts', generation: 4 })
  harness.setGeneration(5)
  await harness.actions.handleCompleted({ resourceKey: 'parts', generation: 4 })
  harness.setGeneration(4)
  harness.setResource('suppliers')
  await harness.actions.handleCompleted({ resourceKey: 'parts', generation: 4 })

  assert.equal(harness.refreshes, 1)
})

test('browser download removes its temporary link and revokes the object URL one turn later', () => {
  const callbacks: Array<() => void> = []
  let removed = 0
  const appended: unknown[] = []
  const revoked: string[] = []
  const link = {
    href: '',
    download: '',
    style: { display: '' },
    click() {},
    remove() { removed += 1 },
  }
  const download = createXlsxDownloadTrigger({
    document: {
      body: { append: (value: unknown) => appended.push(value) },
      createElement: () => link,
    },
    objectUrls: {
      createObjectURL: () => 'blob:transfer',
      revokeObjectURL: (url) => revoked.push(url),
    },
    defer: (callback) => { callbacks.push(callback) },
  })

  download(new Blob(['workbook']), 'parts-export.xlsx')

  assert.equal(link.download, 'parts-export.xlsx')
  assert.equal(removed, 1)
  assert.deepEqual(appended, [link])
  assert.deepEqual(revoked, [])
  assert.equal(callbacks.length, 1)
  callbacks[0]()
  assert.deepEqual(revoked, ['blob:transfer'])
})

test('page wires dialog error events into actionError and uses the injected controller', () => {
  const source = readFileSync(
    new URL('../master-data/MasterDataListPage.vue', import.meta.url),
    'utf8',
  )

  assert.match(source, /createMasterDataTransferActions\(/)
  assert.match(source, /@error="reportImportError"/)
  assert.match(source, /function reportImportError\(error: MaintenanceClientError\)/)
  assert.match(source, /actionError\.value\s*=\s*error/)
})

test('resource changes clear the prior page action error before resetting the dialog', () => {
  const source = readFileSync(
    new URL('../master-data/MasterDataListPage.vue', import.meta.url),
    'utf8',
  )

  assert.match(
    source,
    /closeDrawer\(\)\s*actionError\.value\s*=\s*null\s*importDialogOpen\.value\s*=\s*false/,
  )
})
