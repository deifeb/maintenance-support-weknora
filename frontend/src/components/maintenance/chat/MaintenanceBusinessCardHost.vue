<template>
  <section
    v-if="renderItems.length"
    class="maintenance-business-card-host"
    aria-label="Maintenance cards"
  >
    <button
      v-for="item in renderItems"
      :key="item.key"
      type="button"
      class="maintenance-business-card-host__item"
      @click="handleNavigate(item.card)"
    >
      <component
        :is="item.component"
        :card="item.card"
      />
    </button>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  type Component,
} from 'vue'
import { useRouter } from 'vue-router'

import {
  isSafeMaintenanceNavigationPath,
  type MaintenanceCard,
} from '@/utils/maintenanceCards'

import { buildMaintenanceCardRenderItems } from './card-host'

const props = defineProps<{
  cards?: unknown
}>()

const router = useRouter()

const renderItems = computed(() =>
  buildMaintenanceCardRenderItems(props.cards).map((item) => ({
    ...item,
    component: defineAsyncComponent(async () => {
      const module = await item.loader()
      return (module as { default: Component }).default
    }),
  })),
)

const handleNavigate = (card: MaintenanceCard) => {
  const path = card.target.navigation_path
  if (!isSafeMaintenanceNavigationPath(path)) return
  void router.push(path)
}
</script>

<style scoped>
.maintenance-business-card-host {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.maintenance-business-card-host__item {
  width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
</style>
