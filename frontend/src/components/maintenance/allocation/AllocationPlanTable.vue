<template>
  <div class="allocation-plan-table-wrap">
    <table class="allocation-plan-table">
      <thead>
        <tr>
          <th>Line</th>
          <th>Part</th>
          <th>Demand</th>
          <th>Allocated</th>
          <th>Gap</th>
          <th>Recommended balance</th>
          <th>Recommended lot</th>
          <th>Recommended serial</th>
          <th>Expected balance version</th>
          <th>Risks</th>
          <th>Manual override</th>
          <th>Reservation</th>
          <th>Result</th>
          <th>Version</th>
          <th v-if="editable">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="line in lines" :key="line.id">
          <td>#{{ line.id }}</td>
          <td>#{{ line.spare_part_id }}</td>
          <td>{{ line.demand_quantity }}</td>
          <td>{{ line.allocated_quantity }}</td>
          <td>{{ line.gap_quantity }}</td>
          <td>{{ idLabel(line.recommended_balance_id) }}</td>
          <td>{{ idLabel(line.recommended_lot_id) }}</td>
          <td>{{ idLabel(line.recommended_serial_item_id) }}</td>
          <td>{{ idLabel(line.expected_balance_version) }}</td>
          <td><pre>{{ formatEvidence(line.risks) }}</pre></td>
          <td><pre>{{ formatEvidence(line.manual_override) }}</pre></td>
          <td>{{ idLabel(line.reservation_id) }}</td>
          <td><pre>{{ formatEvidence(line.result) }}</pre></td>
          <td>{{ line.version }}</td>
          <td v-if="editable">
            <button type="button" @click="emit('edit', line)">
              Edit
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type {
  AllocationPlanLineRead,
} from '@/api/maintenance/allocations'

withDefaults(defineProps<{
  lines: AllocationPlanLineRead[]
  editable?: boolean
}>(), {
  editable: false,
})

const emit = defineEmits<{
  edit: [line: AllocationPlanLineRead]
}>()

function idLabel(value: number | null): string {
  return value === null ? '—' : `#${value}`
}

function formatEvidence(value: unknown): string {
  if (value === null || value === undefined) return '—'
  return typeof value === 'string'
    ? value
    : JSON.stringify(value, null, 2)
}
</script>

<style scoped>
.allocation-plan-table-wrap {
  overflow-x: auto;
}

.allocation-plan-table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}

.allocation-plan-table th,
.allocation-plan-table td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  vertical-align: top;
  font-size: 12px;
}

.allocation-plan-table pre {
  max-width: 280px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
