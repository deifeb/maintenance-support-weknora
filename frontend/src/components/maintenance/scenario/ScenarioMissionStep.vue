<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>03 / MISSION</span>
      <h2>{{ t('maintenance.scenario.steps.mission') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.mission') }}</p>
    </header>

    <ScenarioFieldShell
      field-key="stages"
      :label="t('maintenance.scenario.fields.stages')"
      required
      :source="stagesField.source"
      :confidence="stagesField.confidence"
      :risk="stagesField.risk"
      :confirmed="stagesField.confirmed"
      :evidence-refs="stagesField.evidence_refs"
      :disabled="disabled"
      @confirm="confirm"
      @open-evidence="emit('open-evidence', $event)"
    >
      <div class="stage-composer">
        <label>
          <span>{{ t('maintenance.scenario.fields.stageCode') }}</span>
          <input
            :value="stage.stage_code"
            :disabled="disabled"
            @input="update({ stage_code: ($event.target as HTMLInputElement).value })"
          >
        </label>
        <label>
          <span>{{ t('maintenance.scenario.fields.stageName') }}</span>
          <input
            :value="stage.stage_name"
            :disabled="disabled"
            @input="update({ stage_name: ($event.target as HTMLInputElement).value })"
          >
        </label>
        <label>
          <span>{{ t('maintenance.scenario.fields.durationHours') }}</span>
          <input
            type="number"
            min="0.1"
            step="0.1"
            :value="stage.duration_hours"
            :disabled="disabled"
            @input="update({ duration_hours: ($event.target as HTMLInputElement).value })"
          >
        </label>
        <label>
          <span>{{ t('maintenance.scenario.fields.activeQuantity') }}</span>
          <input
            type="number"
            min="0"
            :value="activeQuantity"
            :disabled="disabled"
            @input="updateUsage(Number(($event.target as HTMLInputElement).value))"
          >
        </label>
        <label class="stage-composer__wide">
          <span>{{ t('maintenance.scenario.fields.maintenanceLevel') }}</span>
          <input
            :value="stage.maintenance_level ?? ''"
            :disabled="disabled"
            @input="update({ maintenance_level: ($event.target as HTMLInputElement).value || null })"
          >
        </label>
      </div>
    </ScenarioFieldShell>

    <p
      v-if="fleetGroupKey === null"
      class="scenario-step__notice"
    >
      {{ t('maintenance.scenario.empty.fleetFirst') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  ScenarioDraftFleetGroup,
  ScenarioDraftPayload,
  ScenarioDraftStage,
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
const stagesField = computed(
  () => draftField(props.draft, 'stages'),
)
const fleetGroupKey = computed(() => {
  const value = (
    props.draft.fields.fleet_groups?.value
  )
  if (!Array.isArray(value)) return null
  return (
    (value[0] as ScenarioDraftFleetGroup | undefined)
      ?.client_key ?? null
  )
})
const stage = computed<ScenarioDraftStage>(() => {
  const value = stagesField.value.value
  if (Array.isArray(value) && value[0]) {
    return value[0] as ScenarioDraftStage
  }
  return {
    client_key: 'stage-a',
    stage_code: '',
    stage_name: '',
    stage_order: 1,
    duration_hours: '24',
    fleet_usages: (
      fleetGroupKey.value
        ? [{
            fleet_group_key: fleetGroupKey.value,
            active_quantity: 0,
          }]
        : []
    ),
    shocks: [],
  }
})
const activeQuantity = computed(
  () => stage.value.fleet_usages[0]
    ?.active_quantity ?? 0,
)

function commit(next: ScenarioDraftStage): void {
  emit(
    'patch',
    'stages',
    userField([next], stagesField.value),
  )
}

function update(
  patch: Partial<ScenarioDraftStage>,
): void {
  commit({
    ...stage.value,
    ...patch,
  })
}

function updateUsage(quantity: number): void {
  const key = (
    fleetGroupKey.value
    ?? stage.value.fleet_usages[0]
      ?.fleet_group_key
  )
  commit({
    ...stage.value,
    fleet_usages: key
      ? [{
          ...stage.value.fleet_usages[0],
          fleet_group_key: key,
          active_quantity: Math.max(0, quantity || 0),
        }]
      : [],
  })
}

function confirm(): void {
  emit(
    'patch',
    'stages',
    confirmedField(stagesField.value),
  )
}
</script>

<style scoped>
.stage-composer {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.stage-composer label {
  display: grid;
  gap: 6px;
}

.stage-composer label span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.stage-composer__wide {
  grid-column: 1 / -1;
}

@media (max-width: 680px) {
  .stage-composer {
    grid-template-columns: 1fr;
  }

  .stage-composer__wide {
    grid-column: auto;
  }
}
</style>
