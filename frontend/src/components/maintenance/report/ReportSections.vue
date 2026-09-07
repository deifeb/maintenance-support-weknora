<template>
  <section class="report-sections" aria-labelledby="report-sections-title">
    <h2 id="report-sections-title">{{ t('maintenance.reports.presentation.sections') }}</h2>
    <p v-if="sections.length === 0" class="report-sections__empty">{{ t('maintenance.reports.presentation.noSections') }}</p>
    <article v-for="section in sections" :key="section.section_code"><h3>{{ section.title }}</h3><p v-if="section.content">{{ section.content }}</p><div v-for="(table, index) in publicTables(section.tables)" :key="index" class="report-sections__table"><table><thead><tr><th v-for="column in table.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in table.rows" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td></tr></tbody></table></div></article>
    <aside v-if="citations.length"><h3>{{ t('maintenance.reports.presentation.citations') }}</h3><ul><li v-for="citation in citations" :key="citation.citation_id">{{ citation.source_name || citation.citation_id }} · {{ citation.source_type }}<span v-if="citation.document_version"> · {{ t('maintenance.reports.presentation.documentVersion') }}: {{ citation.document_version }}</span><span v-if="citation.page_number != null"> · {{ t('maintenance.reports.presentation.page') }}: {{ citation.page_number }}</span><span v-if="citation.chunk_reference"> · {{ t('maintenance.reports.presentation.chunk') }}: {{ citation.chunk_reference }}</span><span v-if="citation.knowledge_node"> · {{ t('maintenance.reports.presentation.knowledgeNode') }}: {{ citation.knowledge_node }}</span></li></ul></aside>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import type { ReportCitation, ReportSection } from './report-types'
type PublicCell = string | number | boolean | null
type PublicTable = { columns: string[]; rows: PublicCell[][] }
defineProps<{ sections: ReportSection[]; citations: ReportCitation[] }>()
function publicTables(value: unknown): PublicTable[] { if (!Array.isArray(value)) return []; return value.flatMap((table) => { if (typeof table !== 'object' || table === null) return []; const item = table as Record<string, unknown>; if (!Array.isArray(item.columns) || !item.columns.every((column) => typeof column === 'string') || !Array.isArray(item.rows)) return []; const rows = item.rows.filter((row): row is PublicCell[] => Array.isArray(row) && row.every((cell) => cell === null || ['string', 'number', 'boolean'].includes(typeof cell))); return [{ columns: item.columns, rows }] }) }
</script>

<style scoped>
.report-sections { display: grid; gap: 16px; padding: 20px; border: 1px solid var(--td-component-stroke); border-radius: 10px; background: var(--td-bg-color-container); }.report-sections h2, .report-sections h3 { margin: 0; }.report-sections__empty { margin: 0; color: var(--td-text-color-secondary); }.report-sections article { display: grid; gap: 10px; }.report-sections p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }.report-sections__table { overflow-x: auto; }.report-sections table { width: 100%; border-collapse: collapse; text-align: left; }.report-sections th, .report-sections td { padding: 8px; border-bottom: 1px solid var(--td-component-stroke); }.report-sections aside ul { margin: 8px 0 0; padding-left: 20px; }
</style>
