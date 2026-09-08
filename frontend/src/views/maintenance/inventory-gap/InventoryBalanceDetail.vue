<template>
  <main class="inventory-detail">
    <button type="button" class="inventory-detail__back" @click="back">
      ← {{ t('maintenance.inventory.detail.back') }}
    </button>

    <MaintenanceEmptyState
      v-if="invalidRoute"
      :title="t('maintenance.inventory.detail.invalid')"
      :description="t('maintenance.inventory.detail.missingDescription')"
    />
    <template v-else>
      <MaintenanceErrorState v-if="inventory.balanceDetail.error" :error="inventory.balanceDetail.error" :locale="locale" @retry="load" />
      <div v-if="inventory.balanceDetail.loading && !current" class="inventory-detail__loading">{{ t('maintenance.inventory.detail.loading') }}</div>
      <MaintenanceEmptyState v-else-if="!current && !inventory.balanceDetail.loading && !inventory.balanceDetail.error" :title="t('maintenance.inventory.detail.missing')" :description="t('maintenance.inventory.detail.missingDescription')" />

      <template v-if="current">
        <MaintenancePageHeader :title="`Balance #${current.id}`" :description="`${t('maintenance.inventory.detail.version')}: ${current.version}`">
          <template #primaryActions>
            <button v-if="canReserve" type="button" @click="reservationOpen = true">
              {{ t('maintenance.inventory.reservation.reserve') }}
            </button>
            <button v-if="permissions.transferInventory" type="button" @click="transferOpen = !transferOpen">
              {{ t('maintenance.inventory.transfer.actions.create') }}
            </button>
            <button v-if="canAdjust" type="button" @click="openAdjustWorkflow">
              {{ t('maintenance.inventory.operations.actions.adjust') }}
            </button>
            <button
              v-if="lotState.available && canLotAction"
              type="button"
              @click="openLotWorkflow"
            >
              {{ t(`maintenance.inventory.operations.actions.${lotState.action}`) }}
            </button>
          </template>
        </MaintenancePageHeader>
        <section class="inventory-detail__facts">
          <article><span>{{ t('maintenance.inventory.columns.warehouse') }}</span><strong>#{{ current.warehouse_id }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.location') }}</span><strong>#{{ current.location_id }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.part') }}</span><strong>#{{ current.spare_part_id }}</strong></article>
          <article><span>lot_id</span><strong>{{ current.lot_id === null ? t('maintenance.inventory.detail.unavailable') : `#${current.lot_id}` }}</strong></article>
          <article><span>lot_version</span><strong>{{ current.lot_version === null ? t('maintenance.inventory.detail.unavailable') : current.lot_version }}</strong></article>
          <article><span>lot_is_frozen</span><strong>{{ lotFrozen }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.serial') }}</span><strong>{{ current.serial_item_id === null ? '—' : `#${current.serial_item_id}` }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.onHand') }}</span><strong>{{ current.on_hand_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.reserved') }}</span><strong>{{ current.reserved_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.damaged') }}</span><strong>{{ current.damaged_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.quarantined') }}</span><strong>{{ current.quarantined_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.inTransit') }}</span><strong>{{ current.in_transit_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.available') }}</span><strong>{{ current.available_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.version') }}</span><strong>{{ current.version }}</strong></article>
        </section>

        <p v-if="!lotState.available && current.lot_id !== null" class="inventory-detail__notice">
          {{ t('maintenance.inventory.operations.lotConcurrencyUnavailable') }}
        </p>

        <section v-if="operationMode" class="inventory-detail__operation">
          <h2>{{ operationMode === 'adjust'
            ? t('maintenance.inventory.operations.adjustTitle')
            : t(`maintenance.inventory.operations.${lotState.available ? lotState.action : 'freeze'}Title`) }}</h2>
          <label>
            <span>{{ t('maintenance.inventory.operations.fields.reason') }}</span>
            <textarea v-model="operationReason" :disabled="commandBusy" />
          </label>
          <div v-if="operationMode === 'adjust'" class="inventory-detail__deltas">
            <label><span>on_hand</span><input v-model="adjustDeltas.on_hand" type="text" inputmode="decimal" :disabled="commandBusy"></label>
            <label><span>reserved</span><input v-model="adjustDeltas.reserved" type="text" inputmode="decimal" :disabled="commandBusy"></label>
            <label><span>damaged</span><input v-model="adjustDeltas.damaged" type="text" inputmode="decimal" :disabled="commandBusy"></label>
            <label><span>quarantined</span><input v-model="adjustDeltas.quarantined" type="text" inputmode="decimal" :disabled="commandBusy"></label>
            <label><span>in_transit</span><input v-model="adjustDeltas.in_transit" type="text" inputmode="decimal" :disabled="commandBusy"></label>
          </div>
          <p v-if="operationError" class="inventory-detail__error" role="alert">{{ operationError }}</p>
          <div class="inventory-detail__operation-actions">
            <button type="button" :disabled="commandBusy" @click="operationMode = null">{{ t('maintenance.inventory.operations.actions.cancel') }}</button>
            <button type="button" :disabled="commandBusy" @click="previewHighRisk">{{ t('maintenance.inventory.operations.actions.preview') }}</button>
          </div>
        </section>

        <TransferWorkflow
          v-if="transferOpen"
          :source-balances="[current]"
          :closable="true"
          @close="transferOpen = false"
          @saved="handleTransferSaved"
        />

        <ReservationDialog
          :open="reservationOpen"
          :balance="current"
          @close="reservationOpen = false"
          @saved="handleReservationSaved"
        />

        <InventoryOperationPreviewDialog
          :open="operationPreview !== null"
          :command-summary="commandSummary"
          :preview="operationPreview"
          :busy="commandBusy"
          :can-execute="inventory.canExecutePreview"
          :error="operationError"
          @close="closeOperationPreview"
          @execute="executeHighRisk"
        />
      </template>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import InventoryOperationPreviewDialog from '@/components/maintenance/inventory/InventoryOperationPreviewDialog.vue'
