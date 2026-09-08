<template>
  <section class="scenario-step">
    <header class="scenario-step__header">
      <span>04 / RELIABILITY</span>
      <h2>{{ t('maintenance.scenario.steps.reliabilityRepair') }}</h2>
      <p>{{ t('maintenance.scenario.stepHints.reliabilityRepair') }}</p>
    </header>

    <ScenarioFieldShell
      field-key="reliability_profiles"
      :label="t('maintenance.scenario.fields.reliabilityProfiles')"
      required
      v-bind="shellProps('reliability_profiles')"
      :disabled="disabled || loading"
      @confirm="confirm('reliability_profiles')"
      @open-evidence="emit('open-evidence', $event)"
    >
      <div
        v-if="profiles.length > 0"
        class="profile-grid"
      >
        <label
          v-for="profile in profiles"
          :key="profile.id"
          class="profile-card"
        >
          <input
            type="checkbox"
            :checked="selectedIds.has(profile.id)"
            :disabled="disabled"
            @change="toggle(profile)"
          >
          <span>
            <strong>{{ profile.profile_code }}</strong>
            <small>
              {{ profile.model_type }}
              · {{ profile.data_source_type }}
            </small>
          </span>
        </label>
      </div>
      <p
        v-else
        class="scenario-step__notice"
      >
        {{
          loading
            ? t('maintenance.scenario.loading')
            : t('maintenance.scenario.empty.reliability')
        }}
      </p>
    </ScenarioFieldShell>

    <div class="scenario-step__grid">
      <ScenarioFieldShell
        field-key="repair_policy"
        :label="t('maintenance.scenario.fields.repairPolicy')"
        :required="false"
        v-bind="shellProps('repair_policy')"
        :disabled="disabled"
        @confirm="confirm('repair_policy')"
      >
        <select
          :value="String(field('repair_policy').value ?? '')"
          :disabled="disabled"
          @change="patch('repair_policy', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option value="ENABLED">ENABLED</option>
          <option value="DISABLED">DISABLED</option>
        </select>
      </ScenarioFieldShell>

      <ScenarioFieldShell
        field-key="common_shock_policy"
        :label="t('maintenance.scenario.fields.shockPolicy')"
        :required="false"
        v-bind="shellProps('common_shock_policy')"
        :disabled="disabled"
        @confirm="confirm('common_shock_policy')"
      >
        <select
          :value="String(field('common_shock_policy').value ?? '')"
          :disabled="disabled"
          @change="patch('common_shock_policy', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">
            {{ t('maintenance.scenario.selectPlaceholder') }}
          </option>
          <option value="ENABLED">ENABLED</option>
          <option value="DISABLED">DISABLED</option>
        </select>
      </ScenarioFieldShell>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { masterDataApi } from '@/api/maintenance/master-data'
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

interface ReliabilityOption {
  id: number
  profile_code: string
  model_type: string
  data_source_type: string
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
const profiles = ref<ReliabilityOption[]>([])
const loading = ref(false)

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

const selectedProfiles = computed(() => {
  const value = field('reliability_profiles').value
  return Array.isArray(value)
    ? value as Array<Record<string, unknown>>
    : []
})
const selectedIds = computed(() => new Set(
  selectedProfiles.value
    .map((item) => Number(item.profile_id))
    .filter((id) => id > 0),
))

function toggle(profile: ReliabilityOption): void {
  const retained = selectedProfiles.value.filter(
    (item) => Number(item.profile_id) !== profile.id,
  )
  const next = selectedIds.value.has(profile.id)
    ? retained
    : [
        ...retained,
        {
          profile_id: profile.id,
          profile_code: profile.profile_code,
          status: 'confirmed',
        },
      ]
  patch('reliability_profiles', next)
}

function patch(key: string, value: unknown): void {
  emit(
    'patch',
    key,
    userField(value, field(key)),
  )
}

function confirm(key: string): void {
  emit(
    'patch',
    key,
    confirmedField(field(key)),
  )
}

onMounted(async () => {
  loading.value = true
  try {
    const response = await masterDataApi.list<
      ReliabilityOption
    >(
      {
        endpoint: (
          '/v1/master-data/reliability-profiles'
        ),
      },
      {
        page: 1,
        page_size: 200,
        include_inactive: false,
        sort_by: 'profile_code',
        sort_order: 'asc',
      },
    )
    profiles.value = response.data.items
  } catch {
    profiles.value = []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.profile-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  cursor: pointer;
}

.profile-card:has(input:checked) {
  border-color: var(--td-brand-color);
  background: color-mix(in srgb, var(--td-brand-color) 7%, transparent);
}

.profile-card input {
  width: 16px !important;
  min-height: 16px !important;
}

.profile-card span {
  display: grid;
  gap: 2px;
}

.profile-card strong {
  font-size: 13px;
}

.profile-card small {
  color: var(--td-text-color-secondary);
  font-size: 11px;
}

@media (max-width: 680px) {
  .profile-grid {
    grid-template-columns: 1fr;
  }
}
</style>
