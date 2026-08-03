<template>
  <section class="master-data-home">
    <MaintenancePageHeader
      title="维修主数据"
      description="通过统一资源注册表管理设备、备件、供应、库存和可靠性规则。"
    />

    <div class="master-data-home__layout">
      <nav
        class="master-data-home__navigation"
        aria-label="主数据资源"
      >
        <section
          v-for="group in groups"
          :key="group.key"
          class="master-data-home__group"
        >
          <h2>{{ group.title }}</h2>
          <button
            v-for="resource in group.resources"
            :key="resource.key"
            type="button"
            class="master-data-home__resource"
            :class="{
              'master-data-home__resource--active': resource.key === selectedKey,
            }"
            @click="selectedKey = resource.key"
          >
            <span>{{ resource.title }}</span>
            <span
              class="master-data-home__availability"
              :class="{
                'master-data-home__availability--planned': resource.availability === 'planned',
              }"
            >
              {{ resource.availability === 'available' ? '可用' : '规划中' }}
            </span>
          </button>
        </section>
      </nav>

      <main class="master-data-home__content">
        <MasterDataListPage :resource="selectedResource" />
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  ref,
  watch,
} from 'vue'
import {
  useRoute,
  useRouter,
} from 'vue-router'

import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import {
  MASTER_DATA_RESOURCE_LIST,
  MASTER_DATA_RESOURCES,
  isMasterDataResourceKey,
  type MasterDataResourceKey,
} from '@/components/maintenance/master-data/MasterDataRegistry'
import MasterDataListPage from './MasterDataListPage.vue'

const route = useRoute()
const router = useRouter()

const selectedKey = ref<MasterDataResourceKey>(
  isMasterDataResourceKey(route.query.resource)
    ? route.query.resource
    : 'equipmentModels',
)

watch(selectedKey, async (resource) => {
  await router.replace({
    query: {
      ...route.query,
      resource,
    },
  })
})

watch(
  () => route.query.resource,
  (resource) => {
    selectedKey.value = isMasterDataResourceKey(resource)
      ? resource
      : 'equipmentModels'
  },
)

const groups = [
  {
    key: 'assets',
    title: '设备与备件',
    resources: MASTER_DATA_RESOURCE_LIST.filter(
      (resource) => resource.group === 'assets',
    ),
  },
  {
    key: 'supply',
    title: '供应与库存',
    resources: MASTER_DATA_RESOURCE_LIST.filter(
      (resource) => resource.group === 'supply',
    ),
  },
  {
    key: 'rules',
    title: '规则与可靠性',
    resources: MASTER_DATA_RESOURCE_LIST.filter(
      (resource) => resource.group === 'rules',
    ),
  },
] as const

const selectedResource = computed(
  () => MASTER_DATA_RESOURCES[selectedKey.value],
)
</script>

<style scoped>
.master-data-home {
  max-width: 1540px;
  margin: 0 auto;
  padding: 28px 32px 40px;
}

.master-data-home__layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 24px;
}

.master-data-home__navigation {
  position: sticky;
  top: 20px;
  align-self: start;
  max-height: calc(100vh - 40px);
  overflow: auto;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.master-data-home__group + .master-data-home__group {
  margin-top: 20px;
}

.master-data-home__group h2 {
  margin: 0 0 8px;
  color: var(--td-text-color-placeholder);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.master-data-home__resource {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 9px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--td-text-color-secondary);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.master-data-home__resource:hover,
.master-data-home__resource--active {
  background: var(--td-brand-color-light);
  color: var(--td-brand-color);
}

.master-data-home__availability {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--td-success-color-1);
  color: var(--td-success-color);
  font-size: 10px;
}

.master-data-home__availability--planned {
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-placeholder);
}

.master-data-home__content {
  min-width: 0;
  padding: 22px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

@media (max-width: 960px) {
  .master-data-home__layout {
    grid-template-columns: 1fr;
  }

  .master-data-home__navigation {
    position: static;
    max-height: none;
  }
}

@media (max-width: 640px) {
  .master-data-home {
    padding: 20px 16px 32px;
  }

  .master-data-home__content {
    padding: 16px;
  }
}
</style>
