<template>
  <div class="inventory-list-toolbar">
    <label>
      <span>{{ t('maintenance.inventory.sort.label') }}</span>
      <select
        :value="sortBy"
        :disabled="loading"
        @change="changeSortBy"
      >
        <slot />
      </select>
    </label>

    <label>
      <span>{{ t('maintenance.inventory.sort.order') }}</span>
      <select
        :value="sortOrder"
        :disabled="loading"
        @change="changeSortOrder"
      >
        <option value="asc">
          {{ t('maintenance.inventory.sort.asc') }}
        </option>
        <option value="desc">
          {{ t('maintenance.inventory.sort.desc') }}
        </option>
      </select>
    </label>

    <button
      type="button"
      :disabled="loading"
      @click="emit('refresh')"
    >
      {{ t('maintenance.inventory.workspace.refresh') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  loading: boolean
  sortBy: string
  sortOrder: 'asc' | 'desc'
}>()

const emit = defineEmits<{
  refresh: []
  sortChange: [
    value: {
      sortBy: string
      sortOrder: 'asc' | 'desc'
    },
  ]
}>()

const { t } = useI18n()

function changeSortBy(event: Event): void {
  const target = event.target as HTMLSelectElement
  emit('sortChange', {
    sortBy: target.value,
    sortOrder: props.sortOrder,
  })
}

function changeSortOrder(event: Event): void {
  const target = event.target as HTMLSelectElement
  emit('sortChange', {
    sortBy: props.sortBy,
    sortOrder: target.value === 'desc' ? 'desc' : 'asc',
  })
}
</script>

<style scoped>
.inventory-list-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  justify-content: flex-end;
  gap: 12px;
}

.inventory-list-toolbar label {
  display: grid;
  gap: 5px;
  min-width: 150px;
  color: var(--td-text-color-secondary);
  font-size: 11px;
}

.inventory-list-toolbar select,
.inventory-list-toolbar button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.inventory-list-toolbar button {
  cursor: pointer;
}
</style>
