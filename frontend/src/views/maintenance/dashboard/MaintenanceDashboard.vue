<template>
  <section class="maintenance-dashboard">
    <MaintenancePageHeader
      :title="t('maintenance.pages.dashboard')"
      :description="copy.description"
    >
      <template #secondaryActions>
        <span
          v-if="summary"
          class="maintenance-dashboard__generated-at"
        >
          {{ copy.generatedAt }}: {{ formatDate(summary.generated_at) }}
        </span>
      </template>
      <template #primaryActions>
        <t-button
          theme="primary"
          :loading="loading"
          @click="refresh"
        >
          {{ copy.refresh }}
        </t-button>
      </template>
    </MaintenancePageHeader>

    <MaintenanceErrorState
      v-if="error"
      class="maintenance-dashboard__error"
      :error="error"
      :locale="locale"
      @retry="refresh"
    />

    <section class="maintenance-dashboard__quick-actions">
      <h2>{{ copy.quickActions }}</h2>
      <div class="maintenance-dashboard__quick-action-list">
        <t-button
          v-for="action in quickActions"
          :key="action.route"
          variant="outline"
          @click="navigate(action.route)"
        >
          {{ action.label }}
        </t-button>
      </div>
    </section>

    <section class="maintenance-dashboard__metrics">
      <MaintenanceMetricCard
        v-for="metric in metricCards"
        :key="metric.key"
        :label="metric.label"
        :value="metric.value"
        :trend="metric.trend"
        :loading="loading && !summary"
        clickable
        @click="navigate(metric.route)"
      />
    </section>

    <div class="maintenance-dashboard__content-grid">
      <article class="maintenance-dashboard__panel">
        <div class="maintenance-dashboard__panel-header">
          <h2>{{ copy.recentTasks }}</h2>
          <span>{{ recentTasks.length }}/10</span>
        </div>

        <MaintenanceEmptyState
          v-if="!loading && recentTasks.length === 0"
          :title="copy.noRecentTasks"
          :description="copy.noRecentTasksDescription"
        />

        <div
          v-else
          class="maintenance-dashboard__list"
        >
          <button
            v-for="task in recentTasks"
            :key="`${task.task_type}:${task.task_id}`"
            type="button"
            class="maintenance-dashboard__list-item"
            @click="openTask(task)"
          >
            <span class="maintenance-dashboard__list-main">
              <strong>{{ task.title }}</strong>
              <small>
                {{ taskTypeLabel(task.task_type) }}
                · {{ formatDate(task.updated_at) }}
              </small>
            </span>
            <span class="maintenance-dashboard__list-side">
              <span v-if="task.progress !== null && task.progress !== undefined">
                {{ formatProgress(task.progress) }}
              </span>
              <MaintenanceStatusTag
                :status="task.status"
                :locale="locale"
              />
            </span>
          </button>
        </div>
      </article>

      <article class="maintenance-dashboard__panel">
        <div class="maintenance-dashboard__panel-header">
          <h2>{{ copy.riskRanking }}</h2>
          <span>{{ riskItems.length }}/10</span>
        </div>

        <MaintenanceEmptyState
          v-if="!loading && riskItems.length === 0"
          :title="copy.noRiskItems"
          :description="copy.noRiskItemsDescription"
        />

        <div
          v-else
          class="maintenance-dashboard__list"
        >
          <button
            v-for="item in riskItems"
            :key="item.key"
            type="button"
            class="maintenance-dashboard__list-item"
            @click="openRisk(item)"
          >
            <span class="maintenance-dashboard__list-main">
              <strong>{{ item.title }}</strong>
              <small>
                {{ riskTypeLabel(item.risk_type) }}
                <template v-if="item.detail"> · {{ item.detail }}</template>
              </small>
            </span>
            <span class="maintenance-dashboard__list-side">
              <span v-if="item.value !== null && item.value !== undefined">
                {{ item.value }}
              </span>
              <MaintenanceRiskTag
                :risk="item.severity"
                :locale="locale"
              />
            </span>
          </button>
        </div>
      </article>

      <article class="maintenance-dashboard__panel maintenance-dashboard__panel--distribution">
        <div class="maintenance-dashboard__panel-header">
          <h2>{{ copy.riskDistribution }}</h2>
          <span>{{ riskTotal }}</span>
        </div>

        <div class="maintenance-dashboard__distribution">
          <div
            v-for="entry in riskDistribution"
            :key="entry.level"
            class="maintenance-dashboard__distribution-row"
          >
            <div class="maintenance-dashboard__distribution-label">
              <MaintenanceRiskTag
                :risk="entry.level"
                :locale="locale"
              />
              <strong>{{ entry.count }}</strong>
            </div>
            <div class="maintenance-dashboard__distribution-track">
              <span :style="{ width: `${entry.percentage}%` }" />
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type {
  DashboardRiskLevel,
  DashboardScalar,
  RecentTask,
  RiskItem,
} from '@/api/maintenance/dashboard'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenanceMetricCard from '@/components/maintenance/common/MaintenanceMetricCard.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceRiskTag from '@/components/maintenance/common/MaintenanceRiskTag.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import { usePageVisibilityPolling } from '@/composables/maintenance/usePageVisibilityPolling'
import { useMaintenanceDashboardStore } from '@/stores/maintenance/dashboard'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const dashboardStore = useMaintenanceDashboardStore()
const { summary, loading, error } = storeToRefs(dashboardStore)
const { refresh } = dashboardStore

