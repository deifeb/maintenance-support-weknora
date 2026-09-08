<template>
  <main class="spare-part-detail">
    <header class="spare-part-detail__topbar">
      <button
        type="button"
        class="spare-part-detail__back"
        @click="returnToSpareParts"
      >
        返回备件列表
      </button>
    </header>

    <section
      v-if="invalidRoute"
      class="spare-part-detail__invalid"
      role="alert"
    >
      <h1>无效备件</h1>
      <p>备件 ID 必须是正整数，当前页面不会发起数据请求。</p>
    </section>

    <template v-else>
      <section class="spare-part-detail__heading">
        <div>
          <span class="spare-part-detail__eyebrow">
            {{ overviewRecord?.code || `备件 #${sparePartId}` }}
          </span>
          <h1>{{ overviewRecord?.name || '备件详情' }}</h1>
          <p>按需加载库存、可靠性和供应信息；未开放页签不会发起猜测请求。</p>
        </div>

        <button
          v-if="canEdit"
          type="button"
          class="spare-part-detail__edit"
          :disabled="saving"
          @click="openEditor"
        >
          编辑备件
        </button>
      </section>

      <nav
        class="spare-part-detail__tabs"
        aria-label="备件详情页签"
      >
        <button
          v-for="tab in SPARE_PART_TABS"
          :key="tab.key"
          type="button"
          :class="{
            'spare-part-detail__tab--active': activeTab === tab.key,
          }"
          :aria-current="activeTab === tab.key ? 'page' : undefined"
          @click="activateTab(tab.key)"
        >
          {{ tab.label }}
          <span
            v-if="tab.availability === 'unavailable'"
            class="spare-part-detail__planned"
          >
            未开放
          </span>
        </button>
      </nav>

      <section class="spare-part-detail__content">
        <div
          v-if="activeState.status === 'loading'"
          class="spare-part-detail__loading"
          aria-live="polite"
        >
          正在加载{{ activeTabLabel }}…
        </div>

        <MaintenanceErrorState
          v-else-if="activeState.status === 'error' && activeError"
          :error="activeError"
          :title="`${activeTabLabel}加载失败`"
          @retry="retryActiveTab"
        />

        <SparePartOverview
          v-else-if="
            activeTab === 'overview'
            && activeState.status === 'loaded'
            && overviewRecord
          "
          :record="overviewRecord"
        />

        <SparePartInventory
          v-else-if="
            activeTab === 'inventory'
            && activeState.status === 'loaded'
          "
          :page="inventoryPage"
        />

        <SparePartReliability
          v-else-if="
            activeTab === 'reliability'
            && activeState.status === 'loaded'
          "
          :page="reliabilityPage"
        />

        <SparePartSupply
          v-else-if="
            activeTab === 'supply'
            && activeState.status === 'loaded'
          "
          :page="supplyPage"
        />

        <SparePartApplicability
          v-else-if="activeTab === 'applicability'"
        />
        <SparePartLotsSerials
          v-else-if="activeTab === 'lotsSerials'"
        />
        <SparePartSubstitutions
          v-else-if="activeTab === 'substitutions'"
        />
        <SparePartKitRules
          v-else-if="activeTab === 'kitRules'"
        />
        <SparePartEvidence
          v-else-if="activeTab === 'evidence'"
        />
        <SparePartAudit
          v-else-if="activeTab === 'audit'"
        />

        <div
          v-else-if="activeState.status === 'idle'"
          class="spare-part-detail__loading"
        >
          等待加载{{ activeTabLabel }}。
        </div>
      </section>
    </template>

    <MasterDataEditorDrawer
      :open="editorOpen"
      :resource="MASTER_DATA_RESOURCES.spareParts"
      :record="editorRecord"
      mode="edit"
      :saving="saving"
      :error="editorError"
      @close="closeEditor"
      @save="saveSparePart"
    />
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import {
  useRoute,
  useRouter,
} from 'vue-router'

