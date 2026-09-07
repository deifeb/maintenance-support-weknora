<template>
  <div v-if="open" class="report-regenerate-dialog" role="dialog" aria-modal="true" :aria-label="t('maintenance.reports.regenerate.title')">
    <p>{{ t('maintenance.reports.regenerate.explanation') }}</p>
    <p v-if="errorKey" role="alert">{{ t(errorKey) }}<template v-if="requestId"> {{ t('maintenance.reports.errors.requestId', { requestId }) }}</template></p>
    <button type="button" :disabled="submitting" @click="confirm">{{ t('maintenance.reports.actions.regenerate') }}</button><button type="button" :disabled="submitting" @click="emit('close')">{{ t('maintenance.reports.actions.cancel') }}</button>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { reportApi } from '@/api/maintenance/reports'
import { reportErrorMessageKey } from './report-actions'
const props = defineProps<{ open: boolean; reportId: number }>(); const emit = defineEmits<{ (event: 'changed'): void; (event: 'close'): void }>(); const { t } = useI18n(); const submitting = ref(false); const errorKey = ref(''); const requestId = ref('')
async function confirm(): Promise<void> { if (submitting.value) return; submitting.value = true; errorKey.value = ''; requestId.value = ''; try { await reportApi.regenerateReport(props.reportId); emit('changed'); emit('close') } catch (reason) { const error = normalizeMaintenanceError(reason); errorKey.value = reportErrorMessageKey(error.code); requestId.value = error.request_id ?? '' } finally { submitting.value = false } }
</script>
<style scoped>.report-regenerate-dialog { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }.report-regenerate-dialog p { margin: 0; }.report-regenerate-dialog [role="alert"] { color: var(--td-error-color); }</style>