const isChinese = computed(
  () => locale.value.toLowerCase().startsWith('zh'),
)

const copy = computed(() => (
  isChinese.value
    ? {
        description: '当前租户的维修保障指标、任务进度与风险概览。',
        refresh: '刷新',
        generatedAt: '生成时间',
        quickActions: '快捷操作',
        recentTasks: '最近任务',
        riskRanking: '风险排行',
        riskDistribution: '风险分布',
        noRecentTasks: '暂无最近任务',
        noRecentTasksDescription: '场景、推算、审查和报告任务将在此显示。',
        noRiskItems: '暂无风险事项',
        noRiskItemsDescription: '当前租户没有需要优先处理的缺口或审查发现。',
      }
    : {
        description: 'Current-tenant maintenance metrics, task progress, and operational risks.',
        refresh: 'Refresh',
        generatedAt: 'Generated',
        quickActions: 'Quick actions',
        recentTasks: 'Recent tasks',
        riskRanking: 'Risk ranking',
        riskDistribution: 'Risk distribution',
        noRecentTasks: 'No recent tasks',
        noRecentTasksDescription: 'Scenario, calculation, review, and report tasks will appear here.',
        noRiskItems: 'No risk items',
        noRiskItemsDescription: 'This tenant has no urgent gaps or review findings.',
      }
))

const metricDefinitions = [
  {
    key: 'active_equipment_count',
    zh: '启用装备',
    en: 'Active equipment',
    route: '/platform/maintenance/master-data',
  },
  {
    key: 'active_spare_part_count',
    zh: '启用器材',
    en: 'Active spare parts',
    route: '/platform/maintenance/master-data',
  },
  {
    key: 'inventory_risk_count',
    zh: '库存风险器材',
    en: 'Inventory risks',
    route: '/platform/maintenance/inventory-gap',
  },
  {
    key: 'pending_scenario_count',
    zh: '待确认场景',
    en: 'Pending scenarios',
    route: '/platform/maintenance/scenarios',
  },
  {
    key: 'running_calculation_count',
    zh: '运行中推算',
    en: 'Running calculations',
    route: '/platform/maintenance/calculations',
  },
  {
    key: 'failed_calculation_count',
    zh: '失败推算',
    en: 'Failed calculations',
    route: '/platform/maintenance/calculations',
  },
  {
    key: 'high_risk_finding_count',
    zh: '高风险发现',
    en: 'High-risk findings',
    route: '/platform/maintenance/reviews',
  },
  {
    key: 'demand_gap_count',
    zh: '需求缺口器材',
    en: 'Demand gaps',
    route: '/platform/maintenance/inventory-gap',
  },
] as const

const quickActions = computed(() => [
  {
    label: isChinese.value ? '任务场景' : 'Scenarios',
    route: '/platform/maintenance/scenarios',
  },
  {
    label: isChinese.value ? '开始推算' : 'Calculations',
    route: '/platform/maintenance/calculations',
  },
  {
    label: isChinese.value ? '查看缺口' : 'Inventory gaps',
    route: '/platform/maintenance/inventory-gap',
  },
  {
    label: isChinese.value ? '报告中心' : 'Reports',
    route: '/platform/maintenance/reports',
  },
])

const metricCards = computed(() => metricDefinitions.map((definition) => {
  const metric = summary.value?.metrics.find(
    (item) => item.key === definition.key,
  )
  const numericTrend = metric?.trend === null || metric?.trend === undefined
    ? undefined
    : Number(metric.trend)

  return {
    key: definition.key,
    label: isChinese.value ? definition.zh : definition.en,
    value: metric?.value ?? 0,
    trend: Number.isFinite(numericTrend) ? numericTrend : undefined,
    route: definition.route,
  }
}))

const recentTasks = computed(
  () => summary.value?.recent_tasks ?? [],
)
const riskItems = computed(
  () => summary.value?.risk_items ?? [],
)

const riskLevels: DashboardRiskLevel[] = [
  'BLOCKING',
  'HIGH',
  'MEDIUM',
  'LOW',
]

const riskTotal = computed(() => riskLevels.reduce(
  (total, level) => (
    total + (summary.value?.risk_distribution[level] ?? 0)
  ),
  0,
))

const riskDistribution = computed(() => {
  const maximum = Math.max(
    1,
    ...riskLevels.map(
      (level) => summary.value?.risk_distribution[level] ?? 0,
    ),
  )

  return riskLevels.map((level) => {
    const count = summary.value?.risk_distribution[level] ?? 0
    return {
      level,
      count,
      percentage: Math.round((count / maximum) * 100),
    }
  })
})

