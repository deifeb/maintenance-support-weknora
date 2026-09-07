import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

import {
  createReportApi,
  toPublicSourceProvenance,
  type ReportApiClient,
} from '../../../../api/maintenance/reports.ts'
import { parseAttachmentFilename } from '../../../../api/maintenance/client.ts'
import type { MaintenanceResult } from '../../../../api/maintenance/types.ts'

type Call = {
  method: 'get' | 'post' | 'download'
  path: string
  body?: unknown
}

test('all lifecycle endpoint declarations expose the public ReportJobStatusRead envelope', () => {
  const source = readFileSync('src/api/maintenance/reports.ts', 'utf8')
  for (const name of ['generate', 'validate', 'finalize', 'regenerate']) {
    assert.match(source, new RegExp(`${name}Report\\(reportId: number\\): Promise<MaintenanceResult<ReportJobStatusRead>>`))
    assert.match(source, new RegExp('client.post<ReportJobStatusRead>\\(`\\$\\{reportPath\\(reportId\\)\\}/' + name))
  }
})

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: { request_id: 'request-1', tenant_id: 'tenant-1' },
  }
}

test('report API uses the C2D report endpoints and encoded query values', async () => {
  const calls: Call[] = []
  const client: ReportApiClient = {
    get: async <T>(path: string): Promise<MaintenanceResult<T>> => {
      calls.push({ method: 'get', path })
      return result({} as T)
    },
    post: async <T>(path: string, body: unknown): Promise<MaintenanceResult<T>> => {
      calls.push({ method: 'post', path, body })
      return result({} as T)
    },
    downloadWithMetadata: async (path: string) => {
      calls.push({ method: 'download', path })
      return {
        blob: new Blob(['report']),
        contentType: 'application/json',
        filename: 'report.json',
      }
    },
  }
  const api = createReportApi(client)

  await api.listReports({
    page: 2,
    page_size: 20,
    source_type: 'AI_SESSION',
    keyword: 'weekly report',
  })
  await api.createReportJob({
    title: 'Weekly',
    report_type: 'MANAGEMENT_DECISION',
    source_refs: [],
  })
  await api.createReportJob({
    title: 'Source report',
    report_type: 'MANAGEMENT_DECISION',
    source_refs: [{ type: 'AI_SESSION', id: 7, version: 'v2' }],
  })
  await api.getReportJob(42)
  await api.getReport(42)
  await api.listReportVersions(42)
  await api.generateReport(42)
  await api.validateReport(42)
  await api.finalizeReport(42)
  await api.regenerateReport(42)
  const exported = await api.exportReport(42, 'JSON')

  assert.equal(
    calls[0].path,
    '/v1/reports?page=2&page_size=20&source_type=AI_SESSION&keyword=weekly+report',
  )
  assert.deepEqual(calls[1], {
    method: 'post',
    path: '/v1/reports/jobs',
    body: {
      title: 'Weekly',
      report_type: 'MANAGEMENT_DECISION',
      source_refs: [],
    },
  })
  assert.deepEqual(calls[2], {
    method: 'post',
    path: '/v1/reports/jobs',
    body: {
      title: 'Source report',
      report_type: 'MANAGEMENT_DECISION',
      source_refs: [{ type: 'AI_SESSION', id: 7, version: 'v2' }],
    },
  })
  assert.deepEqual(calls.slice(3), [
    { method: 'get', path: '/v1/reports/jobs/42' },
    { method: 'get', path: '/v1/reports/42' },
    { method: 'get', path: '/v1/reports/42/versions' },
    { method: 'post', path: '/v1/reports/42/generate', body: {} },
    { method: 'post', path: '/v1/reports/42/validate', body: {} },
    { method: 'post', path: '/v1/reports/42/finalize', body: {} },
    { method: 'post', path: '/v1/reports/42/regenerate', body: {} },
    { method: 'download', path: '/v1/reports/42/exports/json' },
  ])
  assert.equal(exported.filename, 'report.json')
  assert.equal(exported.contentType, 'application/json')
})

test('public provenance selector preserves only C2D display fields', () => {
  assert.deepEqual(
    toPublicSourceProvenance({
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      source_snapshot_json: { private: true },
      sources: [{
        type: 'AI_SESSION',
        id: 7,
        version: 'v2',
        lineage_id: 'lineage-1',
        digest: 'a'.repeat(64),
        tenant_id: 'private',
        database_record_json: { secret: true },
      }],
    }),
    {
      kind: 'authoritative',
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      sources: [{
        type: 'AI_SESSION',
        id: 7,
        version: 'v2',
        lineage_id: 'lineage-1',
        digest: 'a'.repeat(64),
      }],
    },
  )
})

test('public provenance selector supports C2D legacy and unavailable payloads', () => {
  assert.deepEqual(
    toPublicSourceProvenance({
      capture_mode: 'LEGACY_RECONSTRUCTED',
      provenance_completeness: 'PERSISTED_LINKS_ONLY',
      sources: {
        session: { id: 7, version: 'v2', session_code: 'S-7', tenant_id: 'private' },
        inventory: { snapshot_at: '2026-09-06', source_snapshot_json: { secret: true } },
      },
    }),
    {
      kind: 'legacy',
      capture_mode: 'LEGACY_RECONSTRUCTED',
      provenance_completeness: 'PERSISTED_LINKS_ONLY',
      sources: {
        session: { id: 7, version: 'v2', session_code: 'S-7' },
        inventory: { snapshot_at: '2026-09-06' },
      },
    },
  )
  assert.deepEqual(toPublicSourceProvenance({}), { kind: 'unavailable' })
})

test('authoritative provenance preserves nullable digest and scalar lineage only', () => {
  assert.deepEqual(
    toPublicSourceProvenance({
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      sources: [{
        type: 'AI_SESSION',
        id: 7,
        version: 'v2',
        lineage_id: 12,
        digest: null,
        source_snapshot_json: { private: true },
      }],
    }),
    {
      kind: 'authoritative',
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      sources: [{
        type: 'AI_SESSION',
        id: 7,
        version: 'v2',
        lineage_id: 12,
        digest: null,
      }],
    },
  )
  assert.deepEqual(
    toPublicSourceProvenance({
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      sources: [{
        type: 'AI_SESSION', id: 7, version: 'v2', lineage_id: {}, digest: null,
      }],
    }),
    { kind: 'unavailable' },
  )
})

test('attachment filename parsing rejects unsafe or non-attachment names', () => {
  assert.equal(
    parseAttachmentFilename('attachment; filename="RPT-1-v2.docx"'),
    'RPT-1-v2.docx',
  )
  assert.equal(
    parseAttachmentFilename('inline; filename="report.docx"'),
    'download',
  )
  assert.equal(
    parseAttachmentFilename('attachment; filename="../report.docx"'),
    'download',
  )
})