import ReservationDialog from '@/components/maintenance/inventory/ReservationDialog.vue'
import TransferWorkflow from '@/components/maintenance/inventory/TransferWorkflow.vue'
import {
  buildLotStatePreviewRequest,
  canExecuteHighRisk,
  lotFreezeUiState,
  positiveInventoryRouteId,
  SIGNED_DECIMAL_18_4,
} from '@/components/maintenance/inventory/inventory-workflow'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()

type OperationPreview = Awaited<ReturnType<typeof inventory.previewOperation>>
type OperationPreviewRequest = Parameters<typeof inventory.previewOperation>[0]
type AdjustPreviewRequest = Extract<OperationPreviewRequest, { operation_type: 'ADJUST' }>
type TransferRead = Awaited<ReturnType<typeof inventory.createTransfer>>
const permissions = computed(() => permissionStore.permissions)
const reservationOpen = ref(false)
const transferOpen = ref(false)
const routeId = computed(() => positiveInventoryRouteId(route.params.balanceId))
const invalidRoute = computed(() => routeId.value === null)
const current = computed(() => inventory.balanceDetail.item)
const lotState = computed(() => current.value === null
  ? { available: false as const, reason: 'NO_LOT' as const }
  : lotFreezeUiState(current.value))
const canReserve = computed(() => permissions.value.reserveInventory)
const canAdjust = computed(() => canExecuteHighRisk('adjust', permissions.value))
const canLotAction = computed(() => (
  lotState.value.available
  && canExecuteHighRisk(lotState.value.action, permissions.value)
))
const commandBusy = computed(() => inventory.commandState.phase === 'running')
const lotFrozen = computed(() => {
  if (current.value?.lot_is_frozen === null || current.value === null) {
    return t('maintenance.inventory.detail.unavailable')
  }
  return current.value.lot_is_frozen
    ? t('maintenance.inventory.detail.yes')
    : t('maintenance.inventory.detail.no')
})

const operationMode = ref<'adjust' | 'lot' | null>(null)
const operationReason = ref('')
const operationError = ref('')
const operationPreview = ref<OperationPreview | null>(null)
const commandSummary = ref('')
const adjustDeltas = reactive({
  on_hand: '0',
  reserved: '0',
  damaged: '0',
  quarantined: '0',
  in_transit: '0',
})

