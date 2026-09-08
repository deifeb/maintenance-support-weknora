<template>
  <section class="import-mapping-step">
    <h3>Map workbook columns</h3>
    <p>Review the suggested mappings before validating the import.</p>
    <div v-for="sheet in sheets" :key="sheet.name" class="import-mapping-step__sheet">
      <h4>{{ sheet.name }}</h4>
      <label v-for="source in sheet.source_headers" :key="source" class="import-mapping-step__row">
        <span>{{ source }}</span>
        <input
          :value="mapping[sheet.name]?.[source] ?? sheet.suggested_mapping[source] ?? ''"
          :disabled="disabled"
          :placeholder="sheet.required_fields.includes(source) ? 'Required target field' : 'Ignore column'"
          @input="emitMapping(sheet.name, source, $event)"
        >
      </label>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { ImportMapping, ImportSheetInspection } from '@/api/maintenance/imports'

defineProps<{ sheets: ImportSheetInspection[]; mapping: ImportMapping; disabled?: boolean }>()
const emit = defineEmits<{ (event: 'mapping-change', sheet: string, source: string, target: string): void }>()

function emitMapping(sheet: string, source: string, event: Event): void {
  emit('mapping-change', sheet, source, (event.target as HTMLInputElement).value)
}
</script>

<style scoped>
.import-mapping-step { display: grid; gap: 16px; }
.import-mapping-step h3, .import-mapping-step h4, .import-mapping-step p { margin: 0; }
.import-mapping-step p { color: var(--td-text-color-secondary); }
.import-mapping-step__sheet { display: grid; gap: 8px; padding: 16px; border: 1px solid var(--td-component-stroke); border-radius: 8px; }
.import-mapping-step__row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: 12px; align-items: center; }
.import-mapping-step input { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--td-component-stroke); border-radius: 6px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); }
</style>
