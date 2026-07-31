<template>
  <div
    v-if="open && row"
    class="decision-drawer"
    role="dialog"
    aria-modal="true"
  >
    <button
      class="decision-drawer__backdrop"
      type="button"
      :aria-label="t('maintenance.calculation.comparison.cancel')"
      @click="$emit('close')"
    />
    <aside>
      <header>
        <div>
          <span>{{ row.spare_part_code }}</span>
          <h2>{{ t('maintenance.calculation.comparison.drawerTitle') }}</h2>
          <p>{{ row.spare_part_name }}</p>
        </div>
        <button type="button" @click="$emit('close')">×</button>
      </header>

      <form @submit.prevent="submit">
        <label>
          <span>{{ t('maintenance.calculation.comparison.candidate') }}</span>
          <select v-model="selectedCandidateKey">
            <option
              v-for="cell in selectableCells"
              :key="cell.candidate_key"
              :value="cell.candidate_key"
            >
              {{ cell.candidate_key }} · {{ cell.recommended_quantity }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t('maintenance.calculation.comparison.quantity') }}</span>
          <input
            v-model="finalQuantity"
            inputmode="decimal"
            required
          >
        </label>
        <label>
          <span>{{ t('maintenance.calculation.comparison.reason') }}</span>
          <textarea v-model="reason" rows="4" />
          <small>{{ t('maintenance.calculation.comparison.reasonHint') }}</small>
        </label>

        <section v-if="row.decision" class="decision-drawer__risk">
          <span>{{ t('maintenance.calculation.comparison.risk') }}</span>
          <strong>{{ row.decision.risk }}</strong>
          <p v-if="row.decision.requires_admin_confirmation">
            {{ t('maintenance.calculation.comparison.adminRequired') }}
          </p>
          <small>
            {{ t('maintenance.calculation.comparison.version') }}
            {{ row.decision.version }}
            · {{ row.decision.risk_rule_version }}
          </small>
        </section>

        <p v-if="!validation.valid" class="decision-drawer__validation">
          {{
            validation.quantityValid
              ? t('maintenance.calculation.comparison.reasonHint')
              : t('maintenance.calculation.comparison.quantity')
          }}
        </p>
        <footer>
          <button type="button" @click="$emit('close')">
            {{ t('maintenance.calculation.comparison.cancel') }}
          </button>
          <button
            type="submit"
            class="decision-drawer__save"
            :disabled="saving || !validation.valid"
          >
            {{
              saving
                ? t('maintenance.calculation.comparison.saving')
                : t('maintenance.calculation.comparison.save')
            }}
          </button>
        </footer>
      </form>
    </aside>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  ref,
  watch,
} from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  CalculationComparisonRow,
  CalculationDecisionSaveRequest,
} from '@/api/maintenance/calculation-groups'
import {
  validateDecision,
} from './comparison-decisions'

const props = withDefaults(
  defineProps<{
    open: boolean
    row: CalculationComparisonRow | null
    saving?: boolean
  }>(),
  {
    saving: false,
  },
)

const emit = defineEmits<{
  (event: 'close'): void
  (
    event: 'save',
    sparePartId: number,
    request: CalculationDecisionSaveRequest,
  ): void
}>()

const { t } = useI18n()
const selectedCandidateKey = ref('')
const finalQuantity = ref('')
const reason = ref('')

const selectableCells = computed(() => (
  props.row
    ? Object.values(props.row.candidates).filter(
        (cell) => (
          cell.status === 'SUCCEEDED'
          && cell.recommended_quantity !== null
        ),
      )
    : []
))
const systemCell = computed(() => (
  props.row
    ? Object.values(props.row.candidates).find(
        (cell) => cell.child_id === props.row?.system_child_id,
      ) ?? null
    : null
))
const selectedCell = computed(() => (
  selectableCells.value.find(
    (cell) => (
      cell.candidate_key === selectedCandidateKey.value
    ),
  ) ?? null
))
const validation = computed(() => validateDecision({
  selectedCandidateKey: selectedCandidateKey.value,
  systemCandidateKey: systemCell.value?.candidate_key ?? '',
  finalQuantity: finalQuantity.value,
  originalQuantity: (
    selectedCell.value?.recommended_quantity ?? ''
  ),
  reason: reason.value,
}))

