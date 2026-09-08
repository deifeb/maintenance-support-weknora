<template>
  <section
    class="scenario-field"
    :class="{
      'scenario-field--blocking': risk === 'BLOCKING' && !confirmed,
      'scenario-field--disabled': disabled,
    }"
  >
    <header class="scenario-field__header">
      <div class="scenario-field__identity">
        <span class="scenario-field__key">{{ fieldKey }}</span>
        <label class="scenario-field__label">
          {{ label }}
          <span
            v-if="required"
            class="scenario-field__required"
            aria-label="required"
          >*</span>
        </label>
      </div>

      <div class="scenario-field__signals">
        <MaintenanceSourceTag
          :source="source"
          :evidence-reference="evidenceRefs[0]"
        />
        <MaintenanceRiskTag :risk="risk" />
        <span
          v-if="confidence !== null"
          class="scenario-field__confidence"
        >
          {{ Math.round(Number(confidence) * 100) }}%
        </span>
      </div>
    </header>

    <div class="scenario-field__control">
      <slot :update-value="updateValue" />
    </div>

    <footer
      v-if="evidenceRefs.length > 0 || !confirmed"
      class="scenario-field__footer"
    >
      <button
        v-if="evidenceRefs.length > 0"
        type="button"
        class="scenario-field__evidence"
        :disabled="disabled"
        @click="emit('open-evidence', evidenceRefs)"
      >
        {{ evidenceRefs.length }}
        {{ t('maintenance.scenario.actions.evidence') }}
      </button>
      <button
        v-if="!confirmed"
        type="button"
        class="scenario-field__confirm"
        :disabled="disabled"
        @click="emit('confirm')"
      >
        {{ t('maintenance.scenario.actions.confirm') }}
      </button>
      <span
        v-else
        class="scenario-field__confirmed"
      >
        {{ t('maintenance.scenario.confirmed') }}
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import MaintenanceRiskTag from '@/components/maintenance/common/MaintenanceRiskTag.vue'
import MaintenanceSourceTag from '@/components/maintenance/common/MaintenanceSourceTag.vue'
import { useI18n } from 'vue-i18n'
import type {
  ScenarioFieldRisk,
  ScenarioFieldSource,
} from '@/api/maintenance/scenarios'

defineProps<{
  fieldKey: string
  label: string
  required: boolean
  source: ScenarioFieldSource
  confidence: string | null
  risk: ScenarioFieldRisk
  confirmed: boolean
  evidenceRefs: string[]
  disabled: boolean
}>()

const emit = defineEmits<{
  'update:value': [value: unknown]
  confirm: []
  'open-evidence': [references: string[]]
}>()

const { t } = useI18n()

function updateValue(value: unknown): void {
  emit('update:value', value)
}
</script>

<style scoped>
.scenario-field {
  position: relative;
  display: grid;
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--td-brand-color) 4%, transparent), transparent 42%),
    var(--td-bg-color-container);
  transition:
    border-color 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.scenario-field:focus-within {
  border-color: var(--td-brand-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--td-brand-color) 12%, transparent);
  transform: translateY(-1px);
}

.scenario-field--blocking {
  border-left: 3px solid var(--td-error-color);
}

.scenario-field--disabled {
  opacity: 0.68;
}

.scenario-field__header,
.scenario-field__footer,
.scenario-field__signals {
  display: flex;
  align-items: center;
}

.scenario-field__header {
  justify-content: space-between;
  gap: 16px;
}

.scenario-field__identity {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.scenario-field__key {
  color: var(--td-text-color-placeholder);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.scenario-field__label {
  color: var(--td-text-color-primary);
  font-size: 14px;
  font-weight: 650;
}

.scenario-field__required {
  color: var(--td-error-color);
}

.scenario-field__signals {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.scenario-field__confidence {
  min-width: 38px;
  color: var(--td-text-color-secondary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
  text-align: right;
}

.scenario-field__control :deep(input),
.scenario-field__control :deep(select),
.scenario-field__control :deep(textarea) {
  width: 100%;
  min-height: 40px;
  padding: 9px 11px;
  border: 1px solid var(--td-component-border);
  border-radius: 5px;
  outline: none;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.scenario-field__control :deep(textarea) {
  min-height: 92px;
  resize: vertical;
}

.scenario-field__control :deep(input:focus),
.scenario-field__control :deep(select:focus),
.scenario-field__control :deep(textarea:focus) {
  border-color: var(--td-brand-color);
}

.scenario-field__footer {
  justify-content: flex-end;
  gap: 8px;
  min-height: 24px;
}

.scenario-field__footer button {
  padding: 3px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.scenario-field__confirm {
  background: color-mix(in srgb, var(--td-warning-color) 12%, transparent) !important;
  color: var(--td-warning-color) !important;
}

.scenario-field__confirmed {
  color: var(--td-success-color);
  font-size: 12px;
}

@media (max-width: 680px) {
  .scenario-field__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .scenario-field__signals {
    justify-content: flex-start;
  }
}
</style>
