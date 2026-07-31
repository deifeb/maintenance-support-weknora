<template>
  <main class="calculation-comparison">
    <button
      type="button"
      class="calculation-comparison__back"
      @click="back"
    >
      ← {{ t('maintenance.calculation.comparison.back') }}
    </button>

    <MaintenancePageHeader
      :eyebrow="t('maintenance.calculation.comparison.eyebrow')"
      :title="t('maintenance.calculation.comparison.title')"
      :description="t('maintenance.calculation.comparison.description')"
    />

    <MaintenanceErrorState
      v-if="error"
      :error="error"
      :locale="locale"
      @retry="load"
    />

    <section
      v-if="comparison"
      class="calculation-comparison__summary"
    >
      <div>
        <span>#{{ comparison.group_id }}</span>
        <strong>{{ comparison.group_status }}</strong>
      </div>
      <dl>
        <div>
          <dt>{{ t('maintenance.calculation.list.primary') }}</dt>
          <dd>{{ comparison.primary_candidate_key }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.fields.candidate') }}</dt>
          <dd>{{ comparison.candidate_keys.length }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.comparison.risk') }}</dt>
          <dd>{{ comparison.risk_rule_version }}</dd>
        </div>
      </dl>
    </section>

    <div
      v-if="loading && !comparison"
      class="calculation-comparison__loading"
    >
      {{ t('maintenance.calculation.setup.loading') }}
    </div>
    <ModelComparisonTable
      v-else-if="comparison?.rows.length"
      :comparison="comparison"
      :editable="canDecide"
      @edit="openDecision"
    />
    <MaintenanceEmptyState
      v-else
      :title="t('maintenance.calculation.comparison.empty')"
      :description="t('maintenance.calculation.comparison.description')"
    />

    <DemandItemDecisionDrawer
      :open="selectedRow !== null"
      :row="selectedRow"
      :saving="mutating"
      @close="selectedRow = null"
      @save="saveDecision"
    />
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import type {
  CalculationComparisonRow,
  CalculationDecisionSaveRequest,
} from '@/api/maintenance/calculation-groups'
import DemandItemDecisionDrawer from '@/components/maintenance/calculation/DemandItemDecisionDrawer.vue'
import ModelComparisonTable from '@/components/maintenance/calculation/ModelComparisonTable.vue'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import { useCalculationGroupStore } from '@/stores/maintenance/calculationGroup'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useCalculationGroupStore()
const permissionStore = useMaintenancePermissionsStore()
const {
  comparison,
  loading,
  mutating,
  error,
} = storeToRefs(store)
const groupId = Number(route.params.groupId)
const selectedRow = ref<CalculationComparisonRow | null>(null)
const canDecide = computed(
  () => permissionStore.permissions.runCalculation,
)

function load(): void {
  if (Number.isInteger(groupId) && groupId > 0) {
    void store.loadComparison(groupId)
  }
}

function back(): void {
  void router.push({
    name: 'maintenanceCalculationProgress',
    params: { groupId },
  })
}

function openDecision(row: CalculationComparisonRow): void {
  selectedRow.value = row
}

async function saveDecision(
  sparePartId: number,
  request: CalculationDecisionSaveRequest,
): Promise<void> {
  try {
    await store.saveDecision(sparePartId, request)
    selectedRow.value = (
      comparison.value?.rows.find(
        (row) => row.spare_part_id === sparePartId,
      ) ?? null
    )
  } catch {
    // The shared store exposes the normalized error state.
  }
}

onMounted(load)
onBeforeUnmount(store.dispose)
</script>

<style scoped>
.calculation-comparison {
  max-width: 1480px;
  margin: 0 auto;
  padding: 32px;
}

.calculation-comparison__back {
  min-height: 36px;
  margin-bottom: 18px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.calculation-comparison__summary {
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 22px;
  margin: 18px 0;
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-comparison__summary > div span,
.calculation-comparison__summary > div strong {
  display: block;
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
}

.calculation-comparison__summary > div span {
  color: var(--td-text-color-placeholder);
  font-size: 11px;
}

.calculation-comparison__summary > div strong {
  margin-top: 5px;
  color: var(--td-success-color);
}

.calculation-comparison__summary dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 0;
}

.calculation-comparison__summary dt {
  color: var(--td-text-color-placeholder);
  font-size: 9px;
  text-transform: uppercase;
}

.calculation-comparison__summary dd {
  margin: 5px 0 0;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.calculation-comparison__loading {
  display: grid;
  min-height: 240px;
  place-items: center;
  color: var(--td-text-color-secondary);
}

@media (max-width: 760px) {
  .calculation-comparison { padding: 22px 16px; }
  .calculation-comparison__summary {
    grid-template-columns: 1fr;
  }
  .calculation-comparison__summary dl {
    grid-template-columns: 1fr;
  }
}
</style>
