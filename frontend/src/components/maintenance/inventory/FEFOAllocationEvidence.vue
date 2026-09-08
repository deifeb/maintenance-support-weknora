<template>
  <section class="fefo-evidence" aria-live="polite">
    <header>
      <h3>{{ t('maintenance.inventory.reservation.fefoEvidence.title') }}</h3>
      <p>{{ t('maintenance.inventory.reservation.fefoEvidence.description') }}</p>
    </header>

    <div class="fefo-evidence__table-wrap">
      <table>
        <thead>
          <tr>
            <th>balance_id</th>
            <th>lot_id</th>
            <th>serial_item_id</th>
            <th>reserved_quantity</th>
            <th>fefo_rank</th>
            <th>fefo_override_reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in reservation.lines" :key="line.id">
            <td>#{{ line.balance_id }}</td>
            <td>{{ idLabel(line.lot_id) }}</td>
            <td>{{ idLabel(line.serial_item_id) }}</td>
            <td>{{ line.reserved_quantity }}</td>
            <td>{{ line.fefo_rank }}</td>
            <td>{{ line.fefo_override_reason || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { InventoryReservationRead } from '@/api/maintenance/inventory'

defineProps<{
  reservation: InventoryReservationRead
}>()

const { t } = useI18n()

function idLabel(value: number | null): string {
  return value === null ? '—' : `#${value}`
}
</script>

<style scoped>
.fefo-evidence {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}
.fefo-evidence header h3 { margin: 0; font-size: 15px; }
.fefo-evidence header p { margin: 6px 0 0; color: var(--td-text-color-secondary); font-size: 12px; }
.fefo-evidence__table-wrap { margin-top: 14px; overflow-x: auto; }
.fefo-evidence table { width: 100%; border-collapse: collapse; white-space: nowrap; }
.fefo-evidence th, .fefo-evidence td { padding: 8px 10px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
</style>
