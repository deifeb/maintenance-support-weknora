<template>
  <div class="master-data-table-wrap">
    <table class="master-data-table">
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            :style="column.width ? { width: `${column.width}px` } : undefined"
            scope="col"
          >
            <button
              v-if="column.sortable"
              type="button"
              class="master-data-table__sort"
              @click="$emit('sort', column.key)"
            >
              <span>{{ column.title }}</span>
              <span
                v-if="sortBy === column.key"
                aria-hidden="true"
              >
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </button>
            <span v-else>{{ column.title }}</span>
          </th>
          <th class="master-data-table__actions-heading" scope="col">
            操作
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, index) in rows"
          :key="rowIdentity(row, index)"
        >
          <td
            v-for="column in columns"
            :key="column.key"
          >
            <MaintenanceStatusTag
              v-if="column.formatter === 'status' && cellValue(row, column.key)"
              :status="String(cellValue(row, column.key))"
            />
            <span
              v-else-if="column.formatter === 'boolean'"
              class="master-data-table__boolean"
              :class="{
                'master-data-table__boolean--true': Boolean(cellValue(row, column.key)),
              }"
            >
              {{ Boolean(cellValue(row, column.key)) ? '是' : '否' }}
            </span>
            <span v-else>
              {{ formatCell(row, column) }}
            </span>
          </td>
          <td class="master-data-table__actions">
            <button
              v-for="action in actionsForRow(row)"
              :key="action.key"
              type="button"
              class="master-data-table__action"
              :class="{
                'master-data-table__action--danger': action.kind === 'deactivate',
              }"
              @click="$emit('action', action, row)"
            >
              {{ action.label }}
            </button>
          </td>
        </tr>
        <tr v-if="loading && rows.length === 0">
          <td
            :colspan="columns.length + 1"
            class="master-data-table__loading"
          >
            正在加载主数据…
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import type {
  MasterDataColumn,
  MasterDataRecord,
  MasterDataRowAction,
  MasterDataSortOrder,
} from './MasterDataRegistry'

const props = withDefaults(
  defineProps<{
    rows: MasterDataRecord[]
    columns: MasterDataColumn[]
    rowKey: string
    loading?: boolean
    sortBy?: string
    sortOrder?: MasterDataSortOrder
    actionsForRow: (row: MasterDataRecord) => MasterDataRowAction[]
  }>(),
  {
    loading: false,
    sortBy: '',
    sortOrder: 'asc',
  },
)

defineEmits<{
  (event: 'sort', column: string): void
  (event: 'action', action: MasterDataRowAction, row: MasterDataRecord): void
}>()

function rowIdentity(
  row: MasterDataRecord,
  index: number,
): string | number {
  const value = row[props.rowKey]
  return typeof value === 'string' || typeof value === 'number'
    ? value
    : index
}

function cellValue(
  row: MasterDataRecord,
  key: string,
): unknown {
  return row[key]
}

function formatCell(
  row: MasterDataRecord,
  column: MasterDataColumn,
): string {
  const value = cellValue(row, column.key)

  if (value === null || value === undefined || value === '') {
    return '—'
  }

  if (column.formatter === 'date' || column.formatter === 'datetime') {
    const date = new Date(String(value))
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat(
        'zh-CN',
        column.formatter === 'datetime'
          ? { dateStyle: 'medium', timeStyle: 'short' }
          : { dateStyle: 'medium' },
      ).format(date)
    }
  }

  if (column.formatter === 'number') {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      return new Intl.NumberFormat('zh-CN', {
        maximumFractionDigits: 6,
      }).format(numeric)
    }
  }

  if (column.formatter === 'currency') {
    const numeric = Number(value)
    const currency = typeof row.currency === 'string' ? row.currency : 'CNY'
    if (Number.isFinite(numeric)) {
      return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency,
      }).format(numeric)
    }
  }

  if (column.formatter === 'json' || typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}
</script>

<style scoped>
.master-data-table-wrap {
  width: 100%;
  overflow: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.master-data-table {
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;
  color: var(--td-text-color-primary);
  font-size: 13px;
}

.master-data-table th,
.master-data-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  vertical-align: middle;
}

.master-data-table th {
  position: sticky;
  z-index: 1;
  top: 0;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-weight: 600;
  white-space: nowrap;
}

.master-data-table tbody tr:last-child td {
  border-bottom: 0;
}

.master-data-table tbody tr:hover {
  background: var(--td-bg-color-container-hover);
}

.master-data-table__sort {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.master-data-table__actions-heading,
.master-data-table__actions {
  position: sticky;
  right: 0;
  min-width: 150px;
  background: var(--td-bg-color-container);
}

.master-data-table__actions-heading {
  background: var(--td-bg-color-secondarycontainer);
}

.master-data-table__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.master-data-table__action {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.master-data-table__action--danger {
  color: var(--td-warning-color);
}

.master-data-table__boolean {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-placeholder);
  font-size: 12px;
}

.master-data-table__boolean--true {
  background: var(--td-success-color-1);
  color: var(--td-success-color);
}

.master-data-table__loading {
  padding: 36px !important;
  color: var(--td-text-color-secondary);
  text-align: center !important;
}
</style>
