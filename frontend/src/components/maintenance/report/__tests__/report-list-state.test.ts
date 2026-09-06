import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const centerPath = new URL('../../../../views/maintenance/reports/ReportCenter.vue', import.meta.url)
const tablePath = new URL('../ReportListTable.vue', import.meta.url)

function source(url: URL): string {
  return readFileSync(url, 'utf8')
}

function exportedFunction(sourceText: string, name: string): (...args: any[]) => any {
  const marker = `export function ${name}`
  const start = sourceText.indexOf(marker)
  assert.notEqual(start, -1, `${name} must be exported from ReportCenter.vue`)
  const bodyStart = sourceText.indexOf('{', sourceText.indexOf(')', start))
  let depth = 0
  let end = bodyStart
  for (; end < sourceText.length; end += 1) {
    if (sourceText[end] === '{') depth += 1
    if (sourceText[end] === '}' && --depth === 0) break
  }
  const declaration = sourceText.slice(start, end + 1)
    .replace(/^export\s+/, '')
    .replace(/input:\s*Record<string, unknown>/, 'input')
    .replace(/const positive:[\s\S]*?= \(value, fallback\) =>/, 'const positive = (value, fallback) =>')
    .replace(/const text:[\s\S]*?= \(value\) =>/, 'const text = (value) =>')
    .replace(/const one:[\s\S]*?= \(value\) =>/, 'const one = (value) =>')
  return new Function(`return (${declaration})`)() as (...args: any[]) => any
}

test('normalizes defaults, removes blank filters, preserves source filters, and rejects unsupported keys', () => {
  const normalizeReportListQuery = exportedFunction(
    source(centerPath),
    'normalizeReportListQuery',
  )

  assert.deepEqual(
    normalizeReportListQuery({ keyword: '', source_type: 'SESSION', page: 0, generator: 'fake' }),
    { page: 1, page_size: 20, source_type: 'SESSION', sort_by: 'created_at', sort_order: 'desc' },
  )
  assert.deepEqual(
    normalizeReportListQuery({ source_id: 7, source_version: 'v3', session_id: 11 }),
    { page: 1, page_size: 20, source_id: 7, source_version: 'v3', session_id: 11, sort_by: 'created_at', sort_order: 'desc' },
  )
})

test('report rows open the established detail route and table renders only allowed actions', () => {
  const [center, table] = [source(centerPath), source(tablePath)]

  assert.match(center, /router\.push\(\{\s*name:\s*'maintenanceReportDetail',\s*params:\s*\{\s*reportId\s*\}/s)
  assert.match(table, /getReportActions/)
  assert.match(table, /v-for="action in reportActions\(report\)"/)
})
