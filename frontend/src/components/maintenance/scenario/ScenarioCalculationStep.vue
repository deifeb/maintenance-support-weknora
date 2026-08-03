<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>05 / CALCULATION</span>
      <h2>{{ t('maintenance.scenario.steps.calculation') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.calculation') }}</p>
    </header>

    <div class="scenario-step__grid">
      <ScenarioFieldShell
        v-for="definition in definitions"
        :key="definition.key"
        :field-key="definition.key"
        :label="t(definition.label)"
        required
        v-bind="shellProps(definition.key)"
        :disabled="disabled"
        @confirm="confirm(definition.key)"
        @open-evidence="emit('open-evidence', $event)"
      >
        <select
          v-if="definition.options"
          :value="String(field(definition.key).value ?? '')"
          :disabled="disabled"
          @change="patch(definition.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option
            v-for="option in definition.options"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>
        <input
          v-else
          type="number"
          min="0.01"
          max="0.99"
          step="0.01"
          :value="String(field(definition.key).value ?? '')"
          :disabled="disabled"
          @input="patch(definition.key, ($event.target as HTMLInputElement).value)"
        >
      </ScenarioFieldShell>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  ScenarioDraftPayload,
  ScenarioFieldState,
} from '@/api/maintenance/scenarios'
import ScenarioFieldShell from './ScenarioFieldShell.vue'
import {
  confirmedField,
  draftField,
  userField,
} from './scenario-field-utils'

const props = defineProps<{
  draft: ScenarioDraftPayload
  disabled: boolean
}>()

const emit = defineEmits<{
  patch: [key: string, field: ScenarioFieldState]
  'open-evidence': [references: string[]]
}>()

const { t } = useI18n()
const definitions: ReadonlyArray<{
  key: string
  label: string
  options?: readonly string[]
}> = [
  {
    key: 'service_level',
    label: 'maintenance.scenario.fields.serviceLevel',
  },
  {
    key: 'execution_preference',
    label: 'maintenance.scenario.fields.executionMode',
    options: [
      'AUTO',
      'ANALYTICAL',
      'MONTE_CARLO',
      'COMPARE',
    ],
  },
  {
    key: 'missing_parameter_policy',
    label: 'maintenance.scenario.fields.missingPolicy',
    options: [
      'STRICT',
      'WARN_AND_SKIP',
      'FALLBACK',
    ],
  },
]

function field(key: string): ScenarioFieldState {
  return draftField(props.draft, key)
}

function shellProps(key: string) {
  const value = field(key)
  return {
    source: value.source,
    confidence: value.confidence,
    risk: value.risk,
    confirmed: value.confirmed,
    evidenceRefs: value.evidence_refs,
  }
}

function patch(key: string, value: unknown): void {
  emit(
    'patch',
    key,
    userField(value || null, field(key)),
  )
}

function confirm(key: string): void {
  emit(
    'patch',
    key,
    confirmedField(field(key)),
  )
}
</script>
