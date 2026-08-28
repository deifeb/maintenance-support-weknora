<template>
  <section
    v-if="execution"
    class="plan-execution-summary"
    :data-status="execution.status"
  >
    <header class="plan-execution-summary__header">
      <div>
        <h2>Execution #{{ execution.execution_id }}</h2>
        <p>{{ execution.execution_as_of }}</p>
      </div>
      <button
        v-if="canRegenerate"
        type="button"
        @click="emit('regenerate')"
      >
        Regenerate plan
      </button>
    </header>

    <p>
      Status: <strong>{{ execution.status }}</strong>
    </p>

    <div class="plan-execution-summary__table-wrap">
      <table>
        <thead>
          <tr>
            <th>Line</th>
            <th>Outcome</th>
            <th>Reservation</th>
            <th>Error code</th>
            <th>Cause code</th>
            <th>Retryable</th>
            <th>Suggested action</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="lineResult in execution.line_results"
            :key="lineResult.line_id"
            :data-outcome="lineResult.outcome"
          >
            <td>#{{ lineResult.line_id }}</td>
            <td>{{ lineResult.outcome }}</td>
            <td>{{ idLabel(lineResult.reservation_id) }}</td>
            <td>{{ lineResult.error_code || '—' }}</td>
            <td>{{ lineResult.cause_code || '—' }}</td>
            <td>{{ lineResult.retryable ? 'yes' : 'no' }}</td>
            <td>{{ lineResult.suggested_action || '—' }}</td>
            <td><pre>{{ formatDetails(lineResult.details) }}</pre></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  AllocationPlanExecutionResult,
} from '@/api/maintenance/allocations'

defineProps<{
  execution: AllocationPlanExecutionResult | null
  canRegenerate: boolean
}>()

const emit = defineEmits<{
  regenerate: []
}>()

function idLabel(value: number | null): string {
  return value === null ? '—' : `#${value}`
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}
</script>

<style scoped>
.plan-execution-summary {
  margin-top: 24px;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
}

.plan-execution-summary__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.plan-execution-summary__header h2,
.plan-execution-summary__header p {
  margin: 0;
}

.plan-execution-summary__table-wrap {
  margin-top: 12px;
  overflow-x: auto;
}

.plan-execution-summary table {
  width: 100%;
  border-collapse: collapse;
}

.plan-execution-summary th,
.plan-execution-summary td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  vertical-align: top;
}

.plan-execution-summary pre {
  max-width: 360px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
