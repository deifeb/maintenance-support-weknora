<template>
  <main class="report-detail">
    <header><button type="button" @click="backToReports">{{ t('maintenance.reports.detail.back') }}</button><h1>{{ detail?.title ?? t('maintenance.reports.detail.title') }}</h1><button type="button" :disabled="busy || invalidRoute" @click="refreshManually">{{ t('maintenance.reports.detail.refresh') }}</button></header>
    <p v-if="invalidRoute" role="alert">{{ t('maintenance.reports.detail.invalidId') }}</p>
    <p v-else-if="notFound" role="status">{{ t('maintenance.reports.detail.notFound') }}</p>
    <p v-else-if="errorKey" role="alert">{{ t(errorKey) }}<template v-if="requestId"> {{ t('maintenance.reports.errors.requestId', { requestId }) }}</template></p>
    <p v-else-if="loading && !detail" role="status">{{ t('maintenance.reports.detail.loading') }}</p>
    <template v-else-if="detail">
      <section class="report-detail__summary"><p>{{ detail.report_code }} · {{ t(`maintenance.reports.types.${detail.report_type}`) }}</p><p>{{ t('maintenance.reports.columns.jobStatus') }}: {{ detail.job_status ? t(`maintenance.reports.jobStatuses.${detail.job_status}`) : t('maintenance.reports.presentation.unavailable') }}</p><p>{{ t('maintenance.reports.presentation.version') }} {{ detail.version_number }} · {{ t(`maintenance.reports.versionStatuses.${detail.status}`) }}</p></section>
      <ReportLifecycleActions v-if="detail.job_status" :report-id="detail.report_id" :job-status="detail.job_status" :version-status="detail.status" :version-generated="versionGenerated" :actions="lifecycleActions" :refresh="refreshOwnedReport" :busy="busy" />
      <ReportExportActions :report-id="detail.report_id" :actions="actions" />
      <ReportRegenerateDialog v-if="actions.includes('regenerate')" :open="regenerateOpen" :allowed="actions.includes('regenerate')" :report-id="detail.report_id" :refresh="refreshOwnedReport" :busy="busy" @close="regenerateOpen = false" />
      <button v-if="actions.includes('regenerate')" type="button" :disabled="busy" @click="openRegenerate">{{ t('maintenance.reports.detail.regenerate') }}</button>
      <ReportProvenancePanel :sources="provenanceSources" /><ReportVersionTimeline :versions="versions" /><ReportValidationFindings :findings="detail.findings ?? []" /><ReportSections :sections="detail.sections" :citations="detail.citations" />
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { reportApi, toPublicSourceProvenance, type PublicSourceVersion, type ReportDetail, type ReportVersionSummary } from '@/api/maintenance/reports'
import ReportProvenancePanel from '@/components/maintenance/report/ReportProvenancePanel.vue'
import ReportSections from '@/components/maintenance/report/ReportSections.vue'
import ReportValidationFindings from '@/components/maintenance/report/ReportValidationFindings.vue'
import ReportVersionTimeline from '@/components/maintenance/report/ReportVersionTimeline.vue'
import ReportLifecycleActions from '@/components/maintenance/report/ReportLifecycleActions.vue'
import ReportRegenerateDialog from '@/components/maintenance/report/ReportRegenerateDialog.vue'
import ReportExportActions from '@/components/maintenance/report/ReportExportActions.vue'
import { getReportActions, reportErrorMessageKey, type ReportRole } from '@/components/maintenance/report/report-actions'
import type { ReportAction } from '@/components/maintenance/report/report-types'
import { useAuthStore } from '@/stores/auth'
import { pendingReportMutations, registerReportReader } from '@/components/maintenance/report/report-mutation-state'

