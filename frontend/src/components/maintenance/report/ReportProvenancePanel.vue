<template>
  <section class="report-provenance-panel" aria-labelledby="report-provenance-title">
    <h2 id="report-provenance-title">Source provenance</h2>
    <p v-if="rows.length === 0" class="report-provenance-panel__unavailable">Source provenance is unavailable.</p>
    <table v-else>
      <thead><tr><th>Source</th><th>ID</th><th>Version</th></tr></thead>
      <tbody><tr v-for="row in rows" :key="`${row.type}-${row.id}-${row.version}`"><td>{{ row.name }}</td><td>{{ row.id }}</td><td>{{ row.version }}</td></tr></tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PublicSourceVersion } from '@/api/maintenance/reports'

const props = defineProps<{ sources: PublicSourceVersion[] | null }>()

const sourceNames: Record<PublicSourceVersion['type'], string> = {
  AI_SESSION: 'Scenario input', SCENARIO_VERSION: 'Scenario version', CALCULATION_RUN: 'Calculation run',
  CALCULATION_GROUP: 'Calculation group', DEMAND_LIST: 'Demand list', DEMAND_REVIEW: 'Demand review',
  ALLOCATION_PLAN: 'Allocation plan', INVENTORY_STOCKTAKE: 'Inventory stocktake',
}

function isPublicSource(source: unknown): source is PublicSourceVersion {
  if (typeof source !== 'object' || source === null) return false
  const value = source as Record<string, unknown>
  const allowedFields = ['type', 'id', 'version', 'lineage_id', 'digest']
  if (Object.keys(value).some((field) => !allowedFields.includes(field))) return false
  return typeof value.type === 'string' && value.type in sourceNames
    && ['string', 'number', 'boolean'].includes(typeof value.id)
    && ['string', 'number', 'boolean'].includes(typeof value.version)
}

const rows = computed(() => (Array.isArray(props.sources) && props.sources.every(isPublicSource)
  ? props.sources.map((source) => ({ type: source.type, id: source.id, version: source.version, name: sourceNames[source.type] }))
  : []))
</script>

<style scoped>
.report-provenance-panel { padding: 20px; border: 1px solid var(--td-component-stroke); border-radius: 10px; background: var(--td-bg-color-container); }.report-provenance-panel h2 { margin: 0 0 14px; font-size: 18px; }.report-provenance-panel__unavailable { margin: 0; color: var(--td-text-color-secondary); }.report-provenance-panel table { width: 100%; border-collapse: collapse; text-align: left; }.report-provenance-panel th, .report-provenance-panel td { padding: 9px; border-bottom: 1px solid var(--td-component-stroke); overflow-wrap: anywhere; }.report-provenance-panel th { color: var(--td-text-color-secondary); font-size: 12px; }
</style>
