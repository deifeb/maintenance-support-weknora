<template>
  <div class="inventory-balance-table" :aria-busy="props.loading">
    <table>
      <thead>
        <tr>
          <th>{{ t('maintenance.inventory.columns.id') }}</th>
          <th>{{ t('maintenance.inventory.columns.warehouse') }}</th>
          <th>{{ t('maintenance.inventory.columns.location') }}</th>
          <th>{{ t('maintenance.inventory.columns.part') }}</th>
          <th>{{ t('maintenance.inventory.columns.lot') }}</th>
          <th>{{ t('maintenance.inventory.columns.serial') }}</th>
          <th>{{ t('maintenance.inventory.columns.onHand') }}</th>
          <th>{{ t('maintenance.inventory.columns.reserved') }}</th>
          <th>{{ t('maintenance.inventory.columns.damaged') }}</th>
          <th>{{ t('maintenance.inventory.columns.quarantined') }}</th>
          <th>{{ t('maintenance.inventory.columns.inTransit') }}</th>
          <th>{{ t('maintenance.inventory.columns.available') }}</th>
          <th>{{ t('maintenance.inventory.columns.version') }}</th>
          <th>{{ t('maintenance.inventory.columns.actions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in props.items" :key="item.id">
          <td>#{{ item.id }}</td>
          <td>#{{ item.warehouse_id }}</td>
          <td>#{{ item.location_id }}</td>
          <td>#{{ item.spare_part_id }}</td>
          <td>{{ displayId(item.lot_id) }}</td>
          <td>{{ displaySerials(item) }}</td>
          <td>{{ item.on_hand_quantity }}</td>
          <td>{{ item.reserved_quantity }}</td>
          <td>{{ item.damaged_quantity }}</td>
          <td>{{ item.quarantined_quantity }}</td>
          <td>{{ item.in_transit_quantity }}</td>
          <td>{{ item.available_quantity }}</td>
          <td>{{ item.version }}</td>
          <td>
            <button type="button" @click="emit('open', item.id)">
              {{ t('maintenance.inventory.columns.open') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  InventoryBalanceRead,
} from '@/api/maintenance/inventory'

const props = defineProps<{
  items: InventoryBalanceRead[]
  loading: boolean
}>()

const emit = defineEmits<{
  open: [balanceId: number]
}>()

const { t } = useI18n()

function displayId(value: number | null): string {
  return value === null ? '—' : `#${value}`
}

function displaySerials(item: InventoryBalanceRead): string {
  if (item.serial_item_id !== null) {
    return `#${item.serial_item_id}`
  }
  if (item.serial_item_ids.length === 0) {
    return '—'
  }
  return item.serial_item_ids.map((value) => `#${value}`).join(', ')
}

</script>

<style scoped>
.inventory-balance-table {
  overflow-x: auto;
}

.inventory-balance-table table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}

.inventory-balance-table th,
.inventory-balance-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  font-size: 12px;
}

.inventory-balance-table th {
  color: var(--td-text-color-secondary);
  font-weight: 600;
}

.inventory-balance-table button {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  cursor: pointer;
}
</style>
