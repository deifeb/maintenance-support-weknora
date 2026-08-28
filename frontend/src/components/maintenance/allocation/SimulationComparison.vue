<template>
  <section
    v-if="simulation"
    class="allocation-simulation-comparison"
    :data-status="simulation.status"
  >
    <header>
      <strong>{{ simulation.status }}</strong>
      <span v-if="simulation.progress.percent !== null">
        {{ simulation.progress.percent }}%
      </span>
      <span>{{ simulation.progress.phase }}</span>
    </header>

    <dl>
      <div>
        <dt>Total rows</dt>
        <dd>{{ simulation.results_summary.total_rows }}</dd>
      </div>
      <div>
        <dt>Demand items</dt>
        <dd>{{ simulation.results_summary.demand_item_count }}</dd>
      </div>
      <div>
        <dt>High-priority regression</dt>
        <dd>{{ simulation.results_summary.high_priority_regression }}</dd>
      </div>
      <div>
        <dt>Completed at</dt>
        <dd>{{ simulation.completed_at || '—' }}</dd>
      </div>
      <div>
        <dt>Error code</dt>
        <dd>{{ simulation.error_code || '—' }}</dd>
      </div>
      <div>
        <dt>Error summary</dt>
        <dd>{{ simulation.error_summary || '—' }}</dd>
      </div>
    </dl>

    <div v-if="simulation.blockers.length > 0">
      <strong>Blockers</strong>
      <pre>{{ formatBlockers(simulation.blockers) }}</pre>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  AllocationSimulationSummaryRead,
} from '@/api/maintenance/allocations'

defineProps<{
  simulation: AllocationSimulationSummaryRead | null
}>()

function formatBlockers(
  blockers: Record<string, unknown>[],
): string {
  return JSON.stringify(blockers, null, 2)
}
</script>
