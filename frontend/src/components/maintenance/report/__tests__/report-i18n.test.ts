import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { parse as parseTemplate, NodeTypes } from '@vue/compiler-dom'
import en from '../../../../i18n/locales/en-US.ts'
import zh from '../../../../i18n/locales/zh-CN.ts'
import { REPORT_TYPES, REPORT_SOURCE_TYPES, REPORT_JOB_STATUSES, REPORT_VERSION_STATUSES } from '../report-types.ts'

test('C3 visible copy uses translated keys in both locales', () => {
  const files = ['ReportProvenancePanel', 'ReportVersionTimeline', 'ReportValidationFindings', 'ReportSections', 'ReportGenerationDialog', 'ReportListTable', 'ReportFilterBar']
    .map((name) => `src/components/maintenance/report/${name}.vue`)
  files.push('src/views/maintenance/reports/ReportDetail.vue')
  for (const file of files) {
    const source = readFileSync(file, 'utf8')
    const template = parse(source).descriptor.template!.content
    const walk = (node: any) => {
      if (node.type === NodeTypes.TEXT) assert.doesNotMatch(node.content, /[A-Za-z]{2}/, `${file}: hardcoded visible text`)
      for (const child of node.children ?? []) walk(child)
    }
    walk(parseTemplate(template))
    for (const match of source.matchAll(/t\('maintenance\.reports\.([\w.]+)'/g)) {
      for (const locale of [en, zh]) {
        const value = match[1].split('.').reduce((object: any, key) => object?.[key], locale.maintenance.reports)
        assert.equal(typeof value, 'string', `${file}: missing ${match[1]}`)
      }
    }
  }
  for (const locale of [en, zh]) {
    for (const [group, values] of Object.entries({ types: REPORT_TYPES, sourceTypes: REPORT_SOURCE_TYPES, jobStatuses: REPORT_JOB_STATUSES, versionStatuses: REPORT_VERSION_STATUSES })) {
      for (const value of values) assert.equal(typeof (locale.maintenance.reports as any)[group]?.[value], 'string', `missing ${group}.${value}`)
    }
  }
})
