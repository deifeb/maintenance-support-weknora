<template>
  <section class="report-version-timeline" aria-labelledby="report-version-title">
    <h2 id="report-version-title">{{ t('maintenance.reports.presentation.timeline') }}</h2>
    <p v-if="versions.length === 0" class="report-version-timeline__empty">{{ t('maintenance.reports.presentation.noVersions') }}</p>
    <ol v-else><li v-for="version in versions" :key="version.id"><strong>{{ t('maintenance.reports.presentation.version') }} {{ version.version_number }} · {{ t(`maintenance.reports.versionStatuses.${version.status}`) }}</strong><dl><div><dt>{{ t('maintenance.reports.presentation.parentVersion') }}</dt><dd>{{ version.parent_version_id ?? t('maintenance.reports.presentation.none') }}</dd></div><div><dt>{{ t('maintenance.reports.presentation.template') }}</dt><dd>{{ version.template_version }}</dd></div><div><dt>{{ t('maintenance.reports.presentation.generationMode') }}</dt><dd>{{ version.generation_mode ?? t('maintenance.reports.presentation.unavailable') }}</dd></div><div><dt>{{ t('maintenance.reports.presentation.generated') }}</dt><dd>{{ version.generated_at ?? t('maintenance.reports.presentation.unavailable') }}</dd></div><div><dt>{{ t('maintenance.reports.presentation.contentDigest') }}</dt><dd>{{ version.content_digest }}</dd></div></dl></li></ol>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import type { ReportVersionSummary } from '@/api/maintenance/reports'
defineProps<{ versions: ReportVersionSummary[] }>()
</script>

<style scoped>
.report-version-timeline { padding: 20px; border: 1px solid var(--td-component-stroke); border-radius: 10px; background: var(--td-bg-color-container); }.report-version-timeline h2 { margin: 0 0 14px; font-size: 18px; }.report-version-timeline__empty { margin: 0; color: var(--td-text-color-secondary); }.report-version-timeline ol { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; }.report-version-timeline li { padding: 14px; border-left: 3px solid var(--td-brand-color); background: var(--td-bg-color-secondarycontainer); }.report-version-timeline dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 12px 0 0; }.report-version-timeline dt { color: var(--td-text-color-secondary); font-size: 12px; }.report-version-timeline dd { margin: 3px 0 0; overflow-wrap: anywhere; }
</style>
