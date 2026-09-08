<template>
  <main class="configuration-detail">
    <header class="configuration-detail__topbar">
      <button
        type="button"
        class="configuration-detail__back"
        @click="returnToConfigurations"
      >
        返回配置版本
      </button>
    </header>

    <section
      v-if="invalidRoute"
      class="configuration-detail__invalid"
      role="alert"
    >
      <h1>无效配置版本</h1>
      <p>配置版本 ID 必须是正整数。</p>
    </section>

    <template v-else>
      <section
        v-if="version"
        class="configuration-detail__summary"
      >
        <div class="configuration-detail__heading">
          <div>
            <span class="configuration-detail__eyebrow">
              {{ version.version_code }}
            </span>
            <h1>{{ version.version_name }}</h1>
          </div>

          <div class="configuration-detail__actions">
            <button
              v-if="mode === 'editable'"
              type="button"
              :disabled="saving"
              @click="openVersionEdit"
            >
              编辑版本
            </button>
            <button
              v-if="mode === 'clone-only'"
              type="button"
              class="configuration-detail__primary"
              :disabled="saving"
              @click="openVersionClone"
            >
              克隆为草稿
            </button>
          </div>
        </div>

        <dl class="configuration-detail__facts">
          <div>
            <dt>状态</dt>
            <dd>
              <MaintenanceStatusTag :status="version.status" />
            </dd>
          </div>
          <div>
            <dt>生效日期</dt>
            <dd>{{ displayDate(version.effective_date) }}</dd>
          </div>
          <div>
            <dt>失效日期</dt>
            <dd>{{ displayDate(version.expiry_date) }}</dd>
          </div>
          <div>
            <dt>默认版本</dt>
            <dd>{{ version.is_default ? '是' : '否' }}</dd>
          </div>
          <div class="configuration-detail__source">
            <dt>来源参考</dt>
            <dd>{{ version.source_reference || '未提供来源参考' }}</dd>
          </div>
        </dl>
      </section>

      <section
        v-if="loading && !version"
        class="configuration-detail__loading"
        aria-live="polite"
      >
        正在加载配置版本…
      </section>

      <MaintenanceErrorState
        v-if="loadError"
        :error="loadError"
        title="配置版本加载失败"
        @retry="load"
      />

      <section
        v-if="version"
        class="configuration-detail__tree-panel"
        :aria-busy="loading"
      >
        <div
          v-if="loading"
          class="configuration-detail__refreshing"
          aria-live="polite"
        >
          正在刷新配置树…
        </div>

        <ConfigurationTree
          :items="items"
          :editable="mode === 'editable'"
          @create-root="openRootItemCreate"
          @create-child="openChildItemCreate"
          @edit-item="openItemEdit"
        />
      </section>
    </template>

    <ConfigurationVersionEditor
      v-if="version"
      :open="versionEditorOpen"
      :mode="versionEditorMode"
      :version="version"
      :saving="saving"
      :error="actionError"
      @close="closeVersionEditor"
      @save="saveVersion"
    />

    <ConfigurationItemEditor
      v-if="version"
      :open="itemEditorOpen"
      :mode="itemEditorMode"
      :configuration-id="version.id"
      :parent="itemEditorParent"
      :item="itemEditorItem"
      :saving="saving"
      :error="actionError"
      @close="closeItemEditor"
      @save="saveItem"
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

import {
  masterDataDetailsApi,
  type ConfigurationClonePayload,
  type ConfigurationItemCreatePayload,
  type ConfigurationItemUpdatePayload,
  type ConfigurationTreeNode,
  type ConfigurationVersion,
  type ConfigurationVersionUpdatePayload,
} from '@/api/maintenance/master-data-details'
import {
  normalizeMaintenanceError,
} from '@/api/maintenance/client'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import ConfigurationItemEditor from '@/components/maintenance/master-data/ConfigurationItemEditor.vue'
import ConfigurationTree from '@/components/maintenance/master-data/ConfigurationTree.vue'
import {
  configurationDetailMode,
  sortConfigurationTree,
} from '@/components/maintenance/master-data/ConfigurationTree'
import ConfigurationVersionEditor from '@/components/maintenance/master-data/ConfigurationVersionEditor.vue'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const permissionsStore = useMaintenancePermissionsStore()

