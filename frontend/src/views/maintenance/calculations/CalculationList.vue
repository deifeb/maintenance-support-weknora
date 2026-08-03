<template>
  <main class="calculation-list">
    <MaintenancePageHeader
      :eyebrow="t('maintenance.calculation.list.eyebrow')"
      :title="t('maintenance.pages.calculations')"
      :description="t('maintenance.calculation.list.description')"
    >
      <template #secondaryActions>
        <button type="button" :disabled="loading" @click="refresh">
          {{ t('maintenance.calculation.list.refresh') }}
        </button>
      </template>
      <template #primaryActions>
        <button
          v-if="canRun"
          type="button"
          class="calculation-list__primary"
          @click="create"
        >
          {{ t('maintenance.calculation.list.new') }}
        </button>
      </template>
    </MaintenancePageHeader>

    <section class="calculation-list__toolbar">
      <label>
        <span>{{ t('maintenance.calculation.list.status') }}</span>
        <select v-model="statusFilter" :disabled="loading" @change="applyStatus">
          <option value="">
            {{ t('maintenance.calculation.list.allStatuses') }}
          </option>
          <option v-for="status in statuses" :key="status" :value="status">
            {{ status }}
          </option>
        </select>
      </label>
      <strong>{{ total }}</strong>
    </section>

    <MaintenanceErrorState
      v-if="error"
      :error="error"
      :locale="locale"
      @retry="refresh"
    />

    <div v-if="loading && groups.length === 0" class="calculation-list__loading">
      {{ t('maintenance.calculation.setup.loading') }}
    </div>
    <MaintenanceEmptyState
      v-else-if="groups.length === 0"
      :title="t('maintenance.calculation.list.emptyTitle')"
      :description="t('maintenance.calculation.list.emptyDescription')"
    />
    <div v-else class="calculation-list__table-wrap" :aria-busy="loading">
      <table>
        <thead>
          <tr>
            <th>{{ t('maintenance.calculation.list.group') }}</th>
            <th>{{ t('maintenance.calculation.list.scenarioVersion') }}</th>
            <th>{{ t('maintenance.calculation.list.primary') }}</th>
            <th>{{ t('maintenance.calculation.list.status') }}</th>
            <th>{{ t('maintenance.calculation.list.updated') }}</th>
            <th>{{ t('maintenance.calculation.list.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in groups" :key="item.id">
            <td><code>#{{ item.id }}</code></td>
            <td>#{{ item.scenario_version_id }}</td>
            <td><code>{{ item.primary_candidate_key }}</code></td>
            <td><MaintenanceStatusTag :status="item.status" /></td>
            <td>{{ formatDate(item.updated_at) }}</td>
            <td>
              <button
                type="button"
                @click="openGroup(item.id, item.status)"
              >
                {{
                  terminalWithResults.has(item.status)
                    ? t('maintenance.calculation.list.openComparison')
                    : t('maintenance.calculation.list.openProgress')
                }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="pages > 0" class="calculation-list__pagination">
      <button
        type="button"
        :disabled="page <= 1 || loading"
        @click="setPage(page - 1)"
      >
        {{ t('maintenance.calculation.actions.previous') }}
      </button>
      <span>{{ page }} / {{ pages }}</span>
      <button
        type="button"
        :disabled="page >= pages || loading"
        @click="setPage(page + 1)"
      >
        {{ t('maintenance.calculation.actions.next') }}
      </button>
    </footer>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type {
  CalculationGroupStatus,
} from '@/api/maintenance/calculation-groups'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import { useCalculationGroupStore } from '@/stores/maintenance/calculationGroup'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const statuses: CalculationGroupStatus[] = [
  'PENDING',
  'RUNNING',
  'COMPLETED',
  'PARTIALLY_COMPLETED',
  'FAILED',
  'CANCELLED',
  'INTERRUPTED',
]
const terminalWithResults = new Set<CalculationGroupStatus>([
  'COMPLETED',
  'PARTIALLY_COMPLETED',
])

const { t, locale } = useI18n()
const router = useRouter()
const calculationGroupStore = useCalculationGroupStore()
const permissionStore = useMaintenancePermissionsStore()
const {
  groups,
  total,
  page,
  pageSize,
  selectedStatus,
  loading,
  error,
} = storeToRefs(calculationGroupStore)
const statusFilter = ref(selectedStatus.value ?? '')
const pages = computed(() => (
  total.value === 0
    ? 0
    : Math.ceil(total.value / pageSize.value)
))
const canRun = computed(
  () => permissionStore.permissions.runCalculation,
)

function refresh(): void {
  void calculationGroupStore.list()
}

function applyStatus(): void {
  selectedStatus.value = (
    statusFilter.value || undefined
  ) as CalculationGroupStatus | undefined
  page.value = 1
  refresh()
}

function setPage(value: number): void {
  page.value = value
  refresh()
}

function create(): void {
  void router.push({ name: 'maintenanceCalculationNew' })
}

function openGroup(
  groupId: number,
  status: CalculationGroupStatus,
): void {
  void router.push({
    name: terminalWithResults.has(status)
      ? 'maintenanceCalculationComparison'
      : 'maintenanceCalculationProgress',
    params: { groupId },
  })
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(date)
}

onMounted(refresh)
</script>

<style scoped>
.calculation-list {
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px;
}

.calculation-list button,
.calculation-list select {
  min-height: 36px;
  padding: 0 13px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.calculation-list__primary {
  border-color: var(--td-brand-color) !important;
  background: var(--td-brand-color) !important;
  color: var(--td-text-color-anti) !important;
}

.calculation-list__toolbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-list__toolbar label {
  display: grid;
  gap: 5px;
  color: var(--td-text-color-secondary);
  font-size: 10px;
}

.calculation-list__toolbar strong {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
}

.calculation-list__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.calculation-list table {
  width: 100%;
  border-collapse: collapse;
}

.calculation-list th,
.calculation-list td {
  padding: 13px 14px;
  border-bottom: 1px solid var(--td-component-stroke);
  color: var(--td-text-color-secondary);
  font-size: 12px;
  text-align: left;
}

.calculation-list th {
  background: var(--td-bg-color-secondarycontainer);
  font-size: 10px;
  letter-spacing: .07em;
  text-transform: uppercase;
}

.calculation-list code {
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.calculation-list td button {
  min-height: 28px;
  color: var(--td-brand-color);
  font-size: 11px;
}

.calculation-list__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 18px;
}

.calculation-list__pagination span {
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.calculation-list__loading {
  display: grid;
  min-height: 240px;
  place-items: center;
  color: var(--td-text-color-secondary);
}

@media (max-width: 760px) {
  .calculation-list { padding: 22px 16px; }
}
</style>
