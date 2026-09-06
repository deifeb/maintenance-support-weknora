<template>
  <form class="report-filter-bar" @submit.prevent="apply">
    <label>
      <span>{{ t('maintenance.reports.filters.keyword') }}</span>
      <input v-model="keyword" :placeholder="t('maintenance.reports.filters.keywordPlaceholder')">
    </label>
    <label>
      <span>{{ t('maintenance.reports.filters.reportType') }}</span>
      <input v-model="reportType" :placeholder="t('maintenance.reports.filters.all')">
    </label>
    <label>
      <span>{{ t('maintenance.reports.filters.jobStatus') }}</span>
      <input v-model="jobStatus" :placeholder="t('maintenance.reports.filters.all')">
    </label>
    <label>
      <span>{{ t('maintenance.reports.filters.versionStatus') }}</span>
      <input v-model="versionStatus" :placeholder="t('maintenance.reports.filters.all')">
    </label>
    <label>
      <span>{{ t('maintenance.reports.filters.sourceType') }}</span>
      <input v-model="sourceType" :placeholder="t('maintenance.reports.filters.all')">
    </label>
    <div class="report-filter-bar__actions">
      <button type="submit">{{ t('maintenance.reports.actions.apply') }}</button>
      <button type="button" @click="clear">{{ t('maintenance.reports.actions.clear') }}</button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ReportListQuery } from './report-types'

const DEFAULT_QUERY: ReportListQuery = {
  page: 1,
  page_size: 20,
  sort_by: 'created_at',
  sort_order: 'desc',
}

const props = defineProps<{ query: ReportListQuery }>()
const emit = defineEmits<{ (event: 'apply', query: ReportListQuery): void }>()
const { t } = useI18n()

const keyword = ref('')
const reportType = ref('')
const jobStatus = ref('')
const versionStatus = ref('')
const sourceType = ref('')

function sync(query: ReportListQuery): void {
  keyword.value = query.keyword ?? ''
  reportType.value = query.report_type ?? ''
  jobStatus.value = query.job_status ?? ''
  versionStatus.value = query.version_status ?? ''
  sourceType.value = query.source_type ?? ''
}

function text(value: string): string | undefined {
  const trimmed = value.trim()
  return trimmed || undefined
}

function apply(): void {
  emit('apply', {
    ...DEFAULT_QUERY,
    ...(text(keyword.value) ? { keyword: text(keyword.value) } : {}),
    ...(text(reportType.value) ? { report_type: text(reportType.value) } : {}),
    ...(text(jobStatus.value) ? { job_status: text(jobStatus.value) as ReportListQuery['job_status'] } : {}),
    ...(text(versionStatus.value) ? { version_status: text(versionStatus.value) as ReportListQuery['version_status'] } : {}),
    ...(text(sourceType.value) ? { source_type: text(sourceType.value) } : {}),
  })
}

function clear(): void {
  sync(DEFAULT_QUERY)
  emit('apply', { ...DEFAULT_QUERY })
}

watch(() => props.query, sync, { immediate: true, deep: true })
</script>

<style scoped>
.report-filter-bar { display: flex; flex-wrap: wrap; gap: 12px; padding: 16px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.report-filter-bar label { display: grid; gap: 5px; min-width: 150px; color: var(--td-text-color-secondary); font-size: 11px; }
.report-filter-bar input, .report-filter-bar button { min-height: 34px; padding: 0 10px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); font: inherit; }
.report-filter-bar button { cursor: pointer; }
.report-filter-bar__actions { display: flex; align-items: end; gap: 8px; }
</style>
