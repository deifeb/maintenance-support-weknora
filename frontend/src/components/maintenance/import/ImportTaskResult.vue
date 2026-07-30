<template>
  <section class="import-task-result" :class="`import-task-result--${phase}`">
    <template v-if="phase === 'queued' || phase === 'running'"><h3>{{ phase === 'queued' ? 'Import queued' : 'Import running' }}</h3><p>The import is processing. This dialog refreshes its status automatically.</p></template>
    <template v-else-if="phase === 'completed'"><h3>Import completed</h3><p v-if="task.result">{{ task.result.total_rows }} rows processed.</p><dl v-if="task.result"><template v-for="(count, key) in task.result.created" :key="`created-${key}`"><dt>Created {{ key }}</dt><dd>{{ count }}</dd></template><template v-for="(count, key) in task.result.updated" :key="`updated-${key}`"><dt>Updated {{ key }}</dt><dd>{{ count }}</dd></template></dl><t-button theme="primary" @click="$emit('completed')">Done</t-button></template>
    <template v-else-if="phase === 'expired'"><h3>Import task expired</h3><p>Start a new upload; expired tasks cannot be resumed.</p><t-button @click="$emit('start-over')">Upload a new file</t-button></template>
    <template v-else><h3>Import failed</h3><p>{{ task.error_message || 'The import could not be completed.' }}</p><t-button v-if="task.error_code" theme="primary" variant="outline" @click="$emit('retry-status')">Retry status</t-button><t-button variant="outline" @click="$emit('start-over')">Upload a corrected file</t-button></template>
  </section>
</template>

<script setup lang="ts">
import type { ImportPhase } from './import-state'
import type { ImportTaskView } from '@/api/maintenance/imports'

defineProps<{ phase: Extract<ImportPhase, 'queued' | 'running' | 'completed' | 'failed' | 'expired'>; task: ImportTaskView }>()
defineEmits<{ (event: 'completed'): void; (event: 'retry-status'): void; (event: 'start-over'): void }>()
</script>

<style scoped>
.import-task-result { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; }.import-task-result--completed { border-color: var(--td-success-color-5); }.import-task-result--failed,.import-task-result--expired { border-color: var(--td-error-color-5); }.import-task-result h3,.import-task-result p { margin: 0; }.import-task-result p { color: var(--td-text-color-secondary); }.import-task-result dl { display: grid; grid-template-columns: 1fr auto; gap: 6px 14px; margin: 0; }.import-task-result dd { margin: 0; font-weight: 600; }
</style>
