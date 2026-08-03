<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>06 / RELEASE GATE</span>
      <h2>{{ t('maintenance.scenario.steps.confirmation') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.confirmation') }}</p>
    </header>

    <div class="confirmation-ledger">
      <article>
        <span>{{ t('maintenance.scenario.fields.scenarioName') }}</span>
        <strong>{{ draft.scenario_name || '—' }}</strong>
      </article>
      <article>
        <span>{{ t('maintenance.scenario.confirmation.completedSteps') }}</span>
        <strong>{{ completedCount }} / 5</strong>
      </article>
      <article>
        <span>{{ t('maintenance.scenario.confirmation.blockingCount') }}</span>
        <strong>{{ evaluation.blockingFields.length }}</strong>
      </article>
      <article>
        <span>{{ t('maintenance.scenario.confirmation.draftVersion') }}</span>
        <strong>v{{ version }}</strong>
      </article>
    </div>

    <section
      v-if="unconfirmedFields.length > 0"
      class="confirmation-panel confirmation-panel--warning"
    >
      <h3>{{ t('maintenance.scenario.confirmation.aiReview') }}</h3>
      <button
        v-for="item in unconfirmedFields"
        :key="item.key"
        type="button"
        :disabled="disabled"
        @click="emit('confirm-field', item.key)"
      >
        <span>{{ item.key }}</span>
        <strong>{{ displayValue(item.value) }}</strong>
        <small>{{ t('maintenance.scenario.actions.confirm') }}</small>
      </button>
    </section>

    <section
      v-if="evaluation.blockingFields.length > 0"
      class="confirmation-panel confirmation-panel--blocking"
      role="alert"
    >
      <h3>{{ t('maintenance.scenario.confirmation.blocked') }}</h3>
      <div class="confirmation-chips">
        <span
          v-for="key in evaluation.blockingFields"
          :key="key"
        >{{ key }}</span>
      </div>
    </section>

    <section
      v-else
      class="confirmation-panel confirmation-panel--ready"
    >
      <div>
        <span class="confirmation-panel__signal">READY</span>
        <h3>{{ t('maintenance.scenario.confirmation.ready') }}</h3>
        <p>{{ t('maintenance.scenario.confirmation.readyHint') }}</p>
      </div>
      <button
        type="button"
        class="confirmation-panel__materialize"
        :disabled="disabled || saving"
        @click="emit('materialize')"
      >
        {{
          saving
            ? t('maintenance.scenario.actions.materializing')
            : t('maintenance.scenario.actions.materialize')
        }}
      </button>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  ScenarioDraftPayload,
} from '@/api/maintenance/scenarios'
import type {
  WizardEvaluation,
} from './scenario-validation'

const props = defineProps<{
  draft: ScenarioDraftPayload
  evaluation: WizardEvaluation
  version: number
  disabled: boolean
  saving: boolean
}>()

const emit = defineEmits<{
  'confirm-field': [key: string]
  materialize: []
}>()

const { t } = useI18n()
const completedCount = computed(() => (
  Object.entries(props.evaluation.completion)
    .filter(([key, done]) => (
      key !== 'confirmation' && done
    ))
    .length
))
const unconfirmedFields = computed(() => (
  Object.entries(props.draft.fields)
    .filter(([, field]) => (
      field !== undefined
      && !field.confirmed
      && field.value !== null
    ))
    .map(([key, field]) => ({
      key,
      value: field?.value,
    }))
))

function displayValue(value: unknown): string {
  if (
    typeof value === 'string'
    || typeof value === 'number'
    || typeof value === 'boolean'
  ) {
    return String(value)
  }
  if (Array.isArray(value)) {
    return `${value.length} items`
  }
  return value ? 'Configured' : '—'
}
</script>

<style scoped>
.confirmation-ledger {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-component-stroke);
}

.confirmation-ledger article {
  display: grid;
  min-height: 96px;
  align-content: space-between;
  gap: 12px;
  padding: 16px;
  background: var(--td-bg-color-container);
}

.confirmation-ledger span {
  color: var(--td-text-color-secondary);
  font-size: 11px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.confirmation-ledger strong {
  overflow: hidden;
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.confirmation-panel {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.confirmation-panel h3,
.confirmation-panel p {
  margin: 0;
}

.confirmation-panel p {
  margin-top: 6px;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.confirmation-panel--warning {
  border-left: 3px solid var(--td-warning-color);
}

.confirmation-panel--warning button {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr) auto;
  gap: 12px;
  padding: 10px;
  border: 0;
  border-top: 1px solid var(--td-component-stroke);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.confirmation-panel--warning small {
  color: var(--td-brand-color);
}

.confirmation-panel--blocking {
  border-color: var(--td-error-color);
}

.confirmation-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.confirmation-chips span {
  padding: 4px 8px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--td-error-color) 10%, transparent);
  color: var(--td-error-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.confirmation-panel--ready {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  border-color: var(--td-success-color);
}

.confirmation-panel__signal {
  color: var(--td-success-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.12em;
}

.confirmation-panel__materialize {
  min-height: 44px;
  padding: 0 20px;
  border: 1px solid var(--td-success-color);
  border-radius: 5px;
  background: var(--td-success-color);
  color: #fff;
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

@media (max-width: 760px) {
  .confirmation-ledger {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .confirmation-panel--ready {
    grid-template-columns: 1fr;
  }
}
</style>
