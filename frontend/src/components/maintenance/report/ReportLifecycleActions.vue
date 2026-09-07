<template>
  <div class="report-lifecycle-actions">
    <button v-for="action in lifecycleActions" :key="action" type="button" :disabled="submitting" @click="run(action)">{{ t(`maintenance.reports.actions.${action}`) }}</button>
    <p v-if="errorKey" role="alert">{{ t(errorKey) }}<template v-if="requestId"> {{ t('maintenance.reports.errors.requestId', { requestId }) }}</template></p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { reportApi } from '@/api/maintenance/reports'
import { createReportLifecycleController } from './report-actions'
import type { ReportAction, ReportJobStatus, ReportVersionStatus } from './report-types'

type LifecycleAction = 'generate' | 'validate' | 'finalize' | 'regenerate'
const props = defineProps<{ reportId: number; jobStatus: ReportJobStatus; versionStatus: ReportVersionStatus | null; versionGenerated: boolean; actions: ReportAction[]; refresh: () => Promise<void> }>()
const { t } = useI18n(); const submitting = ref(false); const errorKey = ref(''); const requestId = ref('')
const lifecycleActions = computed(() => props.actions.filter((action): action is LifecycleAction => ['generate', 'validate', 'finalize', 'regenerate'].includes(action)))
const controller = computed(() => createReportLifecycleController({
  reportId: props.reportId, actions: props.actions,
  mutations: { generate: reportApi.generateReport, validate: reportApi.validateReport, finalize: reportApi.finalizeReport, regenerate: reportApi.regenerateReport },
  refresh: props.refresh,
}))
async function run(action: LifecycleAction): Promise<void> { if (submitting.value) return; submitting.value = true; errorKey.value = ''; requestId.value = ''; try { await controller.value.run(action) } catch (reason) { const error = normalizeMaintenanceError(reason); errorKey.value = controller.value.messageFor(error); requestId.value = controller.value.requestIdFor(error) ?? '' } finally { submitting.value = false } }
</script>

<style scoped>
.report-lifecycle-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }.report-lifecycle-actions button { min-height: 34px; padding: 0 12px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-brand-color); font: inherit; cursor: pointer; }.report-lifecycle-actions [role="alert"] { width: 100%; margin: 0; color: var(--td-error-color); }
</style>