watch(
  () => props.row,
  (row) => {
    if (!row) return
    const selectedId = (
      row.decision?.selected_child_id
      ?? row.system_child_id
    )
    const selected = Object.values(row.candidates).find(
      (cell) => cell.child_id === selectedId,
    )
    selectedCandidateKey.value = (
      selected?.candidate_key
      ?? systemCell.value?.candidate_key
      ?? ''
    )
    finalQuantity.value = (
      row.decision?.final_quantity
      ?? selected?.recommended_quantity
      ?? ''
    )
    reason.value = row.decision?.reason ?? ''
  },
  { immediate: true },
)

watch(selectedCandidateKey, () => {
  if (!props.row?.decision) {
    finalQuantity.value = (
      selectedCell.value?.recommended_quantity ?? ''
    )
  }
})

function submit(): void {
  const row = props.row
  const cell = selectedCell.value
  if (!row || !cell || !validation.value.valid) return
  emit(
    'save',
    row.spare_part_id,
    {
      expected_version: row.decision?.version ?? 0,
      selected_child_id: cell.child_id,
      final_quantity: finalQuantity.value.trim(),
      reason: reason.value.trim() || null,
    },
  )
}
</script>

<style scoped>
.decision-drawer {
  position: fixed;
  z-index: 1200;
  inset: 0;
}

.decision-drawer__backdrop {
  position: absolute;
  width: 100%;
  height: 100%;
  border: 0;
  background: rgba(0, 0, 0, .36);
}

.decision-drawer aside {
  position: absolute;
  top: 0;
  right: 0;
  width: min(460px, 94vw);
  height: 100%;
  overflow-y: auto;
  background: var(--td-bg-color-container);
  box-shadow: -12px 0 40px rgba(0, 0, 0, .14);
}

.decision-drawer header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 24px;
  border-bottom: 1px solid var(--td-component-stroke);
}

.decision-drawer header span {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
}

.decision-drawer h2 {
  margin: 5px 0 0;
  font-size: 20px;
}

.decision-drawer header p {
  margin: 5px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.decision-drawer header button {
  align-self: flex-start;
  border: 0;
  background: transparent;
  color: var(--td-text-color-secondary);
  font-size: 24px;
  cursor: pointer;
}

.decision-drawer form {
  display: grid;
  gap: 18px;
  padding: 24px;
}

.decision-drawer label {
  display: grid;
  gap: 7px;
  color: var(--td-text-color-secondary);
  font-size: 11px;
}

.decision-drawer select,
.decision-drawer input,
.decision-drawer textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 10px;
  border: 1px solid var(--td-component-border);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.decision-drawer label small {
  color: var(--td-text-color-placeholder);
}

.decision-drawer__risk {
  padding: 14px;
  border: 1px solid var(--td-component-stroke);
  border-left: 3px solid var(--td-warning-color);
  border-radius: 6px;
}

.decision-drawer__risk span,
.decision-drawer__risk strong,
.decision-drawer__risk small {
  display: block;
}

.decision-drawer__risk span,
.decision-drawer__risk small {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
}

.decision-drawer__risk strong {
  margin-top: 5px;
  color: var(--td-warning-color);
}

.decision-drawer__risk p {
  color: var(--td-warning-color);
  font-size: 11px;
}

.decision-drawer__validation {
  margin: 0;
  color: var(--td-error-color);
  font-size: 11px;
}

.decision-drawer footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.decision-drawer footer button {
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: transparent;
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.decision-drawer footer .decision-drawer__save {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.decision-drawer footer button:disabled {
  cursor: not-allowed;
  opacity: .5;
}
</style>
