<template>
  <main class="report-center">
    <header class="report-center__header"><div><h1>{{ t('maintenance.pages.reports') }}</h1><p>{{ t('maintenance.reports.description') }}</p></div><button type="button" class="report-center__primary" disabled :title="t('maintenance.reports.createComingSoon')">{{ t('maintenance.reports.actions.create') }}</button></header>
    <ReportFilterBar :query="query" @apply="applyFilters" />
    <p v-if="error" class="report-center__error" role="alert">{{ error }} <button type="button" @click="load">{{ t('maintenance.reports.actions.retry') }}</button></p>
    <div v-if="loading && reports.length === 0" class="report-center__state">{{ t('maintenance.reports.loading') }}</div>
    <div v-else-if="reports.length === 0" class="report-center__state">{{ t('maintenance.reports.empty') }}</div>
    <ReportListTable v-else :reports="reports" :role="reportRole" @open="openReport" @generate="emitAction" @validate="emitAction" @finalize="emitAction" @regenerate="emitAction" @export="emitAction" />
    <footer v-if="pages > 1" class="report-center__pagination"><button type="button" :disabled="loading || query.page <= 1" @click="setPage(query.page - 1)">{{ t('maintenance.reports.actions.previous') }}</button><span>{{ query.page }} / {{ pages }}</span><button type="button" :disabled="loading || query.page >= pages" @click="setPage(query.page + 1)">{{ t('maintenance.reports.actions.next') }}</button></footer>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { reportApi, type ReportListItem } from '@/api/maintenance/reports'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import ReportFilterBar from '@/components/maintenance/report/ReportFilterBar.vue'
import ReportListTable from '@/components/maintenance/report/ReportListTable.vue'
import type { ReportRole } from '@/components/maintenance/report/report-actions'
import { useAuthStore } from '@/stores/auth'
import { normalizeReportListQuery, type ReportListQuery } from '@/components/maintenance/report/report-types'

const { t } = useI18n(); const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const reports = ref<ReportListItem[]>([]); const pages = ref(0); const loading = ref(false); const error = ref('')
const query = computed(() => normalizeReportListQuery(route.query) as ReportListQuery)
const reportRole = computed<ReportRole>(() => authStore.hasRole('admin') ? 'ADMIN' : authStore.hasRole('contributor') ? 'CONTRIBUTOR' : 'VIEWER')
let request = 0
function routeQuery(value: ReportListQuery): Record<string, string> { return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, String(item)])) }
async function load(): Promise<void> { const current = ++request; loading.value = true; error.value = ''; reports.value = []; pages.value = 0; try { const result = await reportApi.listReports(query.value); if (current !== request) return; reports.value = result.data.items; pages.value = result.data.pages } catch (value) { if (current === request) error.value = normalizeMaintenanceError(value).message } finally { if (current === request) loading.value = false } }
function applyFilters(value: ReportListQuery): void { void router.push({ path: '/platform/maintenance/reports', query: routeQuery(value) }) }
function setPage(page: number): void { applyFilters({ ...query.value, page }) }
function openReport(reportId: number): void { void router.push({ name: 'maintenanceReportDetail', params: { reportId } }) }
function emitAction(_reportId: number): void { /* Task 4/5 supplies lifecycle and export handling. */ }
watch(query, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { request += 1 })
</script>

<style scoped>
.report-center { display: grid; gap: 18px; max-width: 1440px; margin: 0 auto; padding: 32px; }.report-center__header { display: flex; justify-content: space-between; gap: 16px; }.report-center h1, .report-center p { margin: 0; }.report-center__header p, .report-center__state { color: var(--td-text-color-secondary); }.report-center__primary, .report-center__pagination button { min-height: 34px; padding: 0 12px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); font: inherit; }.report-center__primary { background: var(--td-brand-color); color: var(--td-text-color-anti); }.report-center__error { padding: 12px; border: 1px solid var(--td-error-color); border-radius: 6px; color: var(--td-error-color); }.report-center__error button { margin-left: 8px; }.report-center__state { padding: 48px; text-align: center; }.report-center__pagination { display: flex; justify-content: center; gap: 12px; align-items: center; }@media (max-width: 760px) { .report-center { padding: 20px 16px; }.report-center__header { display: grid; } }
</style>
