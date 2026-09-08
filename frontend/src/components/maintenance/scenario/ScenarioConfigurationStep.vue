<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>02 / FLEET</span>
      <h2>{{ t('maintenance.scenario.steps.configuration') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.configuration') }}</p>
    </header>

    <div class="scenario-step__grid">
      <ScenarioFieldShell
        field-key="equipment_model_id"
        :label="t('maintenance.scenario.fields.equipmentModel')"
        required
        v-bind="shellProps('equipment_model_id')"
        :disabled="disabled || loading"
        @confirm="confirm('equipment_model_id')"
        @open-evidence="openEvidence"
      >
        <select
          :value="String(field('equipment_model_id').value ?? '')"
          :disabled="disabled || loading"
          @change="selectEquipment(($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option
            v-for="item in equipment"
            :key="item.id"
            :value="item.id"
          >
            {{ item.code }} · {{ item.name }}
          </option>
        </select>
      </ScenarioFieldShell>

      <ScenarioFieldShell
        field-key="configuration_version_id"
        :label="t('maintenance.scenario.fields.configurationVersion')"
        required
        v-bind="shellProps('configuration_version_id')"
        :disabled="disabled || loading"
        @confirm="confirm('configuration_version_id')"
        @open-evidence="openEvidence"
      >
        <select
          :value="String(field('configuration_version_id').value ?? '')"
          :disabled="disabled || loading"
          @change="selectConfiguration(($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option
            v-for="item in visibleConfigurations"
            :key="item.id"
            :value="item.id"
          >
            {{ item.version_code }} · {{ item.version_name }}
          </option>
        </select>
      </ScenarioFieldShell>

      <ScenarioFieldShell
        class="scenario-step__wide"
        field-key="fleet_groups"
        :label="t('maintenance.scenario.fields.fleetGroups')"
        required
        v-bind="shellProps('fleet_groups')"
        :disabled="disabled"
        @confirm="confirm('fleet_groups')"
        @open-evidence="openEvidence"
      >
        <div class="fleet-composer">
          <label>
            <span>{{ t('maintenance.scenario.fields.fleetCode') }}</span>
            <input
              :value="fleetCode"
              :disabled="disabled"
              @input="fleetCode = ($event.target as HTMLInputElement).value"
              @change="emitFleet"
            >
          </label>
          <label>
            <span>{{ t('maintenance.scenario.fields.quantity') }}</span>
            <input
              :value="quantity"
              type="number"
              min="1"
              :disabled="disabled"
              @input="quantity = Number(($event.target as HTMLInputElement).value)"
              @change="emitFleet"
            >
          </label>
          <button
            type="button"
            :disabled="disabled || !selectedConfiguration"
            @click="emitFleet"
          >
            {{ t('maintenance.scenario.actions.applyFleet') }}
          </button>
        </div>
      </ScenarioFieldShell>
    </div>

    <p
      v-if="loadError"
      class="scenario-step__notice scenario-step__notice--error"
      role="alert"
    >
      {{ t('maintenance.scenario.errors.masterData') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import { useI18n } from 'vue-i18n'
import {
  masterDataApi,
} from '@/api/maintenance/master-data'
import type {
  ScenarioDraftFleetGroup,
  ScenarioDraftPayload,
  ScenarioFieldState,
} from '@/api/maintenance/scenarios'
import ScenarioFieldShell from './ScenarioFieldShell.vue'
import {
  confirmedField,
  draftField,
  userField,
} from './scenario-field-utils'

interface EquipmentOption {
  id: number
  code: string
  name: string
}

interface ConfigurationOption {
  id: number
  equipment_model_id: number
  version_code: string
  version_name: string
  status: string
}

const props = defineProps<{
  draft: ScenarioDraftPayload
  disabled: boolean
}>()

const emit = defineEmits<{
  patch: [key: string, field: ScenarioFieldState]
  'open-evidence': [references: string[]]
}>()

const { t } = useI18n()
const equipment = ref<EquipmentOption[]>([])
const configurations = ref<ConfigurationOption[]>([])
const loading = ref(false)
const loadError = ref(false)
const quantity = ref(10)
const fleetCode = ref('FLEET-A')

const selectedEquipment = computed(() => Number(
  field('equipment_model_id').value ?? 0,
))
const selectedConfiguration = computed(() => Number(
  field('configuration_version_id').value ?? 0,
))
const visibleConfigurations = computed(() => (
  configurations.value.filter((item) => (
    item.status === 'PUBLISHED'
    && (
      selectedEquipment.value === 0
      || item.equipment_model_id
      === selectedEquipment.value
    )
  ))
))

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

function patch(
  key: string,
  value: unknown,
): void {
  emit(
    'patch',
    key,
    userField(value, field(key)),
  )
}

function selectEquipment(value: string): void {
  const id = Number(value)
  patch('equipment_model_id', id || null)
  const current = configurations.value.find(
    (item) => item.id === selectedConfiguration.value,
  )
  if (!current || current.equipment_model_id !== id) {
    patch('configuration_version_id', null)
    patch('fleet_groups', [])
  }
}

function selectConfiguration(value: string): void {
  patch(
    'configuration_version_id',
    Number(value) || null,
  )
}

function emitFleet(): void {
  if (
    selectedConfiguration.value <= 0
    || quantity.value <= 0
  ) {
    patch('fleet_groups', [])
    return
  }
  const code = fleetCode.value.trim() || 'FLEET-A'
  const fleet: ScenarioDraftFleetGroup = {
    client_key: code.toLowerCase(),
    group_code: code,
    group_name: code,
    configuration_version_id: (
      selectedConfiguration.value
    ),
    initial_quantity: quantity.value,
    age_groups: [],
  }
  patch('fleet_groups', [fleet])
}

function confirm(key: string): void {
  emit(
    'patch',
    key,
    confirmedField(field(key)),
  )
}

function openEvidence(references: string[]): void {
  emit('open-evidence', references)
}

onMounted(async () => {
  loading.value = true
  loadError.value = false
  try {
    const query = {
      page: 1,
      page_size: 200,
      include_inactive: false,
      sort_by: 'id',
      sort_order: 'asc' as const,
    }
    const [equipmentResult, configurationResult] = (
      await Promise.all([
        masterDataApi.list<EquipmentOption>(
          {
            endpoint: (
              '/v1/master-data/equipment-models'
            ),
          },
          query,
        ),
        masterDataApi.list<ConfigurationOption>(
          {
            endpoint: (
              '/v1/master-data/configuration-versions'
            ),
          },
          query,
        ),
      ])
    )
    equipment.value = equipmentResult.data.items
    configurations.value = (
      configurationResult.data.items
    )
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.fleet-composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px auto;
  align-items: end;
  gap: 12px;
}

.fleet-composer label {
  display: grid;
  gap: 6px;
}

.fleet-composer label span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.fleet-composer button {
  min-height: 40px;
  padding: 0 16px;
  border: 1px solid var(--td-brand-color);
  border-radius: 5px;
  background: transparent;
  color: var(--td-brand-color);
  cursor: pointer;
}

.fleet-composer button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

@media (max-width: 680px) {
  .fleet-composer {
    grid-template-columns: 1fr;
  }
}
</style>
