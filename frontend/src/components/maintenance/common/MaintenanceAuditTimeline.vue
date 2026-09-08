<template>
  <section class="maintenance-audit-timeline">
    <div
      v-if="loading"
      class="maintenance-audit-timeline__loading"
      aria-label="loading"
    >
      <span v-for="index in 3" :key="index" />
    </div>

    <MaintenanceEmptyState
      v-else-if="entries.length === 0"
      :title="resolvedEmptyTitle"
      :description="resolvedEmptyDescription"
    />

    <ol
      v-else
      class="maintenance-audit-timeline__list"
    >
      <li
        v-for="entry in entries"
        :key="entry.id"
        class="maintenance-audit-timeline__item"
      >
        <span class="maintenance-audit-timeline__dot" />
        <article class="maintenance-audit-timeline__card">
          <div class="maintenance-audit-timeline__header">
            <div>
              <strong>{{ entry.action }}</strong>
              <span class="maintenance-audit-timeline__actor">
                {{ entry.actor }}
              </span>
            </div>
            <time :datetime="entry.timestamp">
              {{ entry.timestamp }}
            </time>
          </div>

          <dl
            v-if="entry.beforeSummary || entry.afterSummary"
            class="maintenance-audit-timeline__changes"
          >
            <div v-if="entry.beforeSummary">
              <dt>{{ beforeLabel }}</dt>
              <dd>{{ entry.beforeSummary }}</dd>
            </div>
            <div v-if="entry.afterSummary">
              <dt>{{ afterLabel }}</dt>
              <dd>{{ entry.afterSummary }}</dd>
            </div>
          </dl>
        </article>
      </li>
    </ol>

    <nav
      v-if="totalPages > 1"
      class="maintenance-audit-timeline__pagination"
      :aria-label="paginationLabel"
    >
      <t-button
        size="small"
        variant="outline"
        :disabled="page <= 1"
        @click="changePage(page - 1)"
      >
        {{ previousLabel }}
      </t-button>
      <span>
        {{ page }} / {{ totalPages }}
      </span>
      <t-button
        size="small"
        variant="outline"
        :disabled="page >= totalPages"
        @click="changePage(page + 1)"
      >
        {{ nextLabel }}
      </t-button>
    </nav>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MaintenanceEmptyState from './MaintenanceEmptyState.vue'
import { normalizeMaintenanceLocale } from './status'

interface MaintenanceAuditEntry {
  id: string | number
  actor: string
  action: string
  timestamp: string
  beforeSummary?: string
  afterSummary?: string
}

const props = withDefaults(
  defineProps<{
    entries: MaintenanceAuditEntry[]
    page?: number
    pageSize?: number
    total?: number
    loading?: boolean
    emptyTitle?: string
    emptyDescription?: string
    locale?: string
  }>(),
  {
    page: 1,
    pageSize: 10,
    total: undefined,
    loading: false,
    emptyTitle: '',
    emptyDescription: '',
    locale: 'zh-CN',
  },
)

const emit = defineEmits<{
  (event: 'page-change', page: number): void
}>()

const isChinese = computed(
  () => normalizeMaintenanceLocale(props.locale) === 'zh-CN',
)

const totalPages = computed(() => {
  const total = props.total ?? props.entries.length
  return Math.max(1, Math.ceil(total / Math.max(1, props.pageSize)))
})

const resolvedEmptyTitle = computed(
  () => props.emptyTitle || (isChinese.value ? '暂无审计记录' : 'No audit records'),
)

const resolvedEmptyDescription = computed(
  () => props.emptyDescription || (
    isChinese.value
      ? '该对象还没有可显示的变更历史'
      : 'No change history is available for this record'
  ),
)

const beforeLabel = computed(
  () => (isChinese.value ? '变更前' : 'Before'),
)

const afterLabel = computed(
  () => (isChinese.value ? '变更后' : 'After'),
)

const previousLabel = computed(
  () => (isChinese.value ? '上一页' : 'Previous'),
)

const nextLabel = computed(
  () => (isChinese.value ? '下一页' : 'Next'),
)

const paginationLabel = computed(
  () => (isChinese.value ? '审计记录分页' : 'Audit record pagination'),
)

function changePage(nextPage: number): void {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === props.page) {
    return
  }
  emit('page-change', nextPage)
}
</script>

<style scoped>
.maintenance-audit-timeline__list {
  position: relative;
  display: grid;
  gap: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.maintenance-audit-timeline__list::before {
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: 6px;
  width: 1px;
  background: var(--td-component-stroke);
  content: '';
}

.maintenance-audit-timeline__item {
  position: relative;
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 14px;
}

.maintenance-audit-timeline__dot {
  position: relative;
  z-index: 1;
  width: 12px;
  height: 12px;
  margin-top: 18px;
  border: 3px solid var(--td-bg-color-container);
  border-radius: 50%;
  background: var(--td-brand-color);
  box-shadow: 0 0 0 1px var(--td-brand-color);
}

.maintenance-audit-timeline__card {
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.maintenance-audit-timeline__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  color: var(--td-text-color-primary);
  font-size: 14px;
}

.maintenance-audit-timeline__header time {
  flex-shrink: 0;
  color: var(--td-text-color-placeholder);
  font-size: 12px;
}

.maintenance-audit-timeline__actor {
  margin-left: 8px;
  color: var(--td-text-color-secondary);
  font-weight: 400;
}

.maintenance-audit-timeline__changes {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
}

.maintenance-audit-timeline__changes div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 10px;
}

.maintenance-audit-timeline__changes dt {
  color: var(--td-text-color-placeholder);
  font-size: 12px;
}

.maintenance-audit-timeline__changes dd {
  margin: 0;
  color: var(--td-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.maintenance-audit-timeline__pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 18px;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.maintenance-audit-timeline__loading {
  display: grid;
  gap: 12px;
}

.maintenance-audit-timeline__loading span {
  display: block;
  height: 86px;
  border-radius: 8px;
  background: var(--td-bg-color-secondarycontainer);
}
</style>