const version = ref<ConfigurationVersion | null>(null)
const loadedConfigurationId = ref<number | null>(null)
const items = ref<ConfigurationTreeNode[]>([])
const loading = ref(false)
const saving = ref(false)
const loadError = ref<MaintenanceClientError | null>(null)
const actionError = ref<MaintenanceClientError | null>(null)

const versionEditorOpen = ref(false)
const versionEditorMode = ref<'edit' | 'clone'>('edit')

const itemEditorOpen = ref(false)
const itemEditorMode = ref<'create' | 'edit'>('create')
const itemEditorParent = ref<ConfigurationTreeNode | null>(null)
const itemEditorItem = ref<ConfigurationTreeNode | null>(null)

let loadGeneration = 0

function positiveInteger(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

const configurationId = computed(
  () => positiveInteger(route.params.configurationId),
)

const invalidRoute = computed(
  () => configurationId.value === null,
)

const mode = computed(() => (
  version.value
    ? configurationDetailMode(
        version.value,
        permissionsStore.permissions,
        {
          routeConfigurationId: configurationId.value,
          loadedConfigurationId: loadedConfigurationId.value,
        },
      )
    : 'readonly'
))

function displayDate(value: string | null): string {
  return value || '未设置'
}

function resetEditorsForRouteChange(): void {
  versionEditorOpen.value = false
  itemEditorOpen.value = false
  itemEditorParent.value = null
  itemEditorItem.value = null
  actionError.value = null
}

function isCurrentLoadedConfiguration(id: number): boolean {
  if (
    configurationId.value !== id
    || loadedConfigurationId.value !== configurationId.value
  ) {
    return false
  }

  return true
}

async function load(): Promise<void> {
  const id = configurationId.value
  const generation = ++loadGeneration

  if (id === null) {
    loading.value = false
    loadError.value = null
    version.value = null
    loadedConfigurationId.value = null
    items.value = []
    return
  }

  loading.value = true
  loadError.value = null

  try {
    const result = await masterDataDetailsApi.getConfigurationTree(id)

    if (generation !== loadGeneration) {
      return
    }

    version.value = result.data.version
    loadedConfigurationId.value = id
    items.value = sortConfigurationTree(result.data.items)
  } catch (error) {
    if (generation !== loadGeneration) {
      return
    }

    loadError.value = normalizeMaintenanceError(error)
  } finally {
    if (generation === loadGeneration) {
      loading.value = false
    }
  }
}

watch(
  () => route.params.configurationId,
  () => {
    resetEditorsForRouteChange()
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  loadGeneration += 1
})

function returnToConfigurations(): void {
  void router.push({
    name: 'maintenanceMasterData',
    query: {
      resource: 'configurations',
    },
  })
}

function openVersionEdit(): void {
  if (mode.value !== 'editable') {
    return
  }

  actionError.value = null
  versionEditorMode.value = 'edit'
  versionEditorOpen.value = true
}

function openVersionClone(): void {
  if (mode.value !== 'clone-only') {
    return
  }

  actionError.value = null
  versionEditorMode.value = 'clone'
  versionEditorOpen.value = true
}

function closeVersionEditor(): void {
  if (saving.value) {
    return
  }

  versionEditorOpen.value = false
  actionError.value = null
}

function openRootItemCreate(): void {
  if (mode.value !== 'editable') {
    return
  }

  actionError.value = null
  itemEditorMode.value = 'create'
  itemEditorParent.value = null
  itemEditorItem.value = null
  itemEditorOpen.value = true
}

function openChildItemCreate(parent: ConfigurationTreeNode): void {
  if (mode.value !== 'editable') {
    return
  }

  actionError.value = null
  itemEditorMode.value = 'create'
  itemEditorParent.value = parent
  itemEditorItem.value = null
  itemEditorOpen.value = true
}

function openItemEdit(item: ConfigurationTreeNode): void {
  if (mode.value !== 'editable') {
    return
  }

  actionError.value = null
  itemEditorMode.value = 'edit'
  itemEditorParent.value = null
  itemEditorItem.value = item
  itemEditorOpen.value = true
}

function closeItemEditor(): void {
  if (saving.value) {
    return
  }

  itemEditorOpen.value = false
  itemEditorParent.value = null
  itemEditorItem.value = null
  actionError.value = null
}

async function saveVersion(
  payload: ConfigurationVersionUpdatePayload | ConfigurationClonePayload,
): Promise<void> {
  const id = configurationId.value
  const expectedMode = versionEditorMode.value === 'clone'
    ? 'clone-only'
    : 'editable'

  if (
    id === null
    || saving.value
    || loadedConfigurationId.value !== id
    || mode.value !== expectedMode
  ) {
    return
  }

  saving.value = true
  actionError.value = null

  try {
    if (versionEditorMode.value === 'clone') {
      const cloned = await masterDataDetailsApi.cloneConfigurationVersion(
        id,
        payload as ConfigurationClonePayload,
      )

      if (!isCurrentLoadedConfiguration(id)) {
        return
      }

      versionEditorOpen.value = false
      await router.replace({
        name: 'maintenanceConfigurationDetail',
        params: {
          configurationId: cloned.data.id,
        },
      })
      return
    }

    await masterDataDetailsApi.updateConfigurationVersion(
      id,
      payload as ConfigurationVersionUpdatePayload,
    )

    if (!isCurrentLoadedConfiguration(id)) {
      return
    }

    versionEditorOpen.value = false
    await load()
  } catch (error) {
    if (isCurrentLoadedConfiguration(id)) {
      actionError.value = normalizeMaintenanceError(error)
    }
  } finally {
    saving.value = false
  }
}

async function saveItem(
  payload: ConfigurationItemCreatePayload | ConfigurationItemUpdatePayload,
): Promise<void> {
  const id = configurationId.value

  if (
    id === null
    || saving.value
    || mode.value !== 'editable'
    || loadedConfigurationId.value !== id
  ) {
    return
  }

  saving.value = true
  actionError.value = null

  try {
    if (itemEditorMode.value === 'create') {
      await masterDataDetailsApi.createConfigurationItem(
        payload as ConfigurationItemCreatePayload,
      )
    } else {
      const itemId = itemEditorItem.value?.id
      if (!itemId) {
        throw new Error('Missing configuration item ID')
      }

      await masterDataDetailsApi.updateConfigurationItem(
        itemId,
        payload as ConfigurationItemUpdatePayload,
      )
    }

    if (!isCurrentLoadedConfiguration(id)) {
      return
    }

    itemEditorOpen.value = false
    itemEditorParent.value = null
    itemEditorItem.value = null
    await load()
  } catch (error) {
    if (isCurrentLoadedConfiguration(id)) {
      actionError.value = normalizeMaintenanceError(error)
    }
  } finally {
    saving.value = false
  }
}

</script>

<style scoped>
.configuration-detail {
  display: grid;
  gap: 20px;
  padding: 24px;
}

.configuration-detail__topbar {
  display: flex;
  justify-content: flex-start;
}

.configuration-detail__back,
.configuration-detail__actions button {
  padding: 8px 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.configuration-detail__summary,
.configuration-detail__tree-panel,
.configuration-detail__invalid,
.configuration-detail__loading {
  padding: 24px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.configuration-detail__invalid h1,
.configuration-detail__invalid p {
  margin: 0;
}

.configuration-detail__invalid p {
  margin-top: 8px;
  color: var(--td-text-color-secondary);
}

.configuration-detail__heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.configuration-detail__eyebrow {
  color: var(--td-brand-color);
  font-size: 12px;
  font-weight: 600;
}

.configuration-detail__heading h1 {
  margin: 6px 0 0;
}

.configuration-detail__actions {
  display: flex;
  gap: 10px;
}

.configuration-detail__actions .configuration-detail__primary {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

.configuration-detail__actions button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.configuration-detail__facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
  margin: 24px 0 0;
}

.configuration-detail__facts div {
  min-width: 0;
}

.configuration-detail__facts dt {
  color: var(--td-text-color-placeholder);
  font-size: 12px;
}

.configuration-detail__facts dd {
  margin: 6px 0 0;
  overflow-wrap: anywhere;
}

.configuration-detail__source {
  grid-column: span 2;
}

.configuration-detail__loading,
.configuration-detail__refreshing {
  color: var(--td-text-color-secondary);
}

.configuration-detail__tree-panel {
  display: grid;
  gap: 14px;
}

.configuration-detail__refreshing {
  font-size: 13px;
}

@media (max-width: 880px) {
  .configuration-detail {
    padding: 16px;
  }

  .configuration-detail__heading {
    display: grid;
  }

  .configuration-detail__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .configuration-detail__facts {
    grid-template-columns: 1fr;
  }

  .configuration-detail__source {
    grid-column: auto;
  }
}
</style>
