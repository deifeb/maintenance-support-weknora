<template>
  <section class="maintenance-empty-state">
    <div class="maintenance-empty-state__icon" aria-hidden="true">
      <slot name="icon">
        <span>—</span>
      </slot>
    </div>
    <h3 class="maintenance-empty-state__title">
      {{ title }}
    </h3>
    <p
      v-if="description"
      class="maintenance-empty-state__description"
    >
      {{ description }}
    </p>
    <div
      v-if="$slots.actions || actionLabel"
      class="maintenance-empty-state__actions"
    >
      <slot name="actions">
        <t-button
          theme="primary"
          variant="outline"
          @click="$emit('action')"
        >
          {{ actionLabel }}
        </t-button>
      </slot>
    </div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    actionLabel?: string
  }>(),
  {
    description: '',
    actionLabel: '',
  },
)

defineEmits<{
  (event: 'action'): void
}>()
</script>

<style scoped>
.maintenance-empty-state {
  display: flex;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px 24px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
  text-align: center;
}

.maintenance-empty-state__icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 50%;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-placeholder);
  font-size: 24px;
}

.maintenance-empty-state__title {
  margin: 16px 0 0;
  color: var(--td-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.maintenance-empty-state__description {
  max-width: 520px;
  margin: 8px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.maintenance-empty-state__actions {
  margin-top: 18px;
}
</style>
