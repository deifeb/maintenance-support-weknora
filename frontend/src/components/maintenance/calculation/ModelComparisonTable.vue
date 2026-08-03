<template>
  <div class="comparison-table">
    <table>
      <thead>
        <tr>
          <th>{{ t('maintenance.calculation.comparison.part') }}</th>
          <th
            v-for="candidateKey in comparison.candidate_keys"
            :key="candidateKey"
          >
            <code>{{ candidateKey }}</code>
          </th>
          <th>{{ t('maintenance.calculation.list.actions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in comparison.rows" :key="row.spare_part_id">
          <th scope="row">
            <code>{{ row.spare_part_code }}</code>
            <strong>{{ row.spare_part_name }}</strong>
            <small>{{ row.criticality_level || '—' }}</small>
          </th>
          <td
            v-for="candidateKey in comparison.candidate_keys"
            :key="candidateKey"
          >
            <template v-if="row.candidates[candidateKey]">
              <span
                v-if="row.candidates[candidateKey].child_id === row.system_child_id"
                class="comparison-table__system"
              >
                {{ t('maintenance.calculation.comparison.system') }}
              </span>
              <strong
                :class="{
                  'comparison-table__missing': (
                    !presentation(row.candidates[candidateKey]).selectable
                  ),
                }"
              >
                {{
                  presentation(row.candidates[candidateKey]).selectable
                    ? presentation(row.candidates[candidateKey]).label
                    : t('maintenance.calculation.comparison.noResult')
                }}
              </strong>
              <small v-if="row.candidates[candidateKey].p50">
                P50 {{ row.candidates[candidateKey].p50 }}
                · P99 {{ row.candidates[candidateKey].p99 }}
              </small>
              <small v-if="presentation(row.candidates[candidateKey]).warningCount">
                {{ presentation(row.candidates[candidateKey]).warningCount }}
                {{ t('maintenance.calculation.fields.warnings') }}
              </small>
            </template>
          </td>
          <td>
            <div v-if="row.decision" class="comparison-table__decision">
              <span>{{ t('maintenance.calculation.comparison.selected') }}</span>
              <strong>{{ row.decision.final_quantity }}</strong>
              <small>{{ row.decision.risk }} · v{{ row.decision.version }}</small>
            </div>
            <button
              type="button"
              :disabled="!editable"
              @click="$emit('edit', row)"
            >
              {{ t('maintenance.calculation.comparison.edit') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  CalculationComparisonRow,
  CalculationGroupComparison,
  ComparisonCandidateCell,
} from '@/api/maintenance/calculation-groups'
import {
  presentCandidateCell,
} from './comparison-decisions'

withDefaults(
  defineProps<{
    comparison: CalculationGroupComparison
    editable?: boolean
  }>(),
  {
    editable: false,
  },
)

defineEmits<{
  (event: 'edit', row: CalculationComparisonRow): void
}>()

const { t } = useI18n()

function presentation(cell: ComparisonCandidateCell) {
  return presentCandidateCell(cell)
}
</script>

<style scoped>
.comparison-table {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.comparison-table table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
}

.comparison-table th,
.comparison-table td {
  min-width: 180px;
  padding: 13px 14px;
  border-right: 1px solid var(--td-component-stroke);
  border-bottom: 1px solid var(--td-component-stroke);
  color: var(--td-text-color-secondary);
  font-size: 11px;
  text-align: left;
  vertical-align: top;
}

.comparison-table thead th {
  background: var(--td-bg-color-secondarycontainer);
  font-size: 10px;
}

.comparison-table tbody th {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--td-bg-color-container);
}

.comparison-table code,
.comparison-table strong,
.comparison-table small {
  display: block;
}

.comparison-table code {
  color: var(--td-text-color-primary);
  font-size: 10px;
}

.comparison-table strong {
  margin-top: 5px;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 13px;
}

.comparison-table small {
  margin-top: 4px;
  color: var(--td-text-color-placeholder);
}

.comparison-table__system {
  display: inline-block;
  padding: 2px 5px;
  border-radius: 3px;
  background: var(--td-brand-color-light);
  color: var(--td-brand-color);
  font-size: 9px;
}

.comparison-table__missing {
  color: var(--td-text-color-placeholder) !important;
}

.comparison-table__decision {
  margin-bottom: 8px;
}

.comparison-table__decision > span {
  color: var(--td-text-color-placeholder);
  font-size: 9px;
  text-transform: uppercase;
}

.comparison-table button {
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 4px;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.comparison-table button:disabled {
  cursor: not-allowed;
  opacity: .45;
}
</style>
