<template>
  <main class="inventory-workspace">
    <MaintenancePageHeader
      :eyebrow="t('maintenance.inventory.workspace.eyebrow')"
      :title="t('maintenance.inventory.workspace.title')"
      :description="t('maintenance.inventory.workspace.description')"
    />

    <nav class="inventory-workspace__tabs" aria-label="Inventory workspace">
      <button
        v-for="tab in INVENTORY_WORKSPACE_TABS"
        :key="tab"
        type="button"
        :class="{ 'inventory-workspace__tab--active': activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ t(`maintenance.inventory.workspace.tabs.${tab}`) }}
      </button>
    </nav>

    <section class="inventory-workspace__controls">
      <div class="inventory-workspace__filters">
        <template v-if="activeTab === 'balances'">
          <NumericFilter v-model="balanceFilters.warehouseId" :label="t('maintenance.inventory.filters.warehouseId')" />
          <NumericFilter v-model="balanceFilters.locationId" :label="t('maintenance.inventory.filters.locationId')" />
          <NumericFilter v-model="balanceFilters.sparePartId" :label="t('maintenance.inventory.filters.sparePartId')" />
          <NumericFilter v-model="balanceFilters.lotId" :label="t('maintenance.inventory.filters.lotId')" />
          <NumericFilter v-model="balanceFilters.serialItemId" :label="t('maintenance.inventory.filters.serialItemId')" />
        </template>

        <template v-else-if="activeTab === 'reservations'">
          <label>
            <span>{{ t('maintenance.inventory.filters.status') }}</span>
            <select v-model="reservationFilters.status">
              <option value="">{{ t('maintenance.inventory.filters.all') }}</option>
              <option v-for="status in reservationStatuses" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <TextFilter v-model="reservationFilters.ownerType" :label="t('maintenance.inventory.filters.ownerType')" />
          <TextFilter v-model="reservationFilters.ownerId" :label="t('maintenance.inventory.filters.ownerId')" />
        </template>

        <template v-else-if="activeTab === 'transfers'">
          <label>
            <span>{{ t('maintenance.inventory.filters.status') }}</span>
            <select v-model="transferFilters.status">
              <option value="">{{ t('maintenance.inventory.filters.all') }}</option>
              <option v-for="status in transferStatuses" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <NumericFilter v-model="transferFilters.sourceWarehouseId" :label="t('maintenance.inventory.filters.sourceWarehouseId')" />
          <NumericFilter v-model="transferFilters.sourceLocationId" :label="t('maintenance.inventory.filters.sourceLocationId')" />
          <NumericFilter v-model="transferFilters.targetWarehouseId" :label="t('maintenance.inventory.filters.targetWarehouseId')" />
          <NumericFilter v-model="transferFilters.targetLocationId" :label="t('maintenance.inventory.filters.targetLocationId')" />
          <TextFilter v-model="transferFilters.referenceType" :label="t('maintenance.inventory.filters.referenceType')" />
          <TextFilter v-model="transferFilters.referenceId" :label="t('maintenance.inventory.filters.referenceId')" />
        </template>

        <template v-else-if="activeTab === 'stocktakes'">
          <label>
            <span>{{ t('maintenance.inventory.filters.status') }}</span>
            <select v-model="stocktakeFilters.status">
              <option value="">{{ t('maintenance.inventory.filters.all') }}</option>
              <option v-for="status in stocktakeStatuses" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <NumericFilter v-model="stocktakeFilters.warehouseId" :label="t('maintenance.inventory.filters.warehouseId')" />
          <NumericFilter v-model="stocktakeFilters.locationId" :label="t('maintenance.inventory.filters.locationId')" />
        </template>

        <template v-else>
          <label>
            <span>{{ t('maintenance.inventory.filters.operationType') }}</span>
            <select v-model="transactionFilters.operationType">
              <option value="">{{ t('maintenance.inventory.filters.all') }}</option>
              <option v-for="operation in operationTypes" :key="operation" :value="operation">{{ operation }}</option>
            </select>
          </label>
          <label>
            <span>{{ t('maintenance.inventory.filters.status') }}</span>
            <select v-model="transactionFilters.status">
              <option value="">{{ t('maintenance.inventory.filters.all') }}</option>
              <option v-for="status in transactionStatuses" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <TextFilter v-model="transactionFilters.referenceType" :label="t('maintenance.inventory.filters.referenceType')" />
          <TextFilter v-model="transactionFilters.referenceId" :label="t('maintenance.inventory.filters.referenceId')" />
        </template>

        <button type="button" :disabled="activeLoading" @click="applyFilters">
          {{ t('maintenance.inventory.workspace.apply') }}
        </button>
      </div>

      <InventoryListToolbar
        :loading="activeLoading"
        :sort-by="activeSortBy"
        :sort-order="activeSortOrder"
        @refresh="refreshActive"
        @sort-change="applySort"
      >
        <option v-for="option in activeSortOptions" :key="option" :value="option">
          {{ option }}
        </option>
      </InventoryListToolbar>
    </section>

    <MaintenanceErrorState
      v-if="activeError"
      :error="activeError"
      :locale="locale"
      @retry="refreshActive"
    />

    <div v-if="activeLoading && activeItems.length === 0" class="inventory-workspace__loading">
      {{ t('maintenance.inventory.workspace.loading') }}
    </div>

    <MaintenanceEmptyState
      v-else-if="activeItems.length === 0"
      :title="t('maintenance.inventory.workspace.emptyTitle')"
      :description="t('maintenance.inventory.workspace.emptyDescription')"
    />

    <template v-else>
      <InventoryBalanceTable
        v-if="activeTab === 'balances'"
        :items="inventory.balances.items"
        :loading="inventory.balances.loading"
        @open="openBalance"
      />

      <div v-else class="inventory-workspace__table-wrap" :aria-busy="activeLoading">
        <table v-if="activeTab === 'reservations'">
          <thead><tr><th>ID</th><th>{{ t('maintenance.inventory.columns.status') }}</th><th>{{ t('maintenance.inventory.columns.owner') }}</th><th>{{ t('maintenance.inventory.columns.reserved') }}</th><th>{{ t('maintenance.inventory.columns.expiresAt') }}</th><th>{{ t('maintenance.inventory.columns.version') }}</th><th>{{ t('maintenance.inventory.columns.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="item in inventory.reservations.items" :key="item.id">
              <td>#{{ item.id }}</td><td><MaintenanceStatusTag :status="item.status" /></td><td>{{ item.owner_type }} / {{ item.owner_id }}</td><td>{{ item.reserved_quantity }}</td><td>{{ item.expires_at || '—' }}</td><td>{{ item.version }}</td><td><button type="button" @click="openReservation(item.id)">{{ t('maintenance.inventory.columns.open') }}</button></td>
            </tr>
          </tbody>
        </table>

        <table v-else-if="activeTab === 'transfers'">
          <thead><tr><th>ID</th><th>{{ t('maintenance.inventory.columns.status') }}</th><th>{{ t('maintenance.inventory.columns.source') }}</th><th>{{ t('maintenance.inventory.columns.target') }}</th><th>{{ t('maintenance.inventory.columns.reference') }}</th><th>{{ t('maintenance.inventory.columns.version') }}</th><th>{{ t('maintenance.inventory.columns.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="item in inventory.transfers.items" :key="item.id">
              <td>#{{ item.id }}</td><td><MaintenanceStatusTag :status="item.status" /></td><td>#{{ item.source_warehouse_id }} / #{{ item.source_location_id }}</td><td>#{{ item.target_warehouse_id }} / #{{ item.target_location_id }}</td><td>{{ referenceLabel(item.reference_type, item.reference_id) }}</td><td>{{ item.version }}</td><td><button type="button" @click="openTransfer(item.id)">{{ t('maintenance.inventory.columns.open') }}</button></td>
            </tr>
          </tbody>
        </table>

        <table v-else-if="activeTab === 'stocktakes'">
          <thead><tr><th>ID</th><th>{{ t('maintenance.inventory.columns.status') }}</th><th>{{ t('maintenance.inventory.columns.warehouse') }}</th><th>{{ t('maintenance.inventory.columns.location') }}</th><th>{{ t('maintenance.inventory.columns.snapshotAt') }}</th><th>{{ t('maintenance.inventory.columns.version') }}</th><th>{{ t('maintenance.inventory.columns.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="item in inventory.stocktakes.items" :key="item.id">
              <td>#{{ item.id }}</td><td><MaintenanceStatusTag :status="item.status" /></td><td>#{{ item.warehouse_id }}</td><td>#{{ item.location_id }}</td><td>{{ item.snapshot_at }}</td><td>{{ item.version }}</td><td><button type="button" @click="openStocktake(item.id)">{{ t('maintenance.inventory.columns.open') }}</button></td>
            </tr>
          </tbody>
        </table>

        <table v-else>
          <thead><tr><th>ID</th><th>{{ t('maintenance.inventory.columns.operationType') }}</th><th>{{ t('maintenance.inventory.columns.status') }}</th><th>{{ t('maintenance.inventory.columns.completedAt') }}</th><th>{{ t('maintenance.inventory.columns.version') }}</th><th>{{ t('maintenance.inventory.columns.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="item in inventory.transactions.items" :key="item.id">
              <td>#{{ item.id }}</td><td>{{ item.operation_type }}</td><td><MaintenanceStatusTag :status="item.status" /></td><td>{{ item.completed_at || '—' }}</td><td>{{ item.version }}</td><td><button type="button" @click="openTransaction(item.id)">{{ t('maintenance.inventory.columns.open') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <footer v-if="activePages > 0" class="inventory-workspace__pagination">
      <button type="button" :disabled="activePage <= 1 || activeLoading" @click="setActivePage(activePage - 1)">
        {{ t('maintenance.inventory.workspace.previous') }}
      </button>
      <span>{{ activePage }} / {{ activePages }} · {{ activeTotal }} {{ t('maintenance.inventory.workspace.records') }}</span>
      <button type="button" :disabled="activePage >= activePages || activeLoading" @click="setActivePage(activePage + 1)">
        {{ t('maintenance.inventory.workspace.next') }}
      </button>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type {
  InventoryBalanceListQuery,
  InventoryOperationType,
  InventoryReservationListQuery,
  InventoryReservationStatus,
  InventorySortOrder,
  InventoryStocktakeListQuery,
  InventoryStocktakeStatus,
  InventoryTransactionListQuery,
  InventoryTransactionStatus,
  InventoryTransferListQuery,
  InventoryTransferStatus,
} from '@/api/maintenance/inventory'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import InventoryBalanceTable from '@/components/maintenance/inventory/InventoryBalanceTable.vue'
import InventoryListToolbar from '@/components/maintenance/inventory/InventoryListToolbar.vue'
import {
  INVENTORY_WORKSPACE_TABS,
  type InventoryWorkspaceTab,
} from '@/components/maintenance/inventory/inventory-workflow'
import { useInventoryStore } from '@/stores/maintenance/inventory'

const NumericFilter = defineComponent({
  props: { modelValue: { type: String, required: true }, label: { type: String, required: true } },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('label', [
      h('span', props.label),
      h('input', {
        value: props.modelValue,
        inputmode: 'numeric',
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      }),
    ])
  },
})

const TextFilter = defineComponent({
  props: { modelValue: { type: String, required: true }, label: { type: String, required: true } },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('label', [
      h('span', props.label),
      h('input', {
        value: props.modelValue,
        onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value),
      }),
    ])
  },
})

const { t, locale } = useI18n()
const router = useRouter()
const inventory = useInventoryStore()
const activeTab = ref<InventoryWorkspaceTab>('balances')
const loaded = reactive<Record<InventoryWorkspaceTab, boolean>>({ balances: false, reservations: false, transfers: false, stocktakes: false, transactions: false })

const balanceFilters = reactive({ warehouseId: '', locationId: '', sparePartId: '', lotId: '', serialItemId: '' })
const reservationFilters = reactive<{ status: '' | InventoryReservationStatus; ownerType: string; ownerId: string }>({ status: '', ownerType: '', ownerId: '' })
const transferFilters = reactive<{ status: '' | InventoryTransferStatus; sourceWarehouseId: string; sourceLocationId: string; targetWarehouseId: string; targetLocationId: string; referenceType: string; referenceId: string }>({ status: '', sourceWarehouseId: '', sourceLocationId: '', targetWarehouseId: '', targetLocationId: '', referenceType: '', referenceId: '' })
const stocktakeFilters = reactive<{ status: '' | InventoryStocktakeStatus; warehouseId: string; locationId: string }>({ status: '', warehouseId: '', locationId: '' })
const transactionFilters = reactive<{ operationType: '' | InventoryOperationType; status: '' | InventoryTransactionStatus; referenceType: string; referenceId: string }>({ operationType: '', status: '', referenceType: '', referenceId: '' })

const sortBy = reactive<Record<InventoryWorkspaceTab, string>>({ balances: 'id', reservations: 'id', transfers: 'id', stocktakes: 'id', transactions: 'id' })
const sortOrder = reactive<Record<InventoryWorkspaceTab, InventorySortOrder>>({ balances: 'asc', reservations: 'asc', transfers: 'asc', stocktakes: 'asc', transactions: 'asc' })

const sortOptions: Record<InventoryWorkspaceTab, readonly string[]> = {
  balances: ['id', 'warehouse_id', 'spare_part_id', 'location_id', 'lot_id', 'on_hand_quantity', 'reserved_quantity', 'available_quantity'],
  reservations: ['id', 'status', 'expires_at'],
  transfers: ['id', 'status', 'dispatched_at', 'completed_at'],
  stocktakes: ['id', 'status', 'snapshot_at', 'confirmed_at'],
  transactions: ['id', 'operation_type', 'status', 'completed_at'],
}

const reservationStatuses: InventoryReservationStatus[] = ['ACTIVE', 'PARTIALLY_ISSUED', 'FULFILLED', 'RELEASED', 'CANCELLED', 'EXPIRED']
const transferStatuses: InventoryTransferStatus[] = ['DRAFT', 'DISPATCHED', 'PARTIALLY_RECEIVED', 'COMPLETED', 'CANCELLED']
const stocktakeStatuses: InventoryStocktakeStatus[] = ['DRAFT', 'COUNTING', 'REVIEWING', 'CONFIRMED', 'CONFLICTED', 'CANCELLED']
const transactionStatuses: InventoryTransactionStatus[] = ['PREVIEWED', 'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'EXPIRED', 'REVERSED']
const operationTypes: InventoryOperationType[] = ['OPENING', 'ADJUST', 'RESERVE', 'UNRESERVE', 'ISSUE', 'RETURN', 'TRANSFER_DISPATCH', 'TRANSFER_RECEIVE', 'FREEZE', 'UNFREEZE', 'REVERSE', 'STOCKTAKE_CONFIRM']

const activeSlice = computed(() => inventory[activeTab.value])
const activeItems = computed(() => activeSlice.value.items)
const activeLoading = computed(() => activeSlice.value.loading)
const activeError = computed(() => activeSlice.value.error)
const activePage = computed(() => activeSlice.value.page)
const activePages = computed(() => activeSlice.value.pages)
const activeTotal = computed(() => activeSlice.value.total)
const activeSortBy = computed(() => sortBy[activeTab.value])
const activeSortOrder = computed(() => sortOrder[activeTab.value])
const activeSortOptions = computed(() => sortOptions[activeTab.value])

function positive(value: string): number | undefined {
  if (value.trim() === '') return undefined
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

function text(value: string): string | undefined {
  const trimmed = value.trim()
  return trimmed === '' ? undefined : trimmed
}

function balanceQuery(page = inventory.balances.page): InventoryBalanceListQuery {
  return { page, page_size: inventory.balances.pageSize, warehouse_id: positive(balanceFilters.warehouseId), location_id: positive(balanceFilters.locationId), spare_part_id: positive(balanceFilters.sparePartId), lot_id: positive(balanceFilters.lotId), serial_item_id: positive(balanceFilters.serialItemId), sort_by: sortBy.balances as NonNullable<InventoryBalanceListQuery['sort_by']>, sort_order: sortOrder.balances }
}
function reservationQuery(page = inventory.reservations.page): InventoryReservationListQuery {
  return { page, page_size: inventory.reservations.pageSize, status: reservationFilters.status || undefined, owner_type: text(reservationFilters.ownerType), owner_id: text(reservationFilters.ownerId), sort_by: sortBy.reservations as NonNullable<InventoryReservationListQuery['sort_by']>, sort_order: sortOrder.reservations }
}
function transferQuery(page = inventory.transfers.page): InventoryTransferListQuery {
  return { page, page_size: inventory.transfers.pageSize, status: transferFilters.status || undefined, source_warehouse_id: positive(transferFilters.sourceWarehouseId), source_location_id: positive(transferFilters.sourceLocationId), target_warehouse_id: positive(transferFilters.targetWarehouseId), target_location_id: positive(transferFilters.targetLocationId), reference_type: text(transferFilters.referenceType), reference_id: text(transferFilters.referenceId), sort_by: sortBy.transfers as NonNullable<InventoryTransferListQuery['sort_by']>, sort_order: sortOrder.transfers }
}
function stocktakeQuery(page = inventory.stocktakes.page): InventoryStocktakeListQuery {
  return { page, page_size: inventory.stocktakes.pageSize, status: stocktakeFilters.status || undefined, warehouse_id: positive(stocktakeFilters.warehouseId), location_id: positive(stocktakeFilters.locationId), sort_by: sortBy.stocktakes as NonNullable<InventoryStocktakeListQuery['sort_by']>, sort_order: sortOrder.stocktakes }
}
function transactionQuery(page = inventory.transactions.page): InventoryTransactionListQuery {
  return { page, page_size: inventory.transactions.pageSize, operation_type: transactionFilters.operationType || undefined, status: transactionFilters.status || undefined, reference_type: text(transactionFilters.referenceType), reference_id: text(transactionFilters.referenceId), sort_by: sortBy.transactions as NonNullable<InventoryTransactionListQuery['sort_by']>, sort_order: sortOrder.transactions }
}

async function fetchBalances(page = inventory.balances.page): Promise<void> { await inventory.fetchBalances(balanceQuery(page)); loaded.balances = true }
async function fetchReservations(page = inventory.reservations.page): Promise<void> { await inventory.fetchReservations(reservationQuery(page)); loaded.reservations = true }
async function fetchTransfers(page = inventory.transfers.page): Promise<void> { await inventory.fetchTransfers(transferQuery(page)); loaded.transfers = true }
async function fetchStocktakes(page = inventory.stocktakes.page): Promise<void> { await inventory.fetchStocktakes(stocktakeQuery(page)); loaded.stocktakes = true }
async function fetchTransactions(page = inventory.transactions.page): Promise<void> { await inventory.fetchTransactions(transactionQuery(page)); loaded.transactions = true }

function loadActive(force = false): void {
  if (!force && loaded[activeTab.value]) return
  const loaders: Record<InventoryWorkspaceTab, () => Promise<void>> = { balances: () => fetchBalances(), reservations: () => fetchReservations(), transfers: () => fetchTransfers(), stocktakes: () => fetchStocktakes(), transactions: () => fetchTransactions() }
  void loaders[activeTab.value]()
}
function refreshActive(): void { loadActive(true) }
function applyFilters(): void { setActivePage(1) }
function applySort(value: { sortBy: string; sortOrder: InventorySortOrder }): void {
  if (!sortOptions[activeTab.value].includes(value.sortBy)) return
  sortBy[activeTab.value] = value.sortBy
  sortOrder[activeTab.value] = value.sortOrder
  setActivePage(1)
}
function setActivePage(page: number): void {
  const loaders: Record<InventoryWorkspaceTab, (value: number) => Promise<void>> = { balances: fetchBalances, reservations: fetchReservations, transfers: fetchTransfers, stocktakes: fetchStocktakes, transactions: fetchTransactions }
  void loaders[activeTab.value](page)
}

function openBalance(id: number): void { void router.push({ name: 'maintenanceInventoryBalanceDetail', params: { balanceId: id } }) }
function openReservation(id: number): void { void router.push({ name: 'maintenanceInventoryReservationDetail', params: { reservationId: id } }) }
function openTransfer(id: number): void { void router.push({ name: 'maintenanceInventoryTransferDetail', params: { transferId: id } }) }
function openStocktake(id: number): void { void router.push({ name: 'maintenanceInventoryStocktakeDetail', params: { stocktakeId: id } }) }
function openTransaction(id: number): void { void router.push({ name: 'maintenanceInventoryTransactionDetail', params: { transactionId: id } }) }
function referenceLabel(type: string | null, id: string | null): string { return type === null && id === null ? '—' : `${type ?? '—'} / ${id ?? '—'}` }

watch(activeTab, () => loadActive())
onMounted(() => loadActive())
</script>

<style scoped>
.inventory-workspace { max-width: 1440px; margin: 0 auto; padding: 32px; }
.inventory-workspace__tabs { display: flex; gap: 8px; margin: 0 0 16px; border-bottom: 1px solid var(--td-component-stroke); }
.inventory-workspace__tabs button, .inventory-workspace__controls button, .inventory-workspace__table-wrap button, .inventory-workspace__pagination button { min-height: 36px; padding: 0 12px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); cursor: pointer; }
.inventory-workspace__tabs button { border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.inventory-workspace__tabs .inventory-workspace__tab--active { border-color: var(--td-brand-color); color: var(--td-brand-color); font-weight: 600; }
.inventory-workspace__controls { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 16px; margin-bottom: 16px; padding: 16px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.inventory-workspace__filters { display: flex; flex: 1 1 620px; flex-wrap: wrap; align-items: end; gap: 10px; }
.inventory-workspace__filters :deep(label) { display: grid; gap: 5px; min-width: 145px; color: var(--td-text-color-secondary); font-size: 11px; }
.inventory-workspace__filters :deep(input), .inventory-workspace__filters select { min-height: 36px; padding: 0 10px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); }
.inventory-workspace__loading { padding: 32px; color: var(--td-text-color-secondary); text-align: center; }
.inventory-workspace__table-wrap { overflow-x: auto; }
.inventory-workspace__table-wrap table { width: 100%; border-collapse: collapse; white-space: nowrap; }
.inventory-workspace__table-wrap th, .inventory-workspace__table-wrap td { padding: 10px 12px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
.inventory-workspace__table-wrap th { color: var(--td-text-color-secondary); font-weight: 600; }
.inventory-workspace__pagination { display: flex; align-items: center; justify-content: center; gap: 14px; margin-top: 18px; color: var(--td-text-color-secondary); font-size: 12px; }
</style>