const taskFallbackRoutes: Record<string, string> = {
  SCENARIO: '/platform/maintenance/scenarios',
  CALCULATION: '/platform/maintenance/calculations',
  REVIEW: '/platform/maintenance/reviews',
  REPORT: '/platform/maintenance/reports',
}

function navigate(target: string, fallback?: string): void {
  const resolved = router.resolve(target)
  const destination = resolved.matched.length > 0
    ? target
    : (fallback ?? target)
  void router.push(destination)
}

function openTask(task: RecentTask): void {
  navigate(
    task.route,
    taskFallbackRoutes[task.task_type]
      ?? '/platform/maintenance/dashboard',
  )
}

function openRisk(item: RiskItem): void {
  navigate(
    item.route,
    item.risk_type === 'REVIEW_FINDING'
      ? '/platform/maintenance/reviews'
      : '/platform/maintenance/inventory-gap',
  )
}

function taskTypeLabel(taskType: string): string {
  const labels: Record<string, [string, string]> = {
    SCENARIO: ['场景', 'Scenario'],
    CALCULATION: ['推算', 'Calculation'],
    REVIEW: ['审查', 'Review'],
    REPORT: ['报告', 'Report'],
  }
  const label = labels[taskType] ?? [taskType, taskType]
  return isChinese.value ? label[0] : label[1]
}

function riskTypeLabel(riskType: string): string {
  if (riskType === 'REVIEW_FINDING') {
    return isChinese.value ? '审查发现' : 'Review finding'
  }
  if (riskType === 'INVENTORY_GAP') {
    return isChinese.value ? '库存缺口' : 'Inventory gap'
  }
  return riskType
}

function formatProgress(value: DashboardScalar): string {
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? `${Math.round(numeric)}%`
    : String(value)
}

function formatDate(value: string): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat(
    isChinese.value ? 'zh-CN' : 'en-US',
    {
      dateStyle: 'medium',
      timeStyle: 'short',
    },
  ).format(date)
}

usePageVisibilityPolling({
  intervalMs: 30_000,
  run: refresh,
  isActive: () => route.path.startsWith('/platform/maintenance'),
})
</script>

<style scoped>
.maintenance-dashboard {
  max-width: 1440px;
  margin: 0 auto;
  padding: 32px;
}

.maintenance-dashboard__generated-at {
  align-self: center;
  color: var(--td-text-color-placeholder);
  font-size: 12px;
  white-space: nowrap;
}

.maintenance-dashboard__error {
  margin-bottom: 20px;
}

.maintenance-dashboard__quick-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px 20px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.maintenance-dashboard__quick-actions h2,
.maintenance-dashboard__panel h2 {
  margin: 0;
  color: var(--td-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.maintenance-dashboard__quick-action-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.maintenance-dashboard__metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.maintenance-dashboard__content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.maintenance-dashboard__panel {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
  box-shadow: var(--td-shadow-1);
}

.maintenance-dashboard__panel--distribution {
  grid-column: 1 / -1;
}

.maintenance-dashboard__panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.maintenance-dashboard__panel-header > span {
  color: var(--td-text-color-placeholder);
  font-size: 12px;
}

.maintenance-dashboard__list {
  display: grid;
  gap: 8px;
}

.maintenance-dashboard__list-item {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--td-bg-color-secondarycontainer);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.maintenance-dashboard__list-item:hover,
.maintenance-dashboard__list-item:focus-visible {
  border-color: var(--td-brand-color);
  outline: none;
}

.maintenance-dashboard__list-main {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.maintenance-dashboard__list-main strong {
  overflow: hidden;
  color: var(--td-text-color-primary);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.maintenance-dashboard__list-main small {
  overflow: hidden;
  color: var(--td-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.maintenance-dashboard__list-side {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.maintenance-dashboard__distribution {
  display: grid;
  gap: 14px;
}

.maintenance-dashboard__distribution-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  align-items: center;
  gap: 16px;
}

.maintenance-dashboard__distribution-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.maintenance-dashboard__distribution-track {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--td-bg-color-secondarycontainer);
}

.maintenance-dashboard__distribution-track span {
  display: block;
  min-width: 2px;
  height: 100%;
  border-radius: inherit;
  background: var(--td-brand-color);
  transition: width 0.2s ease;
}

@media (max-width: 1100px) {
  .maintenance-dashboard__metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .maintenance-dashboard {
    padding: 24px 16px;
  }

  .maintenance-dashboard__quick-actions,
  .maintenance-dashboard__list-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .maintenance-dashboard__metrics,
  .maintenance-dashboard__content-grid {
    grid-template-columns: 1fr;
  }

  .maintenance-dashboard__panel--distribution {
    grid-column: auto;
  }

  .maintenance-dashboard__distribution-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }
}
</style>
