<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>01 / BASIS</span>
      <h2>{{ t('maintenance.scenario.steps.basics') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.basics') }}</p>
    </header>

    <div class="scenario-step__grid">
      <ScenarioFieldShell
        field-key="scenario_name"
        :label="t('maintenance.scenario.fields.scenarioName')"
        required
        :source="nameField.source"
        :confidence="nameField.confidence"
        :risk="nameField.risk"
        :confirmed="nameField.confirmed"
        :evidence-refs="nameField.evidence_refs"
        :disabled="disabled"
        @confirm="confirm('scenario_name')"
        @open-evidence="openEvidence"
      >
        <input
          :value="draft.scenario_name"
          :disabled="disabled"
          maxlength="200"
          @input="rename(($event.target as HTMLInputElement).value)"
        >
      </ScenarioFieldShell>

      <ScenarioFieldShell
        v-for="definition in fieldDefinitions"
        :key="definition.key"
        :field-key="definition.key"
        :label="t(definition.label)"
        required
        :source="field(definition.key).source"
        :confidence="field(definition.key).confidence"
        :risk="field(definition.key).risk"
        :confirmed="field(definition.key).confirmed"
        :evidence-refs="field(definition.key).evidence_refs"
        :disabled="disabled"
        @confirm="confirm(definition.key)"
        @open-evidence="openEvidence"
      >
        <select
          v-if="definition.type === 'select'"
          :value="String(field(definition.key).value ?? '')"
          :disabled="disabled"
          @change="change(definition.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option value="LOW">LOW</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="HIGH">HIGH</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <input
          v-else
          :type="definition.type"
          :value="String(field(definition.key).value ?? '')"
          :disabled="disabled"
          @input="change(definition.key, ($event.target as HTMLInputElement).value)"
        >
      </ScenarioFieldShell>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
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
  rename: [name: string]
  patch: [key: string, field: ScenarioFieldState]
  'open-evidence': [references: string[]]
}>()

const { t } = useI18n()

const fieldDefinitions = [
  {
    key: 'mission_code',
    label: 'maintenance.scenario.fields.missionCode',
    type: 'text',
  },
  {
    key: 'start_at',
    label: 'maintenance.scenario.fields.startAt',
    type: 'datetime-local',
  },
  {
    key: 'end_at',
    label: 'maintenance.scenario.fields.endAt',
    type: 'datetime-local',
  },
  {
    key: 'priority',
    label: 'maintenance.scenario.fields.priority',
    type: 'select',
  },
] as const

const nameField = computed(() => ({
  ...draftField(props.draft, 'scenario_name'),
  value: props.draft.scenario_name,
}))

function field(key: string): ScenarioFieldState {
  return draftField(props.draft, key)
}

function rename(value: string): void {
  emit('rename', value)
  emit(
    'patch',
    'scenario_name',
    userField(value, nameField.value),
  )
}

function change(
  key: string,
  value: string,
): void {
  emit(
    'patch',
    key,
    userField(value || null, field(key)),
  )
}

function confirm(key: string): void {
  if (key === 'scenario_name') {
    emit(
      'patch',
      key,
      confirmedField(nameField.value),
    )
    return
  }
  emit(
    'patch',
    key,
    confirmedField(field(key)),
  )
}

function openEvidence(references: string[]): void {
  emit('open-evidence', references)
}
</script>