const { t } = useI18n(); const route = useRoute(); const router = useRouter(); const authStore = useAuthStore(); const detail = ref<ReportDetail | null>(null); const versions = ref<ReportVersionSummary[]>([]); const loading = ref(false); const errorKey = ref(''); const requestId = ref(''); const notFound = ref(false); const regenerateOpen = ref(false); let request = 0
const reportRole = computed<ReportRole>(() => authStore.hasRole('admin') ? 'ADMIN' : authStore.hasRole('contributor') ? 'CONTRIBUTOR' : 'VIEWER')
const versionGenerated = computed(() => Boolean(detail.value?.generated_at) || Boolean(detail.value?.sections.length))
const actions = computed<ReportAction[]>(() => detail.value && detail.value.job_status ? getReportActions({ role: reportRole.value, jobStatus: detail.value.job_status, versionStatus: detail.value.status, versionGenerated: versionGenerated.value, hasUnresolvedFindings: detail.value.findings?.some((finding) => !finding.resolved) }) : [])
const lifecycleActions = computed<ReportAction[]>(() => actions.value.filter((action) => action !== 'regenerate'))
function positiveReportRouteId(value: unknown): number | null { const raw = Array.isArray(value) ? value[0] : value; const parsed = typeof raw === 'number' ? raw : typeof raw === 'string' && /^\d+$/.test(raw) ? Number(raw) : NaN; return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null }
const routeId = computed(() => positiveReportRouteId(route.params.reportId)); const invalidRoute = computed(() => routeId.value === null)
let disposed = false
const refreshOwnedReport = computed(() => {
  const reportId = routeId.value
  return async (): Promise<void> => {
    if (!disposed && routeId.value === reportId) await load()
  }
})
const busy = computed(() => loading.value || (routeId.value !== null && pendingReportMutations.has(routeId.value)))
function refreshManually(): void { if (!busy.value) void load() }
function openRegenerate(): void { if (!busy.value) regenerateOpen.value = true }
const provenanceSources = computed<PublicSourceVersion[] | null>(() => { const provenance = detail.value ? toPublicSourceProvenance(detail.value.source_versions) : { kind: 'unavailable' as const }; return provenance.kind === 'authoritative' ? provenance.sources : null })
async function load(): Promise<void> { const current = ++request; const reportId = routeId.value; if (reportId === null) { loading.value = false; detail.value = null; versions.value = []; errorKey.value = ''; requestId.value = ''; notFound.value = false; return }; loading.value = true; errorKey.value = ''; requestId.value = ''; notFound.value = false; detail.value = null; versions.value = []; try { const [report, timeline] = await Promise.all([reportApi.getReport(reportId), reportApi.listReportVersions(reportId)]); if (current !== request) return; detail.value = report.data; versions.value = timeline.data } catch (reason) { if (current !== request) return; const normalized = normalizeMaintenanceError(reason); notFound.value = normalized.status === 404; if (!notFound.value) { errorKey.value = reportErrorMessageKey(normalized.code); requestId.value = normalized.request_id ?? '' } } finally { if (current === request) loading.value = false } }
function backToReports(): void { void router.push({ name: 'maintenanceReports' }) }
let unregisterReader: (() => void) | undefined
watch(routeId, (reportId) => { unregisterReader?.(); regenerateOpen.value = false; if (reportId !== null) unregisterReader = registerReportReader(reportId, refreshOwnedReport.value); void load() }, { immediate: true })
onBeforeUnmount(() => { disposed = true; request += 1; unregisterReader?.() })
</script>

<style scoped>
.report-detail { display: grid; gap: 18px; max-width: 1200px; margin: 0 auto; padding: 32px; }.report-detail > header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }.report-detail h1 { margin: 0; }.report-detail__summary { display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 16px 20px; border: 1px solid var(--td-component-stroke); border-radius: 10px; background: var(--td-bg-color-container); }.report-detail__summary p { margin: 0; }@media (max-width: 760px) { .report-detail { padding: 20px 16px; }.report-detail > header { align-items: flex-start; flex-direction: column; } }
</style>
