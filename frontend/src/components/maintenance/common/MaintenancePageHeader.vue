<template>
  <header class="maintenance-page-header">
    <div class="maintenance-page-header__content">
      <div class="maintenance-page-header__title-row">
        <h1 class="maintenance-page-header__title">
          {{ title }}
        </h1>
        <MaintenanceStatusTag
          v-if="status"
          :status="status"
          :locale="locale"
        />
        <span
          v-if="version !== undefined && version !== null && version !== ''"
          class="maintenance-page-header__version"
        >
          v{{ version }}
        </span>
      </div>
      <p
        v-if="description"
        class="maintenance-page-header__description"
      >
        {{ description }}
      </p>
    </div>

    <div
      v-if="
        $slots.secondaryActions
        || $slots.actions
        || $slots.primaryActions
      "
      class="maintenance-page-header__actions"
    >
      <slot name="secondaryActions" />
      <slot name="actions" />
      <slot name="primaryActions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import MaintenanceStatusTag from './MaintenanceStatusTag.vue'

withDefaults(
  defineProps<{
    title: string
    description?: string
    status?: string
    version?: string | number
    locale?: string
  }>(),
  {
    description: '',
    status: '',
    version: undefined,
    locale: 'zh-CN',
  },
)
</script>

<style scoped>
.maintenance-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.maintenance-page-header__content {
  min-width: 0;
}

.maintenance-page-header__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.maintenance-page-header__title {
  margin: 0;
  color: var(--td-text-color-primary);
  font-size: 28px;
  font-weight: 600;
  line-height: 1.3;
}

.maintenance-page-header__version {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 999px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
  line-height: 20px;
}

.maintenance-page-header__description {
  max-width: 760px;
  margin: 8px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.maintenance-page-header__actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
}

@media (max-width: 720px) {
  .maintenance-page-header {
    flex-direction: column;
  }

  .maintenance-page-header__actions {
    width: 100%;
  }
}
</style>
