<template>
  <section class="master-data-list-page">
    <MaintenancePageHeader
      :title="resource.title"
      :description="resource.description"
    >
      <template #secondaryActions>
        <button
          v-if="transferActions.includes('template')"
          type="button"
          class="master-data-list-page__secondary-button"
          :disabled="transferring"
          @click="downloadTemplate"
        >
          下载模板
        </button>
        <button
          v-if="transferActions.includes('export')"
          type="button"
          class="master-data-list-page__secondary-button"
          :disabled="transferring"
          @click="exportCurrentResults"
        >
          导出当前结果
        </button>
      </template>
      <template #primaryActions>
        <button
          v-if="transferActions.includes('import')"
          type="button"
          class="master-data-list-page__primary-button"
          :disabled="transferring"
          @click="openImport"
        >
          导入 Excel
        </button>
        <button
          v-if="canCreate"
          type="button"
          class="master-data-list-page__primary-button"
          @click="openCreate"
        >
          新建{{ resource.title }}
        </button>
      </template>
    </MaintenancePageHeader>

    <MaintenanceEmptyState
      v-if="resource.availability === 'planned'"
      title="该资源尚未开放"
      description="注册表已保留该资源定义；后端主数据路由就绪后即可启用列表和编辑器。"
    />

    <template v-else>
      <div class="master-data-list-page__toolbar">
        <form
          class="master-data-list-page__search"
          @submit.prevent="applyKeyword"
        >
          <input
            v-model="keywordDraft"
            type="search"
            placeholder="按编码或名称搜索"
          >
          <button type="submit">
            搜索
          </button>
        </form>

        <label class="master-data-list-page__inactive-toggle">
          <input
            :checked="includeInactive"
            type="checkbox"
            @change="toggleInactive"
          >
          包含停用记录
        </label>

        <button
          type="button"
          class="master-data-list-page__refresh"
          :disabled="loading"
          @click="refresh"
        >
          {{ loading ? '刷新中…' : '刷新' }}
        </button>
      </div>

      <MaintenanceErrorState
        v-if="error"
        :error="error"
        class="master-data-list-page__error"
        @retry="refresh"
      />

      <MaintenanceErrorState
        v-if="actionError"
        :error="actionError"
        class="master-data-list-page__error"
      />

      <MaintenanceEmptyState
        v-if="!loading && !error && rows.length === 0"
        title="暂无主数据"
        description="调整搜索条件，或在具备维护权限时新建记录。"
        :action-label="canCreate ? `新建${resource.title}` : ''"
        @action="openCreate"
      />

      <MasterDataTable
        v-else
        :rows="rows"
        :columns="resource.columns"
        :row-key="resource.rowKey"
        :loading="loading"
        :sort-by="sortBy"
        :sort-order="sortOrder"
        :actions-for-row="actionsForRow"
        @sort="setSort"
        @action="handleRowAction"
      />

      <footer class="master-data-list-page__pagination">
        <span>
          共 {{ total }} 条
        </span>
        <label>
          每页
          <select
            :value="pageSize"
            @change="changePageSize"
          >
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
        </label>
        <button
          type="button"
          :disabled="page <= 1 || loading"
          @click="setPage(page - 1)"
        >
          上一页
        </button>
        <span>
          第 {{ page }} / {{ Math.max(pages, 1) }} 页
        </span>
        <button
          type="button"
          :disabled="page >= pages || loading"
          @click="setPage(page + 1)"
        >
          下一页
        </button>
      </footer>
    </template>

    <MasterDataEditorDrawer
      :open="drawerOpen"
      :resource="resource"
      :record="selectedRecord"
      :mode="drawerMode"
      :saving="saving"
      :error="drawerError"
      @close="closeDrawer"
      @save="saveRecord"
    />

    <MasterDataImportDialog
      v-if="resource.availability === 'available'"
      :key="resource.key"
      :open="importDialogOpen"
      :resource-key="resource.key"
      :can-import="transferActions.includes('import')"
      @close="closeImport"
      @completed="handleImportCompleted"
      @error="reportImportError"
    />
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  ref,
  watch,
} from 'vue'
import { useRouter } from 'vue-router'

import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { masterDataTransferApi } from '@/api/maintenance/imports'
import { masterDataApi } from '@/api/maintenance/master-data'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import { useServerTable } from '@/composables/maintenance/useServerTable'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'
import MasterDataEditorDrawer from '@/components/maintenance/master-data/MasterDataEditorDrawer.vue'
import MasterDataImportDialog from '@/components/maintenance/import/MasterDataImportDialog.vue'
import MasterDataTable from '@/components/maintenance/master-data/MasterDataTable.vue'
import {
  createMasterDataTransferActions,
  createXlsxDownloadTrigger,
  type MasterDataTransferToken,
} from './master-data-transfer-actions'
import {
  serializeMasterDataForm,
  visibleMasterDataTransferActions,
  type MasterDataRecord,
  type MasterDataResourceDefinition,
  type MasterDataRowAction,
} from '@/components/maintenance/master-data/MasterDataRegistry'

