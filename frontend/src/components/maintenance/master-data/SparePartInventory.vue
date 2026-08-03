<template>
  <section
    class="spare-part-inventory"
    aria-label="备件库存"
  >
    <div class="spare-part-inventory__summary">
      <article>
        <span>账面库存</span>
        <strong>{{ formatNumber(summary.onHand) }}</strong>
      </article>
      <article>
        <span>可用库存</span>
        <strong>{{ formatNumber(summary.available) }}</strong>
      </article>
      <article>
        <span>预留库存</span>
        <strong>{{ formatNumber(summary.reserved) }}</strong>
      </article>
      <article>
        <span>损坏库存</span>
        <strong>{{ formatNumber(summary.damaged) }}</strong>
      </article>
      <article>
        <span>隔离库存</span>
        <strong>{{ formatNumber(summary.quarantined) }}</strong>
      </article>
      <article>
        <span>在途库存</span>
        <strong>{{ formatNumber(summary.inTransit) }}</strong>
      </article>
    </div>

    <p
      v-if="page.total > page.items.length"
      class="spare-part-inventory__notice"
    >
      当前显示前 {{ page.items.length }} / {{ page.total }} 条库存记录。
    </p>

    <div
      v-if="page.items.length === 0"
      class="spare-part-inventory__empty"
    >
      当前备件没有库存记录。
    </div>

    <div
      v-else
      class="spare-part-inventory__table-wrap"
    >
      <table>
        <thead>
          <tr>
            <th>仓库 ID</th>
            <th>账面</th>
            <th>可用</th>
            <th>预留</th>
            <th>损坏</th>
            <th>隔离</th>
            <th>在途</th>
            <th>补货点</th>
            <th>安全库存</th>
            <th>最后盘点</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in page.items"
            :key="row.id"
          >
            <td>{{ row.warehouse_id }}</td>
            <td>{{ formatNumber(numeric(row.on_hand_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.available_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.reserved_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.damaged_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.quarantined_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.in_transit_quantity)) }}</td>
            <td>{{ formatNumber(numeric(row.reorder_point)) }}</td>
            <td>{{ formatNumber(numeric(row.safety_stock)) }}</td>
            <td>{{ row.last_counted_at || '未盘点' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type {
  InventoryDetailRecord,
} from '@/api/maintenance/master-data-details'
import type { PageData } from '@/api/maintenance/types'
import {
  numeric,
  summarizeInventory,
} from './SparePartOverview'

const props = defineProps<{
  page: PageData<InventoryDetailRecord>
}>()

const summary = computed(
  () => summarizeInventory(props.page.items),
)

function formatNumber(value: number): string {
  return Number.isInteger(value)
    ? String(value)
    : String(Number(value.toFixed(6)))
}
</script>

<style scoped>
.spare-part-inventory {
  display: grid;
  gap: 16px;
}

.spare-part-inventory__summary {
  display: grid;
  grid-template-columns: repeat(6, minmax(120px, 1fr));
  gap: 12px;
}

.spare-part-inventory__summary article {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.spare-part-inventory__summary span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.spare-part-inventory__summary strong {
  font-size: 22px;
}

.spare-part-inventory__notice,
.spare-part-inventory__empty {
  margin: 0;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
}

.spare-part-inventory__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
}

.spare-part-inventory table {
  width: 100%;
  min-width: 980px;
  border-collapse: collapse;
}

.spare-part-inventory th,
.spare-part-inventory td {
  padding: 12px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  white-space: nowrap;
}

.spare-part-inventory th {
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .spare-part-inventory__summary {
    grid-template-columns: repeat(3, minmax(120px, 1fr));
  }
}

@media (max-width: 620px) {
  .spare-part-inventory__summary {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>
