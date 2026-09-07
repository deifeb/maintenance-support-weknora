<template>
  <section class="report-validation-findings" aria-labelledby="report-findings-title">
    <h2 id="report-findings-title">Validation findings</h2>
    <p v-if="findings.length === 0" class="report-validation-findings__empty">No validation findings.</p>
    <ul v-else><li v-for="finding in findings" :key="finding.id"><strong>{{ finding.severity }} · {{ finding.code }}</strong><p>{{ finding.message }}</p></li></ul>
  </section>
</template>

<script setup lang="ts">
import type { ReportValidationFinding } from './report-types'
defineProps<{ findings: ReportValidationFinding[] }>()
</script>

<style scoped>
.report-validation-findings { padding: 20px; border: 1px solid var(--td-component-stroke); border-radius: 10px; background: var(--td-bg-color-container); }.report-validation-findings h2 { margin: 0 0 14px; font-size: 18px; }.report-validation-findings__empty { margin: 0; color: var(--td-text-color-secondary); }.report-validation-findings ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }.report-validation-findings li { padding: 12px; border-left: 3px solid var(--td-warning-color); background: var(--td-bg-color-secondarycontainer); }.report-validation-findings p { margin: 7px 0 0; overflow-wrap: anywhere; }
</style>
