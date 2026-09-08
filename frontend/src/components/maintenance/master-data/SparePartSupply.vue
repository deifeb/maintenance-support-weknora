<template>
  <section
    class="spare-part-supply"
    aria-label="备件供应"
  >
    <div
      v-if="page.items.length === 0"
      class="spare-part-supply__empty"
    >
      当前备件没有供应报价记录。
    </div>

    <div
      v-else
      class="spare-part-supply__table-wrap"
    >
      <table>
        <thead>
          <tr>
            <th>报价编码</th>
            <th>供应商 ID</th>
            <th>单价</th>
            <th>交付周期（天）</th>
            <th>最小订购量</th>
            <th>订购倍数</th>
            <th>最大供应量</th>
            <th>质保（月）</th>
            <th>质量等级</th>
            <th>首选</th>
            <th>有效期开始</th>
            <th>有效期结束</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="record in page.items"
            :key="record.id"
          >
            <td>{{ record.offer_code }}</td>
            <td>{{ record.supplier_id }}</td>
            <td>{{ record.unit_price }} {{ record.currency }}</td>
            <td>{{ record.lead_time_days }}</td>
            <td>{{ record.minimum_order_quantity }}</td>
            <td>{{ record.order_multiple }}</td>
            <td>{{ display(record.maximum_supply_quantity) }}</td>
            <td>{{ display(record.warranty_months) }}</td>
            <td>{{ display(record.quality_level) }}</td>
            <td>{{ record.is_preferred ? '是' : '否' }}</td>
            <td>{{ display(record.valid_from) }}</td>
            <td>{{ display(record.valid_to) }}</td>
            <td>{{ record.is_active ? '启用' : '停用' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  SupplierOfferDetailRecord,
} from '@/api/maintenance/master-data-details'
import type { PageData } from '@/api/maintenance/types'

defineProps<{
  page: PageData<SupplierOfferDetailRecord>
}>()

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '未提供'
  }

  return String(value)
}
</script>

<style scoped>
.spare-part-supply__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
}

.spare-part-supply table {
  width: 100%;
  min-width: 1320px;
  border-collapse: collapse;
}

.spare-part-supply th,
.spare-part-supply td {
  padding: 12px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  white-space: nowrap;
}

.spare-part-supply th {
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.spare-part-supply__empty {
  padding: 24px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 8px;
  color: var(--td-text-color-secondary);
}
</style>