function load(): void {
  if (routeId.value === null) return
  void inventory.fetchBalanceDetail(routeId.value)
}
function handleReservationSaved(): void {
  if (current.value !== null) void inventory.fetchBalanceDetail(current.value.id)
}
function handleTransferSaved(value: TransferRead): void {
  transferOpen.value = false
  void router.push({ name: 'maintenanceInventoryTransferDetail', params: { transferId: value.id } })
}
function back(): void { void router.push({ name: 'maintenanceInventoryGap' }) }

function openAdjustWorkflow(): void {
  operationMode.value = 'adjust'
  operationReason.value = ''
  operationError.value = ''
}

function openLotWorkflow(): void {
  if (!lotState.value.available || !canLotAction.value) return
  operationMode.value = 'lot'
  operationReason.value = ''
  operationError.value = ''
}

function adjustRequest(): AdjustPreviewRequest | null {
  const balance = current.value
  if (balance === null) return null
  if (!Object.values(adjustDeltas).every((value) => SIGNED_DECIMAL_18_4.test(value))) {
    operationError.value = t('maintenance.inventory.operations.validation.delta')
    return null
  }
  return {
    operation_type: 'ADJUST',
    balance_id: balance.id,
    expected_balance_version: balance.version,
    reason: operationReason.value.trim(),
    deltas: {
      on_hand: adjustDeltas.on_hand,
      reserved: adjustDeltas.reserved,
      damaged: adjustDeltas.damaged,
      quarantined: adjustDeltas.quarantined,
      in_transit: adjustDeltas.in_transit,
    },
  }
}

async function previewHighRisk(): Promise<void> {
  const balance = current.value
  if (balance === null || !operationReason.value.trim()) {
    operationError.value = t('maintenance.inventory.operations.validation.reason')
    return
  }

  let request: OperationPreviewRequest | null = null
  if (operationMode.value === 'adjust') {
    if (!canExecuteHighRisk('adjust', permissions.value)) return
    request = adjustRequest()
  } else if (operationMode.value === 'lot') {
    const state = lotFreezeUiState(balance)
    if (!state.available || !canExecuteHighRisk(state.action, permissions.value)) return
    request = buildLotStatePreviewRequest(balance, operationReason.value.trim())
  }
  if (request === null) {
    operationError.value ||= t('maintenance.inventory.operations.validation.authority')
    return
  }

  operationError.value = ''
  commandSummary.value = JSON.stringify(request, null, 2)
  try {
    operationPreview.value = await inventory.previewOperation(request)
  } catch (error) {
    operationPreview.value = null
    operationError.value = error instanceof Error ? error.message : t('maintenance.inventory.operations.validation.commandFailed')
  }
}

async function executeHighRisk(): Promise<void> {
  operationError.value = ''
  try {
    await inventory.executeOperation()
    operationPreview.value = null
    operationMode.value = null
    operationReason.value = ''
  } catch (error) {
    operationPreview.value = null
    operationError.value = error instanceof Error ? error.message : t('maintenance.inventory.operations.validation.commandFailed')
  }
}

function closeOperationPreview(): void {
  operationPreview.value = null
}

watch(() => route.params.balanceId, load, { immediate: true })
</script>

<style scoped>
.inventory-detail { max-width: 1180px; margin: 0 auto; padding: 32px; }
.inventory-detail__back { margin-bottom: 18px; border: 0; background: transparent; color: var(--td-brand-color); cursor: pointer; }
.inventory-detail__loading { padding: 24px; color: var(--td-text-color-secondary); }
.inventory-detail__facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.inventory-detail__facts article { display: grid; gap: 6px; padding: 14px; border: 1px solid var(--td-component-stroke); border-radius: 7px; background: var(--td-bg-color-container); }
.inventory-detail__facts span { color: var(--td-text-color-secondary); font-size: 11px; }
.inventory-detail__facts strong { color: var(--td-text-color-primary); font-size: 13px; }
.inventory-detail__notice { margin-top: 14px; color: var(--td-warning-color); }
.inventory-detail__operation { margin-top: 20px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.inventory-detail__operation label { display: grid; gap: 6px; }
.inventory-detail__deltas { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 12px; }
.inventory-detail__operation-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.inventory-detail__error { color: var(--td-error-color); }
</style>
