<template>
  <div v-if="open && canImport" class="master-data-import-dialog" role="presentation" @click.self="close">
    <section class="master-data-import-dialog__panel" role="dialog" aria-modal="true" aria-labelledby="master-data-import-title">
      <header><div><span>{{ resourceKey }}</span><h2 id="master-data-import-title">Import Excel data</h2></div><button type="button" aria-label="Close" @click="close">×</button></header>
      <main>
        <MaintenanceErrorState v-if="snapshot.error" :error="snapshot.error" title="Import request needs attention" @retry="retryError" />
        <section v-if="snapshot.phase === 'idle' || snapshot.phase === 'selected'" class="master-data-import-dialog__upload">
          <p>Download the current template, then select the completed workbook.</p>
          <t-button variant="outline" @click="downloadTemplate">Download template</t-button>
          <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="selectFile">
          <strong v-if="snapshot.fileName">{{ snapshot.fileName }}</strong>
          <t-button theme="primary" :disabled="!snapshot.fileName" @click="run(workflow.upload)">Upload and inspect</t-button>
        </section>
        <ImportMappingStep v-else-if="snapshot.phase === 'uploaded' && uploadTask" :sheets="uploadTask.sheets" :mapping="snapshot.mapping" @mapping-change="workflow.setMapping" />
        <ImportPreviewStep v-if="previewTask && ['previewed', 'confirmed'].includes(snapshot.phase)" :task="previewTask" />
        <section v-if="snapshot.phase === 'uploaded' || snapshot.phase === 'previewed' || snapshot.phase === 'confirmed'" class="master-data-import-dialog__actions">
          <t-button v-if="snapshot.phase === 'uploaded'" theme="primary" @click="run(workflow.preview)">Validate preview</t-button>
          <template v-else><label><input type="checkbox" :checked="snapshot.confirmed" :disabled="snapshot.phase === 'confirmed'" @change="workflow.confirm"> I have reviewed the preview and want to execute this import.</label><t-button theme="primary" :disabled="snapshot.phase !== 'confirmed'" @click="run(workflow.execute)">Execute import</t-button></template>
          <t-button v-if="previewTask?.errors.length" variant="outline" @click="downloadErrors">Download error workbook</t-button>
          <t-button variant="outline" @click="startOver">Choose another file</t-button>
        </section>
        <ImportTaskResult v-if="resultTask && resultPhase" :phase="resultPhase" :task="resultTask" @completed="completed" @retry-status="run(workflow.retryStatus)" @start-over="startOver" />
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import type { ImportTaskUploadResult, ImportTaskView } from '@/api/maintenance/imports'
import ImportMappingStep from './ImportMappingStep.vue'
import ImportPreviewStep from './ImportPreviewStep.vue'
import ImportTaskResult from './ImportTaskResult.vue'
import { createImportWorkflow } from './import-workflow'
import type { ImportPhase, ImportWorkflowState } from './import-state'

const props = defineProps<{ open: boolean; resourceKey: string; canImport: boolean }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'completed'): void }>()
const workflow = createImportWorkflow({ resourceKey: props.resourceKey })
const snapshot = ref<ImportWorkflowState>(workflow.state)
const objectUrls = new Set<string>()
const unsubscribe = workflow.subscribe((next) => { snapshot.value = next })

const uploadTask = computed<ImportTaskUploadResult | null>(() => snapshot.value.task && !('can_execute' in snapshot.value.task) ? snapshot.value.task : null)
const previewTask = computed<ImportTaskView | null>(() => snapshot.value.task && 'can_execute' in snapshot.value.task ? snapshot.value.task : null)
const resultTask = computed(() => previewTask.value)
const resultPhase = computed<Extract<ImportPhase, 'queued' | 'running' | 'completed' | 'failed' | 'expired'> | null>(() => {
  const phase = snapshot.value.phase
  return ['queued', 'running', 'completed', 'failed', 'expired'].includes(phase)
    ? phase as Extract<ImportPhase, 'queued' | 'running' | 'completed' | 'failed' | 'expired'>
    : null
})

function run(command: () => Promise<void>): void { void command() }
function selectFile(event: Event): void { const file = (event.target as HTMLInputElement).files?.[0]; if (file) workflow.selectFile(file) }
function startOver(): void { workflow.reset(props.resourceKey) }
function close(): void { workflow.setActive(false); emit('close') }
function completed(): void { workflow.setActive(false); emit('completed'); emit('close') }
function retryError(): void { if (snapshot.value.task) run(workflow.retryStatus); else run(workflow.upload) }
function downloadBlob(blob: Blob, filename: string): void { const url = URL.createObjectURL(blob); objectUrls.add(url); const link = document.createElement('a'); link.href = url; link.download = filename; link.click(); window.setTimeout(() => { URL.revokeObjectURL(url); objectUrls.delete(url) }, 0) }
async function downloadTemplate(): Promise<void> { downloadBlob(await (await import('@/api/maintenance/imports')).masterDataTransferApi.downloadTemplate(), 'master-data-import-template.xlsx') }
async function downloadErrors(): Promise<void> { if (snapshot.value.task) downloadBlob(await (await import('@/api/maintenance/imports')).masterDataTransferApi.downloadErrors(snapshot.value.task.task_id), `import-errors-${snapshot.value.task.task_id}.xlsx`) }
function visibilityChanged(): void { workflow.setVisible(document.visibilityState === 'visible') }

watch(() => props.resourceKey, (resourceKey) => workflow.reset(resourceKey), { immediate: true })
watch(() => [props.open, props.canImport], ([open, canImport]) => workflow.setActive(Boolean(open && canImport)), { immediate: true })
onMounted(() => { document.addEventListener('visibilitychange', visibilityChanged); visibilityChanged() })
onBeforeUnmount(() => { document.removeEventListener('visibilitychange', visibilityChanged); objectUrls.forEach((url) => URL.revokeObjectURL(url)); objectUrls.clear(); unsubscribe(); workflow.dispose() })
</script>

<style scoped>
.master-data-import-dialog { position: fixed; z-index: 1600; inset: 0; display: grid; place-items: center; padding: 20px; background: rgb(0 0 0 / 38%); }.master-data-import-dialog__panel { width: min(860px, 100%); max-height: min(760px, 100%); overflow: auto; border-radius: 10px; background: var(--td-bg-color-container); box-shadow: var(--td-shadow-3); }.master-data-import-dialog header { display: flex; justify-content: space-between; gap: 16px; padding: 22px 26px; border-bottom: 1px solid var(--td-component-stroke); }.master-data-import-dialog header span { color: var(--td-brand-color); font-size: 12px; font-weight: 600; }.master-data-import-dialog h2 { margin: 5px 0 0; }.master-data-import-dialog header button { width: 34px; height: 34px; border: 0; border-radius: 50%; background: var(--td-bg-color-secondarycontainer); font-size: 24px; cursor: pointer; }.master-data-import-dialog main { display: grid; gap: 20px; padding: 24px 26px; }.master-data-import-dialog__upload { display: grid; gap: 14px; }.master-data-import-dialog__upload p { margin: 0; color: var(--td-text-color-secondary); }.master-data-import-dialog__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }.master-data-import-dialog__actions label { width: 100%; color: var(--td-text-color-secondary); }
</style>
