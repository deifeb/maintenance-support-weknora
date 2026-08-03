<template>
  <main class="calculation-progress">
    <button
      type="button"
      class="calculation-progress__back"
      @click="back"
    >
      ← {{ t('maintenance.calculation.progress.back') }}
    </button>

    <MaintenancePageHeader
      :eyebrow="t('maintenance.calculation.progress.eyebrow')"
      :title="t('maintenance.calculation.progress.title')"
      :description="t('maintenance.calculation.progress.description')"
    >
      <template #secondaryActions>
        <button
          v-if="hasRetryable"
          type="button"
          :disabled="mutating"
          @click="retryFailed"
        >
          {{ t('maintenance.calculation.progress.retryFailed') }}
        </button>
        <button
          v-if="hasRunning"
          type="button"
          :disabled="mutating"
          @click="cancelRunning"
        >
          {{ t('maintenance.calculation.progress.cancelRunning') }}
        </button>
      </template>
      <template #primaryActions>
        <button
          v-if="canCompare"
          type="button"
          @click="compare"
        >
          {{ t('maintenance.calculation.progress.compare') }}
        </button>
      </template>
    </MaintenancePageHeader>

    <MaintenanceErrorState
      v-if="error"
      :error="error"
      :locale="locale"
      @retry="load"
    />

    <section v-if="group" class="calculation-progress__summary">
      <div>
        <span>#{{ group.id }}</span>
        <strong>{{ group.status }}</strong>
      </div>
      <dl>
        <div>
          <dt>{{ t('maintenance.calculation.list.scenarioVersion') }}</dt>
          <dd>#{{ group.scenario_version_id }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.list.primary') }}</dt>
          <dd>{{ group.primary_candidate_key }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.progress.connection') }}</dt>
          <dd>{{ connectionState }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.progress.sequence') }}</dt>
          <dd>{{ currentSequence }}</dd>
        </div>
      </dl>
    </section>

    <div v-if="loading && !group" class="calculation-progress__loading">
      {{ t('maintenance.calculation.setup.loading') }}
    </div>
    <section
      v-else-if="group?.current_children.length"
      class="calculation-progress__grid"
    >
      <CalculationTaskProgress
        v-for="child in group.current_children"
        :key="child.id"
        :child="child"
        :candidate-label="t('maintenance.calculation.fields.candidate')"
        :primary-label="t('maintenance.calculation.recommendation.primary')"
        :model-label="t('maintenance.calculation.fields.model')"
        :mode-label="t('maintenance.calculation.fields.mode')"
        :attempt-label="t('maintenance.calculation.fields.attempt')"
        :stage-label="t('maintenance.calculation.fields.stage')"
        :progress-label="t('maintenance.calculation.fields.progress')"
      />
    </section>
    <p v-else class="calculation-progress__empty">
      {{ t('maintenance.calculation.progress.noChildren') }}
    </p>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import CalculationTaskProgress from '@/components/maintenance/calculation/CalculationTaskProgress.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import { useCalculationGroupStore } from '@/stores/maintenance/calculationGroup'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useCalculationGroupStore()
const {
  group,
  loading,
  mutating,
  error,
  connectionState,
  currentSequence,
} = storeToRefs(store)
const groupId = Number(route.params.groupId)

const hasRetryable = computed(() => (
  group.value?.current_children.some(
    (child) => (
      child.calculation_status === 'FAILED'
      || child.calculation_status === 'INTERRUPTED'
    ),
  ) ?? false
))
const hasRunning = computed(() => (
  group.value?.current_children.some(
    (child) => (
      child.calculation_status === 'PENDING'
      || child.calculation_status === 'RUNNING'
    ),
  ) ?? false
))
const canCompare = computed(() => (
  group.value?.current_children.some(
    (child) => (
      child.calculation_status === 'SUCCEEDED'
      || child.calculation_status === 'PARTIAL_SUCCESS'
    ),
  ) ?? false
))

function requestKey(action: string): string {
  return `${action}:${groupId}:${globalThis.crypto?.randomUUID?.() ?? Date.now()}`
}

function load(): void {
  if (Number.isInteger(groupId) && groupId > 0) {
    void store.load(groupId)
  }
}

function retryFailed(): void {
  void store.retryFailed(requestKey('retry'))
}

function cancelRunning(): void {
  void store.cancelRunning(requestKey('cancel'))
}

function back(): void {
  void router.push({ name: 'maintenanceCalculations' })
}

function compare(): void {
  void router.push({
    name: 'maintenanceCalculationComparison',
    params: { groupId },
  })
}

onMounted(load)
onBeforeUnmount(store.dispose)
</script>

<style scoped>
.calculation-progress {
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px;
}

.calculation-progress__back,
.calculation-progress :deep(.maintenance-page-header) button {
  min-height: 36px;
  padding: 0 13px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.calculation-progress__back {
  margin-bottom: 18px;
  border: 0;
  background: transparent;
}

.calculation-progress__summary {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 20px;
  margin: 18px 0;
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-progress__summary > div span,
.calculation-progress__summary > div strong {
  display: block;
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
}

.calculation-progress__summary > div span {
  color: var(--td-text-color-placeholder);
  font-size: 11px;
}

.calculation-progress__summary > div strong {
  margin-top: 6px;
  color: var(--td-brand-color);
  font-size: 15px;
}

.calculation-progress__summary dl {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 0;
}

.calculation-progress__summary dt {
  color: var(--td-text-color-placeholder);
  font-size: 9px;
  text-transform: uppercase;
}

.calculation-progress__summary dd {
  margin: 5px 0 0;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.calculation-progress__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 14px;
}

.calculation-progress__loading,
.calculation-progress__empty {
  display: grid;
  min-height: 220px;
  place-items: center;
  color: var(--td-text-color-secondary);
}

@media (max-width: 760px) {
  .calculation-progress { padding: 22px 16px; }
  .calculation-progress__summary {
    grid-template-columns: 1fr;
  }
  .calculation-progress__summary dl {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
