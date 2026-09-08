<template>
  <details class="scenario-records">
    <summary>
      <span>{{ title }}</span>
      <strong>{{ records.length }}</strong>
    </summary>
    <div
      v-if="records.length > 0"
      class="scenario-records__grid"
    >
      <article
        v-for="(record, index) in records"
        :key="String(record.id ?? index)"
      >
        <header>
          <code>
            {{ record[codeKey] ?? `#${index + 1}` }}
          </code>
          <strong>
            {{ record[nameKey] ?? '—' }}
          </strong>
        </header>
        <pre>{{ JSON.stringify(record, null, 2) }}</pre>
      </article>
    </div>
    <p v-else>—</p>
  </details>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  records: Array<Record<string, unknown>>
  codeKey: string
  nameKey: string
}>()
</script>

<style scoped>
.scenario-records {
  border: 1px solid var(--td-component-stroke);
  border-radius: 7px;
  background: var(--td-bg-color-container);
}

.scenario-records summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 15px;
  cursor: pointer;
}

.scenario-records summary span {
  font-size: 13px;
  font-weight: 650;
}

.scenario-records summary strong {
  color: var(--td-text-color-placeholder);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-records__grid {
  display: grid;
  gap: 8px;
  padding: 0 12px 12px;
}

.scenario-records article {
  overflow: hidden;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
}

.scenario-records article header {
  display: flex;
  gap: 10px;
  padding: 9px 11px;
  background: var(--td-bg-color-secondarycontainer);
}

.scenario-records code {
  color: var(--td-brand-color);
}

.scenario-records pre {
  max-height: 220px;
  margin: 0;
  padding: 11px;
  overflow: auto;
  color: var(--td-text-color-secondary);
  font-size: 10px;
  line-height: 1.55;
}

.scenario-records > p {
  margin: 0;
  padding: 0 15px 13px;
  color: var(--td-text-color-placeholder);
}
</style>
