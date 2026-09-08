<template>
  <div class="report-list-table">
    <table>
      <thead><tr><th>{{ t('maintenance.reports.columns.code') }}</th><th>{{ t('maintenance.reports.columns.title') }}</th><th>{{ t('maintenance.reports.columns.type') }}</th><th>{{ t('maintenance.reports.columns.jobStatus') }}</th><th>{{ t('maintenance.reports.columns.version') }}</th><th>{{ t('maintenance.reports.columns.progress') }}</th><th>{{ t('maintenance.reports.columns.created') }}</th><th>{{ t('maintenance.reports.columns.updated') }}</th><th>{{ t('maintenance.reports.columns.actions') }}</th></tr></thead>
      <tbody>
        <tr v-for="report in reports" :key="report.report_id" tabindex="0" @click="emit('open', report.report_id)" @keydown.enter="emit('open', report.report_id)">
          <td><code>{{ report.report_code }}</code></td><td>{{ report.title }}</td><td>{{ t(`maintenance.reports.types.${report.report_type}`) }}</td><td>{{ t(`maintenance.reports.jobStatuses.${report.job_status}`) }}</td>
          <td>{{ report.latest_version ? `v${report.latest_version.version_number} · ${t(`maintenance.reports.versionStatuses.${report.latest_version.status}`)}` : '—' }}</td><td>{{ report.progress_percent }}%</td><td>{{ formatDate(report.created_at) }}</td><td>{{ formatDate(report.updated_at) }}</td>
          <td class="report-list-table__actions" @click.stop @keydown.enter.stop @keydown.space.stop><button v-for="action in reportActions(report)" :key="action" type="button" @click="emit(action === 'view' ? 'open' : action, report.report_id)">{{ t(`maintenance.reports.actions.${action}`) }}</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { getReportActions, type ReportRole } from './report-actions'
import type { ReportAction, ReportListItem } from './report-types'

type ReportRowAction = 'generate' | 'validate' | 'finalize' | 'regenerate' | 'export'
type ReportDisplayAction = 'view' | ReportRowAction
const reportDisplayActions: readonly ReportDisplayAction[] = ['view', 'generate', 'validate', 'finalize', 'regenerate', 'export']

const props = withDefaults(defineProps<{ reports: ReportListItem[]; role?: ReportRole }>(), { role: 'VIEWER' })
const emit = defineEmits<{ (event: 'open' | ReportRowAction, reportId: number): void }>()
const { t, locale } = useI18n()

function isReportDisplayAction(action: ReportAction): action is ReportDisplayAction {
  return reportDisplayActions.includes(action as ReportDisplayAction)
}
function reportActions(report: ReportListItem): ReportDisplayAction[] {
  return getReportActions({ role: props.role, jobStatus: report.job_status, versionStatus: report.latest_version?.status ?? null })
    .filter(isReportDisplayAction)
}
function formatDate(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
</script>

<style scoped>
.report-list-table { overflow-x: auto; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
table { width: 100%; border-collapse: collapse; } th, td { padding: 12px; border-bottom: 1px solid var(--td-component-stroke); color: var(--td-text-color-secondary); font-size: 12px; text-align: left; white-space: nowrap; } th { font-size: 10px; text-transform: uppercase; } tbody tr { cursor: pointer; } code { color: var(--td-text-color-primary); } .report-list-table__actions { display: flex; gap: 6px; } button { border: 0; background: none; color: var(--td-brand-color); cursor: pointer; font: inherit; }
</style>
