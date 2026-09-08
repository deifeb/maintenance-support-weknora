<template>
  <div class="selection-table">
    <table>
      <thead>
        <tr>
          <th>{{ t('maintenance.calculation.fields.select') }}</th>
          <th>{{ t('maintenance.calculation.fields.candidate') }}</th>
          <th>{{ t('maintenance.calculation.fields.model') }}</th>
          <th>{{ t('maintenance.calculation.fields.mode') }}</th>
          <th>{{ t('maintenance.calculation.fields.score') }}</th>
          <th>{{ t('maintenance.calculation.fields.risk') }}</th>
          <th>{{ t('maintenance.calculation.fields.basis') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.candidateKey"
          :class="{ 'selection-table__row--disabled': row.disabled }"
        >
          <td>
            <input
              type="checkbox"
              :checked="modelValue.includes(row.candidateKey)"
              :disabled="row.disabled || row.primary"
              :aria-label="row.candidateKey"
              @change="toggle(row.candidateKey, ($event.target as HTMLInputElement).checked)"
            >
          </td>
          <td>
            <code>{{ row.candidateKey }}</code>
            <span v-if="row.primary" class="selection-table__primary">
              {{ t('maintenance.calculation.recommendation.primary') }}
            </span>
          </td>
          <td>{{ row.reliabilityModel }}</td>
          <td>{{ row.executionMode }}</td>
          <td class="selection-table__numeric">{{ row.score }}</td>
          <td>
            <span :data-risk="row.risk">{{ row.risk }}</span>
          </td>
          <td>
            <ul v-if="row.reasons.length">
              <li v-for="reason in row.reasons" :key="reason">
                {{ reason }}
              </li>
            </ul>
            <div
              v-if="row.missingRequirements.length"
              class="selection-table__missing"
            >
              {{
                t('maintenance.calculation.selection.missing')
              }}:
              {{ row.missingRequirements.join(', ') }}
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  CandidateSelectionRow,
} from './model-selection'

const props = defineProps<{
  rows: CandidateSelectionRow[]
  modelValue: string[]
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: string[]): void
}>()

const { t } = useI18n()

function toggle(candidateKey: string, checked: boolean): void {
  const next = checked
    ? [...new Set([...props.modelValue, candidateKey])]
    : props.modelValue.filter((key) => key !== candidateKey)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.selection-table {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.selection-table table {
  width: 100%;
  min-width: 920px;
  border-collapse: collapse;
}

.selection-table th,
.selection-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--td-component-stroke);
  color: var(--td-text-color-secondary);
  font-size: 12px;
  text-align: left;
  vertical-align: top;
}

.selection-table th {
  background: var(--td-bg-color-secondarycontainer);
  font-size: 10px;
  letter-spacing: .07em;
  text-transform: uppercase;
}

.selection-table code {
  color: var(--td-text-color-primary);
  font-size: 11px;
}

.selection-table__primary {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 5px;
  border-radius: 3px;
  background: var(--td-brand-color-light);
  color: var(--td-brand-color);
  font-size: 9px;
}

.selection-table ul {
  margin: 0;
  padding-left: 15px;
}

.selection-table__missing {
  margin-top: 6px;
  color: var(--td-error-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
}

.selection-table__numeric {
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-weight: 700;
}

.selection-table__row--disabled {
  background: var(--td-bg-color-secondarycontainer);
  opacity: .72;
}

[data-risk="LOW"] { color: var(--td-success-color); }
[data-risk="MEDIUM"] { color: var(--td-warning-color); }
[data-risk="HIGH"] { color: var(--td-error-color); }
</style>