import { normalizeMaintenanceError } from '@/api/maintenance/client'
import {
  masterDataDetailsApi,
  type InventoryDetailRecord,
  type ReliabilityDetailRecord,
  type SparePartDetailRecord,
  type SupplierOfferDetailRecord,
} from '@/api/maintenance/master-data-details'
import { masterDataApi } from '@/api/maintenance/master-data'
import type {
  MaintenanceClientError,
  PageData,
} from '@/api/maintenance/types'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MasterDataEditorDrawer from '@/components/maintenance/master-data/MasterDataEditorDrawer.vue'
import {
  MASTER_DATA_RESOURCES,
  serializeMasterDataForm,
  type MasterDataRecord,
} from '@/components/maintenance/master-data/MasterDataRegistry'
import SparePartApplicability from '@/components/maintenance/master-data/SparePartApplicability.vue'
import SparePartAudit from '@/components/maintenance/master-data/SparePartAudit.vue'
import SparePartEvidence from '@/components/maintenance/master-data/SparePartEvidence.vue'
import SparePartInventory from '@/components/maintenance/master-data/SparePartInventory.vue'
import SparePartKitRules from '@/components/maintenance/master-data/SparePartKitRules.vue'
import SparePartLotsSerials from '@/components/maintenance/master-data/SparePartLotsSerials.vue'
import SparePartOverview from '@/components/maintenance/master-data/SparePartOverview.vue'
import {
  SPARE_PART_TABS,
  type SparePartTabKey,
} from '@/components/maintenance/master-data/SparePartOverview'
import SparePartReliability from '@/components/maintenance/master-data/SparePartReliability.vue'
import SparePartSubstitutions from '@/components/maintenance/master-data/SparePartSubstitutions.vue'
import SparePartSupply from '@/components/maintenance/master-data/SparePartSupply.vue'
import { createLazyDetailTabs } from '@/composables/maintenance/useLazyDetailTabs'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const permissionsStore = useMaintenancePermissionsStore()

function positiveInteger(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0
    ? parsed
    : null
}

const sparePartId = computed(
  () => positiveInteger(route.params.sparePartId),
)
const invalidRoute = computed(
  () => sparePartId.value === null,
)

function currentSparePartId(): number {
  const id = sparePartId.value
  if (id === null) {
    throw new Error('Spare part ID is invalid')
  }
  return id
}

const unavailableTabs: readonly SparePartTabKey[] = [
  'applicability',
  'lotsSerials',
  'substitutions',
  'kitRules',
  'evidence',
  'audit',
]

const tabs = createLazyDetailTabs<SparePartTabKey>(
  {
    overview: async () => {
      const id = currentSparePartId()
      return (await masterDataDetailsApi.getSparePart(id)).data
    },
    inventory: async () => {
      const id = currentSparePartId()
      return (
        await masterDataDetailsApi.listSparePartInventory(id)
      ).data
    },
    reliability: async () => {
      const id = currentSparePartId()
      return (
        await masterDataDetailsApi.listSparePartReliability(id)
      ).data
    },
    supply: async () => {
      const id = currentSparePartId()
      return (
        await masterDataDetailsApi.listSparePartSupply(id)
      ).data
    },
  },
  unavailableTabs,
)

const activeTab = ref<SparePartTabKey>('overview')
const editorOpen = ref(false)
const saving = ref(false)
const editorError = ref<MaintenanceClientError | null>(null)
let routeGeneration = 0

const activeState = computed(
  () => tabs.state(activeTab.value),
)
const activeError = computed(
  () => activeState.value.error,
)
const activeTabLabel = computed(
  () => (
    SPARE_PART_TABS.find(
      (tab) => tab.key === activeTab.value,
    )?.label ?? '页签'
  ),
)

const overviewRecord = computed(
  () => (
    tabs.state('overview').data as SparePartDetailRecord | null
  ),
)

const emptyInventoryPage: PageData<InventoryDetailRecord> = {
  items: [],
  page: 1,
  page_size: 200,
  total: 0,
  pages: 0,
}
const emptyReliabilityPage: PageData<ReliabilityDetailRecord> = {
  items: [],
  page: 1,
  page_size: 200,
  total: 0,
  pages: 0,
}
const emptySupplyPage: PageData<SupplierOfferDetailRecord> = {
  items: [],
  page: 1,
  page_size: 200,
  total: 0,
  pages: 0,
}

const inventoryPage = computed(
  () => (
    tabs.state('inventory').data as
      PageData<InventoryDetailRecord> | null
  ) ?? emptyInventoryPage,
)
const reliabilityPage = computed(
  () => (
    tabs.state('reliability').data as
      PageData<ReliabilityDetailRecord> | null
  ) ?? emptyReliabilityPage,
)
const supplyPage = computed(
  () => (
    tabs.state('supply').data as
      PageData<SupplierOfferDetailRecord> | null
  ) ?? emptySupplyPage,
)

