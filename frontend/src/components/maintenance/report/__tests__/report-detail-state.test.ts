import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

import {
  toPublicSourceProvenance,
  type ReportDetail,
} from '../../../../api/maintenance/reports.ts'

const componentUrl = new URL('../ReportProvenancePanel.vue', import.meta.url)
const timelineUrl = new URL('../ReportVersionTimeline.vue', import.meta.url)
const detailUrl = new URL('../../../../views/maintenance/reports/ReportDetail.vue', import.meta.url)
const routerUrl = new URL('../../../../router/maintenance.ts', import.meta.url)

function source(url: URL): string {
  assert.equal(existsSync(url), true, `${url.pathname} must exist`)
  return readFileSync(url, 'utf8')
}

function toProvenanceRows(detail: ReportDetail) {
  const provenance = toPublicSourceProvenance(detail.source_versions)
  if (provenance.kind !== 'authoritative') return []
  return provenance.sources.map((item) => ({
    type: item.type === 'AI_SESSION' ? 'SESSION' : item.type,
    id: item.id,
    version: item.version,
    name: item.type === 'AI_SESSION' ? 'Scenario input' : item.type,
  }))
}

test('detail provenance displays only whitelisted C2D source version fields', () => {
  const detail: ReportDetail = {
    report_id: 7, report_code: 'RPT-7', report_type: 'MANAGEMENT_DECISION',
    title: 'Weekly report', status: 'DRAFT', version_id: 9, version_number: 2,
    parent_version_id: 8, template_version: 'v3', input_digest: 'input-digest',
    generation_mode: 'MANUAL', generated_at: '2026-09-07T00:00:00Z', sections: [], citations: [],
    source_versions: {
      capture_mode: 'AUTHORITATIVE_CREATE', provenance_completeness: 'AUTHORITATIVE',
      source_snapshot_json: { private: true }, tenant_id: 'tenant-1', database_record_json: { secret: true }, token: 'secret',
      sources: [{ type: 'AI_SESSION', id: 7, version: 'v2', lineage_id: 'lineage-1', digest: 'digest', token: 'secret' }],
    },
  }

  assert.deepEqual(toProvenanceRows(detail), [{ type: 'SESSION', id: 7, version: 'v2', name: 'Scenario input' }])

  const renderedText = source(componentUrl)
  assert.equal(renderedText.includes('source_snapshot_json'), false)
  assert.equal(renderedText.includes('database_record_json'), false)
  assert.equal(renderedText.includes('tenant_id'), false)
  assert.equal(renderedText.includes('JSON.stringify'), false)
})

test('detail timeline exposes lineage and immutable generation evidence', () => {
  const timeline = source(timelineUrl)
  for (const field of ['parent_version_id', 'template_version', 'generation_mode', 'generated_at', 'content_digest']) {
    assert.match(timeline, new RegExp(`\\b${field}\\b`))
  }
  assert.doesNotMatch(timeline, /@(?:generate|validate|finalize|regenerate)|reportApi\.(?:generate|validate|finalize|regenerate)/)
})

test('detail route is registered and detail surface validates the route before loading', () => {
  const router = source(routerUrl)
  assert.match(router, /path:\s*'reports\/:reportId'/)
  assert.match(router, /name:\s*'maintenanceReportDetail'/)
  assert.match(router, /ReportDetail\.vue/)
  assert.match(router, /hideInMaintenanceMenu:\s*true/)

  const detail = source(detailUrl)
  assert.match(detail, /reportApi\.getReport/)
  assert.match(detail, /reportApi\.listReportVersions/)
  assert.match(detail, /positiveReportRouteId/)
  assert.doesNotMatch(detail, /JSON\.stringify/)
})
