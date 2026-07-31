<template>
  <main class="calculation-setup">
    <MaintenancePageHeader
      :eyebrow="t('maintenance.calculation.setup.eyebrow')"
      :title="t('maintenance.calculation.setup.title')"
      :description="t('maintenance.calculation.setup.description')"
    />

    <form class="calculation-setup__version" @submit.prevent="loadSnapshot">
      <label>
        <span>{{ t('maintenance.calculation.setup.scenarioVersion') }}</span>
        <input
          v-model.number="scenarioVersionId"
          type="number"
          min="1"
          required
        >
      </label>
      <button type="submit" :disabled="loading || scenarioVersionId < 1">
        {{
          loading
            ? t('maintenance.calculation.setup.loading')
            : t('maintenance.calculation.setup.load')
        }}
      </button>
    </form>

    <MaintenanceErrorState
      v-if="error"
      :error="error"
      :locale="locale"
      @retry="loadSnapshot"
    />

    <section
      v-if="snapshot"
      class="calculation-setup__snapshot"
    >
      <header>
        <div>
          <span>READ ONLY</span>
          <h2>{{ t('maintenance.calculation.setup.inputTitle') }}</h2>
        </div>
        <MaintenanceStatusTag :status="snapshot.version.status" />
      </header>
      <dl>
        <div>
          <dt>{{ t('maintenance.calculation.setup.versionCode') }}</dt>
          <dd>{{ snapshot.version.version_code }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.setup.serviceLevel') }}</dt>
          <dd>{{ snapshot.version.default_service_level }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.setup.executionPolicy') }}</dt>
          <dd>{{ snapshot.version.execution_mode }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.setup.missingPolicy') }}</dt>
          <dd>{{ snapshot.version.missing_parameter_policy }}</dd>
        </div>
      </dl>
      <footer>
        <span>{{ snapshot.stages.length }} stages</span>
        <span>{{ snapshot.fleet_groups.length }} fleet groups</span>
        <span>{{ snapshot.overrides.length }} overrides</span>
      </footer>
    </section>

    <template v-if="snapshot?.version.status === 'PUBLISHED'">
      <ModelRecommendationPanel
        :recommendation="recommendation"
        :loading="recommendationLoading"
      />

      <section v-if="recommendation" class="calculation-setup__selection">
        <header>
          <div>
            <h2>{{ t('maintenance.calculation.selection.title') }}</h2>
            <p>{{ t('maintenance.calculation.selection.description') }}</p>
          </div>
          <strong>
            {{ selectedCandidateKeys.length }}
            {{ t('maintenance.calculation.setup.selectedCount') }}
          </strong>
        </header>
        <ModelSelectionTable
          v-model="selectedCandidateKeys"
          :rows="candidateRows"
        />
        <p
          v-if="!selectionValidation.valid"
          class="calculation-setup__validation"
        >
          {{ t('maintenance.calculation.setup.selectionInvalid') }}
        </p>
        <div class="calculation-setup__launch">
          <button
            type="button"
            :disabled="!canRun || !selectionValidation.valid || groupStore.mutating"
            @click="startCalculation"
          >
            {{
              groupStore.mutating
                ? t('maintenance.calculation.setup.starting')
                : t('maintenance.calculation.setup.start')
            }}
          </button>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import type {
  MaintenanceClientError,
} from '@/api/maintenance/types'
import {
  recommendationApi,
  type ModelRecommendationSet,
} from '@/api/maintenance/model-recommendations'
import {
  scenarioApi,
  type ScenarioFullVersion,
} from '@/api/maintenance/scenarios'
import {
  normalizeMaintenanceError,
} from '@/api/maintenance/client'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import ModelRecommendationPanel from '@/components/maintenance/calculation/ModelRecommendationPanel.vue'
import ModelSelectionTable from '@/components/maintenance/calculation/ModelSelectionTable.vue'
import {
  buildCandidateRows,
  initialCandidateSelection,
  validateCandidateSelection,
} from '@/components/maintenance/calculation/model-selection'
import { useCalculationGroupStore } from '@/stores/maintenance/calculationGroup'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const groupStore = useCalculationGroupStore()
const permissionStore = useMaintenancePermissionsStore()

const queryVersion = Number(
  route.query.scenario_version_id
  ?? route.query.scenarioVersionId
  ?? 0,
)
const scenarioVersionId = ref(
  Number.isInteger(queryVersion) && queryVersion > 0
    ? queryVersion
    : 0,
)
const snapshot = ref<ScenarioFullVersion | null>(null)
const recommendation = ref<ModelRecommendationSet | null>(null)
const selectedCandidateKeys = ref<string[]>([])
const loading = ref(false)
const recommendationLoading = ref(false)
const error = ref<MaintenanceClientError | null>(null)

const candidateRows = computed(() => (
  recommendation.value
    ? buildCandidateRows(recommendation.value)
    : []
))
const selectionValidation = computed(() => (
  recommendation.value
    ? validateCandidateSelection(
        recommendation.value,
        selectedCandidateKeys.value,
      )
    : {
        valid: false,
        invalidCandidateKeys: [],
        missingPrimary: true,
      }
))
const canRun = computed(
  () => permissionStore.permissions.runCalculation,
)

function idempotencyKey(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random()}`
  return `${prefix}:${suffix}`
}

async function loadSnapshot(): Promise<void> {
  if (scenarioVersionId.value < 1) return
  loading.value = true
  error.value = null
  snapshot.value = null
  recommendation.value = null
  selectedCandidateKeys.value = []
  try {
    const response = await scenarioApi.getFullVersion(
      scenarioVersionId.value,
    )
    if (response.data.version.status !== 'PUBLISHED') {
      throw {
        code: 'SCENARIO_NOT_PUBLISHED',
        message: t(
          'maintenance.calculation.setup.invalidPublished',
        ),
        retryable: false,
      }
    }
    snapshot.value = response.data
    recommendationLoading.value = true
    const recommended = await recommendationApi.recommend(
      scenarioVersionId.value,
    )
    recommendation.value = recommended.data
    selectedCandidateKeys.value = (
      initialCandidateSelection(recommended.data)
    )
  } catch (value) {
    error.value = normalizeMaintenanceError(value)
  } finally {
    recommendationLoading.value = false
    loading.value = false
  }
}

async function startCalculation(): Promise<void> {
  const current = recommendation.value
  if (!current || !selectionValidation.value.valid) return
  try {
    const group = await groupStore.create(
      {
        scenario_version_id: scenarioVersionId.value,
        primary_candidate_key: (
          current.primary?.candidate_key ?? ''
        ),
        selected_candidate_keys: [
          ...selectedCandidateKeys.value,
        ],
        random_seed: 20260723,
      },
      idempotencyKey('calculation-group'),
    )
    await router.push({
      name: 'maintenanceCalculationProgress',
      params: { groupId: group.id },
    })
  } catch {
    error.value = groupStore.error
  }
}

onMounted(() => {
  if (scenarioVersionId.value > 0) {
    void loadSnapshot()
  }
})
</script>

<style scoped>
.calculation-setup {
  display: grid;
  gap: 18px;
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px;
}

.calculation-setup__version {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-setup__version label {
  display: grid;
  flex: 1;
  gap: 6px;
  color: var(--td-text-color-secondary);
  font-size: 11px;
}

.calculation-setup__version input {
  min-height: 38px;
  padding: 7px 10px;
  border: 1px solid var(--td-component-border);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.calculation-setup button {
  min-height: 38px;
  padding: 0 15px;
  border: 1px solid var(--td-brand-color);
  border-radius: 5px;
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
  font: inherit;
  cursor: pointer;
}

.calculation-setup button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.calculation-setup__snapshot {
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-setup__snapshot > header,
.calculation-setup__snapshot > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
}

.calculation-setup__snapshot > header {
  border-bottom: 1px solid var(--td-component-stroke);
}

.calculation-setup__snapshot header span {
  color: var(--td-success-color);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .14em;
}

.calculation-setup__snapshot h2 {
  margin: 3px 0 0;
  font-size: 17px;
}

.calculation-setup__snapshot dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;
}

.calculation-setup__snapshot dl > div {
  padding: 18px;
  border-right: 1px solid var(--td-component-stroke);
}

.calculation-setup__snapshot dt {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
}

.calculation-setup__snapshot dd {
  margin: 6px 0 0;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 12px;
}

.calculation-setup__snapshot > footer {
  justify-content: flex-start;
  border-top: 1px solid var(--td-component-stroke);
  color: var(--td-text-color-placeholder);
  font-size: 10px;
}

.calculation-setup__selection {
  display: grid;
  gap: 14px;
}

.calculation-setup__selection > header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
}

.calculation-setup__selection h2 {
  margin: 0;
  font-size: 18px;
}

.calculation-setup__selection p {
  margin: 5px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.calculation-setup__selection header strong {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.calculation-setup__validation {
  color: var(--td-error-color) !important;
}

.calculation-setup__launch {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 760px) {
  .calculation-setup { padding: 22px 16px; }
  .calculation-setup__snapshot dl {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