const props = defineProps<{
  resource: MasterDataResourceDefinition
}>()

const router = useRouter()
const permissionsStore = useMaintenancePermissionsStore()
const keywordDraft = ref('')
const drawerOpen = ref(false)
const drawerMode = ref<'create' | 'edit' | 'view'>('create')
const selectedRecord = ref<MasterDataRecord | null>(null)
const saving = ref(false)
const drawerError = ref<MaintenanceClientError | null>(null)
const actionError = ref<MaintenanceClientError | null>(null)
const transferring = ref(false)
const importDialogOpen = ref(false)
const importDialogToken = ref<MasterDataTransferToken | null>(null)
const importGeneration = ref(0)

const table = useServerTable<MasterDataRecord>({
  initialPageSize: 20,
  initialSortBy: String(props.resource.rowKey),
  fetchPage: async (query) => {
    return (await masterDataApi.list<MasterDataRecord>(props.resource, query)).data
  },
})

const {
  rows,
  page,
  pageSize,
  total,
  pages,
  keyword,
  includeInactive,
  sortBy,
  sortOrder,
  loading,
  error,
  refresh,
  setKeyword,
  setPage,
  setPageSize,
  setSort,
  setIncludeInactive,
  reset,
} = table

const currentActions = computed(
  () => props.resource.actions(permissionsStore.permissions),
)

const canCreate = computed(() => (
  props.resource.availability === 'available'
  && props.resource.operations.create
  && currentActions.value.some((action) => action.kind === 'edit')
))

const transferActions = computed(() => (
  visibleMasterDataTransferActions(
    props.resource,
    permissionsStore.permissions,
  )
))

const transferDownload = createXlsxDownloadTrigger({
  document: {
    body: {
      append: (link) => document.body.append(link as unknown as Node),
    },
    createElement: () => document.createElement('a'),
  },
  objectUrls: URL,
  defer: (callback) => window.setTimeout(callback, 0),
})

const transferController = createMasterDataTransferActions({
  api: masterDataTransferApi,
  getResource: () => props.resource,
  getQuery: () => ({
    keyword: keyword.value,
    include_inactive: includeInactive.value,
    sort_by: sortBy.value,
    sort_order: sortOrder.value,
  }),
  getGeneration: () => importGeneration.value,
  download: transferDownload,
  onBusyChange: (busy) => { transferring.value = busy },
  onError: (error) => { actionError.value = error },
  refresh,
})

watch(
  () => props.resource.key,
  async () => {
    closeDrawer()
    importDialogOpen.value = false
    importDialogToken.value = null
    importGeneration.value += 1
    await nextTick()
    keywordDraft.value = ''
    reset({
      page: 1,
      page_size: 20,
      keyword: '',
      include_inactive: false,
      sort_by: String(props.resource.rowKey),
      sort_order: 'asc',
    })

    if (props.resource.availability === 'available') {
      await refresh()
    }
  },
  { immediate: true },
)

async function downloadTemplate(): Promise<void> {
  if (transferring.value || !transferActions.value.includes('template')) {
    return
  }

  actionError.value = null
  await transferController.downloadTemplate()
}

async function exportCurrentResults(): Promise<void> {
  if (
    transferring.value
    || !transferActions.value.includes('export')
  ) {
    return
  }

  actionError.value = null
  await transferController.exportCurrentResults()
}

function openImport(): void {
  if (
    transferring.value
    || !transferActions.value.includes('import')
  ) {
    return
  }
  actionError.value = null
  importDialogToken.value = {
    resourceKey: props.resource.key,
    generation: importGeneration.value,
  }
  importDialogOpen.value = true
}

function closeImport(): void {
  importDialogOpen.value = false
  importDialogToken.value = null
}

function handleImportCompleted(): void {
  const token = importDialogToken.value
  importDialogOpen.value = false
  importDialogToken.value = null
  if (token) void transferController.handleCompleted(token)
}

function reportImportError(error: MaintenanceClientError): void {
  actionError.value = error
}

function actionsForRow(
  row: MasterDataRecord,
): MasterDataRowAction[] {
  return props.resource.actions(
    permissionsStore.permissions,
    row,
  ).filter((action) => {
    if (action.kind !== 'deactivate') {
      return true
    }
    return row.is_active !== false
  })
}

