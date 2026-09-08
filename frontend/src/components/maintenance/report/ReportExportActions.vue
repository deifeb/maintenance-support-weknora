<template>
  <div v-if="actions.includes('export')" class="report-export-actions">
    <button v-for="format in formats" :key="format" type="button" :disabled="downloading" @click="download(format)">{{ t('maintenance.reports.actions.export') }} {{ format }}</button>
    <p v-if="errorKey" role="alert">{{ t(errorKey) }}<template v-if="requestId"> {{ t('maintenance.reports.errors.requestId', { requestId }) }}</template></p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { reportApi } from '@/api/maintenance/reports'
import { createReportExportController } from './report-actions'
import type { ReportAction, ReportExportFormat } from './report-types'

const props = defineProps<{ reportId: number; actions: ReportAction[] }>()
const emit = defineEmits<{ (event: 'exported', format: ReportExportFormat): void }>()
const { t } = useI18n()
const formats: readonly ReportExportFormat[] = ['MARKDOWN', 'JSON', 'DOCX']
const downloading = ref(false)
const errorKey = ref('')
const requestId = ref('')
const controller = computed(() => createReportExportController({
  reportId: props.reportId,
  actions: props.actions,
  exportReport: reportApi.exportReport,
  createObjectURL: URL.createObjectURL.bind(URL),
  revokeObjectURL: URL.revokeObjectURL.bind(URL),
  createAnchor: () => {
    const anchor = document.createElement('a')
    anchor.style.display = 'none'
    document.body.append(anchor)
    return anchor
  },
}))

async function download(format: ReportExportFormat): Promise<void> {
  if (downloading.value) return
  downloading.value = true
  errorKey.value = ''
  requestId.value = ''
  try {
    await controller.value.download(format)
    emit('exported', format)
  } catch (reason) {
    const error = normalizeMaintenanceError(reason)
    errorKey.value = controller.value.messageFor(error)
    requestId.value = controller.value.requestIdFor(error) ?? ''
  } finally {
    downloading.value = false
  }
}
</script>

<style scoped>
.report-export-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }.report-export-actions button { min-height: 34px; padding: 0 12px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-brand-color); font: inherit; cursor: pointer; }.report-export-actions [role="alert"] { width: 100%; margin: 0; color: var(--td-error-color); }
</style>
