<template>
  <section class="import-preview-step">
    <h3>Preview validation</h3>
    <div class="import-preview-step__summaries">
      <article v-for="sheet in task.sheets" :key="sheet.name">
        <strong>{{ sheet.name }}</strong>
        <span>Total: {{ sheet.total_rows }}</span>
        <span>Valid: {{ sheet.valid_rows }}</span>
        <span>Invalid: {{ sheet.invalid_rows }}</span>
      </article>
    </div>
    <template v-for="group in issueGroups" :key="group.name">
      <h4>{{ group.name }}</h4>
      <p v-if="group.items.length === 0">None</p>
      <table v-else>
        <thead><tr><th>Sheet</th><th>Row</th><th>Field</th><th>Code</th><th>Message</th></tr></thead>
        <tbody><tr v-for="issue in group.items" :key="`${issue.sheet}-${issue.row}-${issue.field}-${issue.code}`"><td>{{ issue.sheet ?? '-' }}</td><td>{{ issue.row ?? '-' }}</td><td>{{ issue.field ?? '-' }}</td><td>{{ issue.code }}</td><td>{{ issue.message }}</td></tr></tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ImportIssue, ImportTaskView } from '@/api/maintenance/imports'

const props = defineProps<{ task: ImportTaskView }>()
const issueGroups = computed<Array<{ name: string; items: ImportIssue[] }>>(() => [
  { name: 'Errors', items: props.task.errors },
  { name: 'Warnings', items: props.task.warnings },
])
</script>

<style scoped>
.import-preview-step { display: grid; gap: 14px; }.import-preview-step h3,.import-preview-step h4,.import-preview-step p { margin: 0; }.import-preview-step__summaries { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }.import-preview-step article { display: grid; gap: 4px; padding: 12px; border-radius: 8px; background: var(--td-bg-color-secondarycontainer); }.import-preview-step table { width: 100%; border-collapse: collapse; font-size: 13px; }.import-preview-step th,.import-preview-step td { padding: 8px; border: 1px solid var(--td-component-stroke); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
</style>