function openCreate(): void {
  if (!canCreate.value) {
    return
  }
  drawerMode.value = 'create'
  selectedRecord.value = null
  drawerError.value = null
  drawerOpen.value = true
}

function closeDrawer(): void {
  drawerOpen.value = false
  selectedRecord.value = null
  drawerError.value = null
}

function recordIdentifier(row: MasterDataRecord): string | number | null {
  const value = row[props.resource.rowKey]
  return typeof value === 'string' || typeof value === 'number'
    ? value
    : null
}

async function handleRowAction(
  action: MasterDataRowAction,
  row: MasterDataRecord,
): Promise<void> {
  actionError.value = null

  const identifier = recordIdentifier(row)
  const detailRoute = props.resource.detailRoute

  if (
    action.kind === 'view'
    && detailRoute
    && identifier !== null
  ) {
    await router.push({
      name: detailRoute.name,
      params: {
        [detailRoute.param]: identifier,
      },
    })
    return
  }

  if (action.kind === 'view') {
    drawerMode.value = 'view'
    selectedRecord.value = row
    drawerOpen.value = true
    return
  }

  if (action.kind === 'edit') {
    const canEdit = props.resource
      .actions(permissionsStore.permissions, row)
      .some((candidate) => candidate.kind === 'edit')

    if (!canEdit) {
      return
    }

    drawerMode.value = 'edit'
    selectedRecord.value = row
    drawerOpen.value = true
    return
  }

  if (identifier === null || !props.resource.operations.deactivate) {
    return
  }

  try {
    await masterDataApi.setActive(
      props.resource,
      identifier,
      false,
    )
    await refresh()
  } catch (value) {
    actionError.value = normalizeMaintenanceError(value)
  }
}

async function saveRecord(values: MasterDataRecord): Promise<void> {
  const canEditSelected = (
    drawerMode.value !== 'edit'
    || (
      selectedRecord.value !== null
      && props.resource
        .actions(
          permissionsStore.permissions,
          selectedRecord.value,
        )
        .some((action) => action.kind === 'edit')
    )
  )

  if (
    saving.value
    || drawerMode.value === 'view'
    || !canEditSelected
  ) {
    return
  }

  saving.value = true
  drawerError.value = null

  try {
    const mode = drawerMode.value === 'edit' ? 'edit' : 'create'
    const payload = serializeMasterDataForm(
      props.resource,
      values,
      mode,
    )

    if (mode === 'edit') {
      const identifier = selectedRecord.value
        ? recordIdentifier(selectedRecord.value)
        : null
      if (identifier === null) {
        throw new Error('Master data identifier is missing')
      }
      await masterDataApi.update(
        props.resource,
        identifier,
        payload,
      )
    } else {
      await masterDataApi.create(
        props.resource,
        payload,
      )
    }

    closeDrawer()
    await refresh()
  } catch (value) {
    drawerError.value = normalizeMaintenanceError(value)
  } finally {
    saving.value = false
  }
}

async function applyKeyword(): Promise<void> {
  await setKeyword(keywordDraft.value)
}

async function toggleInactive(event: Event): Promise<void> {
  await setIncludeInactive(
    (event.target as HTMLInputElement).checked,
  )
}

async function changePageSize(event: Event): Promise<void> {
  await setPageSize(
    Number((event.target as HTMLSelectElement).value),
  )
}
</script>

<style scoped>
.master-data-list-page {
  min-width: 0;
}

.master-data-list-page__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.master-data-list-page__search {
  display: flex;
  min-width: min(100%, 360px);
}

.master-data-list-page__search input {
  min-width: 0;
  flex: 1;
  padding: 9px 11px;
  border: 1px solid var(--td-component-stroke);
  border-right: 0;
  border-radius: 6px 0 0 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.master-data-list-page__search button,
.master-data-list-page__refresh,
.master-data-list-page__primary-button,
.master-data-list-page__pagination button {
  padding: 9px 14px;
  border: 1px solid var(--td-brand-color);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.master-data-list-page__search button {
  border-radius: 0 6px 6px 0;
  background: var(--td-brand-color);
  color: #fff;
}

.master-data-list-page__primary-button {
  background: var(--td-brand-color);
  color: #fff;
}

.master-data-list-page__inactive-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.master-data-list-page__refresh {
  margin-left: auto;
}

.master-data-list-page__error {
  margin-bottom: 16px;
}

.master-data-list-page__pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.master-data-list-page__pagination label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.master-data-list-page__pagination select {
  padding: 6px 8px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
}

.master-data-list-page__pagination button:disabled,
.master-data-list-page__refresh:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
