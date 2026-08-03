<template>
  <div v-if="open && canImport" class="master-data-import-dialog" role="presentation" @click.self="close">
    <section class="master-data-import-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="master-data-import-title">
      <header><div><span>{{ resourceKey }}</span><h2 id="master-data-import-title">Import Excel data</h2></div><button type="button" aria-label="Close" @click="close">×</button></header>
      <main>
        <MaintenanceErrorState v-if="displayError" :error="displayError" title="Import request needs attention" />
        <t-button v-if="snapshot.error?.retryable" variant="outline" :disabled="busy" @click="retryError">Retry request</t-button>
        <section v-if="snapshot.phase === 'idle' || snapshot.phase === 'selected'" class="master-data-import-dialog__upload">
          <p>Download the current template, then select the completed workbook.</p>
          <t-button variant="outline" :disabled="busy" @click="downloadTemplate">Download template</t-button>
          <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" :disabled="busy" @change="selectFile">
          <strong v-if="snapshot.fileName">{{ snapshot.fileName }}</strong>
          <t-button theme="primary" :disabled="busy || !snapshot.fileName" @click="run(workflow.upload)">Upload and inspect</t-button>
        </section>
        <ImportMappingStep v-else-if="snapshot.phase === 'uploaded' && uploadTask" :sheets="uploadTask.sheets" :mapping="snapshot.mapping" :disabled="busy" @mapping-change="workflow.setMapping" />
        <ImportPreviewStep v-if="previewTask && ['previewed', 'confirmed'].includes(snapshot.phase)" :task="previewTask" />
        <section v-if="snapshot.phase === 'uploaded' || snapshot.phase === 'previewed' || snapshot.phase === 'confirmed'" class="master-data-import-dialog__actions">
          <t-button v-if="snapshot.phase === 'uploaded'" theme="primary" :disabled="busy" @click="run(workflow.preview)">Validate preview</t-button>
          <template v-else><label><input type="checkbox" :checked="snapshot.confirmed" :disabled="busy || (!canConfirm && !snapshot.confirmed)" @change="workflow.confirm"> I have reviewed the preview and want to execute this import.</label><t-button theme="primary" :disabled="busy || !canExecute" @click="run(workflow.execute)">Execute import</t-button></template>
          <t-button v-if="previewTask?.errors.length" variant="outline" :disabled="busy" @click="downloadErrors">Download error workbook</t-button>
          <t-button variant="outline" @click="startOver">Choose another file</t-button>
        </section>
        <ImportTaskResult v-if="resultTask && resultPhase" :phase="resultPhase" :task="resultTask" :busy="busy" @completed="completed" @retry-status="run(workflow.retryStatus)" @start-over="startOver" />
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import {
  masterDataTransferApi,
  type ImportTaskUploadResult,
  type ImportTaskView,
} from '@/api/maintenance/imports'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import ImportMappingStep from './ImportMappingStep.vue'
import ImportPreviewStep from './ImportPreviewStep.vue'
import ImportTaskResult from './ImportTaskResult.vue'
import {
  createImportDialogLifecycle,
  createImportWorkflow,
  normalizeImportWorkflowError,
} from './import-workflow'
import {
  canConfirmImport,
  canExecuteImport,
  type ImportPhase,
  type ImportWorkflowState,
} from './import-state'

const props = defineProps<{ open: boolean; resourceKey: string; canImport: boolean }>()
const emit = defineEmits<{
  (event: 'close'): void
  (event: 'completed'): void
  (event: 'error', error: MaintenanceClientError): void
}>()
const workflow = createImportWorkflow({ resourceKey: props.resourceKey })
const snapshot = ref<ImportWorkflowState>(workflow.state)
const workflowBusy = ref(workflow.busy)
const commandBusy = ref(false)
const busy = computed(() => commandBusy.value || workflowBusy.value)
const lifecycle = createImportDialogLifecycle({
  workflow,
  api: masterDataTransferApi,
  objectUrls: URL,
  triggerDownload: (url, filename) => {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
  },
  onError: (error) => emit('error', error),
  onClose: () => emit('close'),
  onCompleted: () => emit('completed'),
})
const unsubscribe = workflow.subscribe((next, isBusy) => {
  snapshot.value = next
  workflowBusy.value = isBusy
  lifecycle.reportWorkflowError(next.error)
})