const editorRecord = computed<MasterDataRecord | null>(
  () => (
    overviewRecord.value
      ? overviewRecord.value as unknown as MasterDataRecord
      : null
  ),
)

const canEdit = computed(
  () => (
    permissionsStore.permissions.editMasterData
    && overviewRecord.value !== null
  ),
)

function activateTab(tab: SparePartTabKey): void {
  activeTab.value = tab
  void tabs.activate(tab)
}

function retryActiveTab(): void {
  const tab = activeTab.value
  void tabs.retry(tab)
}

function resetForRouteChange(): void {
  routeGeneration += 1
  tabs.reset()
  activeTab.value = 'overview'
  editorOpen.value = false
  editorError.value = null
}

watch(
  () => route.params.sparePartId,
  async () => {
    resetForRouteChange()

    if (sparePartId.value === null) {
      return
    }

    await tabs.activate('overview')
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  routeGeneration += 1
  tabs.reset()
})

function returnToSpareParts(): void {
  void router.push({
    name: 'maintenanceMasterData',
    query: {
      resource: 'spareParts',
    },
  })
}

function openEditor(): void {
  if (!canEdit.value || saving.value) {
    return
  }

  editorError.value = null
  editorOpen.value = true
}

function closeEditor(): void {
  if (saving.value) {
    return
  }

  editorOpen.value = false
  editorError.value = null
}

async function saveSparePart(
  values: MasterDataRecord,
): Promise<void> {
  const id = sparePartId.value
  const generation = routeGeneration

  if (
    id === null
    || saving.value
    || !canEdit.value
  ) {
    return
  }

  saving.value = true
  editorError.value = null

  try {
    const payload = serializeMasterDataForm(
      MASTER_DATA_RESOURCES.spareParts,
      values,
      'edit',
    )

    await masterDataApi.update<SparePartDetailRecord>(
      MASTER_DATA_RESOURCES.spareParts,
      id,
      payload,
    )

    if (
      routeGeneration !== generation
      || sparePartId.value !== id
    ) {
      return
    }

    editorOpen.value = false
    tabs.invalidate('overview')
    await tabs.activate('overview')
  } catch (error) {
    if (
      routeGeneration === generation
      && sparePartId.value === id
    ) {
      editorError.value = normalizeMaintenanceError(error)
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.spare-part-detail {
  display: grid;
  gap: 20px;
  padding: 24px;
}

.spare-part-detail__topbar {
  display: flex;
  align-items: center;
}

.spare-part-detail__back,
.spare-part-detail__edit,
.spare-part-detail__tabs button {
  border: 1px solid var(--td-component-stroke);
  border-radius: 7px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.spare-part-detail__back,
.spare-part-detail__edit {
  padding: 9px 15px;
}

.spare-part-detail__edit {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

.spare-part-detail__edit:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.spare-part-detail__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.spare-part-detail__heading h1 {
  margin: 6px 0 0;
}

.spare-part-detail__heading p {
  margin: 10px 0 0;
  color: var(--td-text-color-secondary);
}

.spare-part-detail__eyebrow {
  color: var(--td-brand-color);
  font-size: 12px;
  font-weight: 600;
}

.spare-part-detail__tabs {
  display: flex;
  overflow-x: auto;
  gap: 8px;
  padding-bottom: 4px;
}

.spare-part-detail__tabs button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 7px;
  padding: 9px 13px;
}

.spare-part-detail__tabs button:hover,
.spare-part-detail__tab--active {
  border-color: var(--td-brand-color) !important;
  color: var(--td-brand-color) !important;
}

.spare-part-detail__planned {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-placeholder);
  font-size: 10px;
}

.spare-part-detail__content {
  min-height: 240px;
}

.spare-part-detail__loading,
.spare-part-detail__invalid {
  padding: 24px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
}

.spare-part-detail__invalid h1 {
  margin: 0;
  color: var(--td-text-color-primary);
}

.spare-part-detail__invalid p {
  margin: 10px 0 0;
}

@media (max-width: 680px) {
  .spare-part-detail {
    padding: 16px;
  }

  .spare-part-detail__heading {
    flex-direction: column;
  }
}
</style>
