<template>
  <div
    v-if="actions.length"
    class="demand-list-lifecycle-actions"
  >
    <button
      v-for="action in actions"
      :key="action"
      type="button"
      :class="{
        'demand-list-lifecycle-actions__danger': (
          action === 'void'
        ),
      }"
      :disabled="busy"
      @click="emit('select', action)"
    >
      {{
        t(
          `maintenance.calculation.demandList.actions.${action}`,
        )
      }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  DemandListStatus,
} from '@/api/maintenance/demand-lists'
import {
  demandListActions,
  type DemandListAction,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
import type {
  MaintenancePermissions,
} from '@/stores/maintenance/permission-matrix'

const props = defineProps<{
  status: DemandListStatus
  permissions: MaintenancePermissions
  busy: boolean
}>()

const emit = defineEmits<{
  select: [action: DemandListAction]
}>()

const { t } = useI18n()

const actions = computed(() => demandListActions(
  props.status,
  props.permissions,
))
</script>

<style scoped>
.demand-list-lifecycle-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.demand-list-lifecycle-actions button {
  min-height: 36px;
  padding: 0 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.demand-list-lifecycle-actions button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.demand-list-lifecycle-actions__danger {
  color: var(--td-error-color) !important;
}
</style>