const uploadTask = computed<ImportTaskUploadResult | null>(() => snapshot.value.task && !('can_execute' in snapshot.value.task) ? snapshot.value.task : null)
const previewTask = computed<ImportTaskView | null>(() => snapshot.value.task && 'can_execute' in snapshot.value.task ? snapshot.value.task : null)
const resultTask = computed(() => previewTask.value)
const canConfirm = computed(() => canConfirmImport(snapshot.value))
const canExecute = computed(() => canExecuteImport(snapshot.value))
const displayError = computed(() => snapshot.value.error === null
  ? null
  : { ...snapshot.value.error, retryable: false })
const resultPhase = computed<Extract<ImportPhase, 'queued' | 'running' | 'completed' | 'failed' | 'expired'> | null>(() => {
  const phase = snapshot.value.phase
  return ['queued', 'running', 'completed', 'failed', 'expired'].includes(phase)
    ? phase as Extract<ImportPhase, 'queued' | 'running' | 'completed' | 'failed' | 'expired'>
    : null
})

async function run(command: () => Promise<void>): Promise<void> {
  if (busy.value) return
  commandBusy.value = true
  try {
    await command()
  } catch (error) {
    emit('error', normalizeImportWorkflowError(error))
  } finally {
    commandBusy.value = false
  }
}
function selectFile(event: Event): void { const file = (event.target as HTMLInputElement).files?.[0]; if (file) workflow.selectFile(file) }
function startOver(): void { workflow.reset(props.resourceKey) }
function close(): void { lifecycle.close() }
function completed(): void { lifecycle.completed() }
function retryError(): void { void run(snapshot.value.task ? workflow.retryStatus : workflow.upload) }
function downloadTemplate(): void { void run(lifecycle.downloadTemplate) }
function downloadErrors(): void {
  const taskId = snapshot.value.task?.task_id
  if (taskId) void run(() => lifecycle.downloadErrors(taskId))
}
function visibilityChanged(): void { lifecycle.setVisible(document.visibilityState === 'visible') }

watch(() => props.resourceKey, (resourceKey) => workflow.reset(resourceKey), { immediate: true })
watch(() => [props.open, props.canImport], ([open, canImport]) => {
  if (open && canImport) workflow.setActive(true)
  else lifecycle.deactivate()
}, { immediate: true })
onMounted(() => { document.addEventListener('visibilitychange', visibilityChanged); visibilityChanged() })
onBeforeUnmount(() => { document.removeEventListener('visibilitychange', visibilityChanged); unsubscribe(); lifecycle.dispose() })
</script>

<style scoped>
.master-data-import-dialog { position: fixed; z-index: 1600; inset: 0; display: grid; place-items: center; padding: 20px; background: rgb(0 0 0 / 38%); }.master-data-import-dialog__panel { width: min(860px, 100%); max-height: min(760px, 100%); overflow: auto; border-radius: 10px; background: var(--td-bg-color-container); box-shadow: var(--td-shadow-3); }.master-data-import-dialog header { display: flex; justify-content: space-between; gap: 16px; padding: 22px 26px; border-bottom: 1px solid var(--td-component-stroke); }.master-data-import-dialog header span { color: var(--td-brand-color); font-size: 12px; font-weight: 600; }.master-data-import-dialog h2 { margin: 5px 0 0; }.master-data-import-dialog header button { width: 34px; height: 34px; border: 0; border-radius: 50%; background: var(--td-bg-color-secondarycontainer); font-size: 24px; cursor: pointer; }.master-data-import-dialog main { display: grid; gap: 20px; padding: 24px 26px; }.master-data-import-dialog__upload { display: grid; gap: 14px; }.master-data-import-dialog__upload p { margin: 0; color: var(--td-text-color-secondary); }.master-data-import-dialog__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }.master-data-import-dialog__actions label { width: 100%; color: var(--td-text-color-secondary); }
</style>
