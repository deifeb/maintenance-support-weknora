<template>
  <article class="maintenance-business-card">
    <header class="maintenance-business-card__header">
      <strong class="maintenance-business-card__title">
        {{ card.title }}
      </strong>
      <span
        v-if="card.status"
        class="maintenance-business-card__status"
      >
        {{ card.status }}
      </span>
    </header>
    <p
      v-if="card.summary"
      class="maintenance-business-card__summary"
    >
      {{ card.summary }}
    </p>
  </article>
</template>

<script setup lang="ts">
import type { MaintenanceCard } from '@/utils/maintenanceCards'

defineProps<{
  card: MaintenanceCard
}>()
</script>

<style scoped>
.maintenance-business-card {
  padding: 14px 16px;
  border: 1px solid var(--td-component-border);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.maintenance-business-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.maintenance-business-card__title {
  min-width: 0;
  font-size: 14px;
  line-height: 22px;
}

.maintenance-business-card__status {
  flex: none;
  font-size: 12px;
  color: var(--td-text-color-secondary);
}

.maintenance-business-card__summary {
  margin: 8px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 13px;
  line-height: 20px;
  white-space: pre-wrap;
}
</style>
