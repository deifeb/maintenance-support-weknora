<template>
  <section class="transfer-workflow">
    <header class="transfer-workflow__header">
      <div>
        <p>{{ t('maintenance.inventory.transfer.eyebrow') }}</p>
        <h2>{{ currentTransfer
          ? t('maintenance.inventory.transfer.manageTitle', { id: currentTransfer.id })
          : t('maintenance.inventory.transfer.createTitle') }}</h2>
      </div>
      <button v-if="closable" type="button" :disabled="busy" @click="emit('close')">
        {{ t('maintenance.inventory.transfer.close') }}
      </button>
    </header>

    <p v-if="localError" class="transfer-workflow__error" role="alert">{{ localError }}</p>
    <p v-if="conflictMessage" class="transfer-workflow__error" role="alert">{{ conflictMessage }}</p>

    <form v-if="!currentTransfer" class="transfer-workflow__form" @submit.prevent="submitCreate">
      <div class="transfer-workflow__source-picker transfer-workflow__wide">
        <label>
          <span>{{ t('maintenance.inventory.transfer.fields.sourceBalance') }}</span>
          <select v-model.number="selectedSourceBalanceId" :disabled="busy">
            <option :value="null">{{ t('maintenance.inventory.transfer.fields.chooseSourceBalance') }}</option>
            <option v-for="balance in sourceBalances" :key="balance.id" :value="balance.id">
              #{{ balance.id }} · W#{{ balance.warehouse_id }} / L#{{ balance.location_id }} · part #{{ balance.spare_part_id }} · v{{ balance.version }}
            </option>
          </select>
        </label>
        <button type="button" :disabled="busy || selectedSourceBalanceId === null" @click="addSourceLine">
          {{ t('maintenance.inventory.transfer.actions.addLine') }}
        </button>
      </div>

      <div v-if="createLines.length" class="transfer-workflow__lines transfer-workflow__wide">
        <table>
          <thead><tr><th>source_balance_id</th><th>{{ t('maintenance.inventory.columns.part') }}</th><th>expected_source_version</th><th>{{ t('maintenance.inventory.transfer.fields.quantity') }}</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(line, index) in createLines" :key="line.balance.id">
              <td>#{{ line.balance.id }}</td>
              <td>#{{ line.balance.spare_part_id }}</td>
              <td>{{ line.balance.version }}</td>
              <td><input v-model="line.quantity" type="text" inputmode="decimal" placeholder="1.0000" :disabled="busy"></td>
              <td><button type="button" :disabled="busy" @click="createLines.splice(index, 1)">{{ t('maintenance.inventory.transfer.actions.removeLine') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>

      <label>
        <span>{{ t('maintenance.inventory.transfer.fields.targetWarehouse') }}</span>
        <input v-model.number="form.target_warehouse_id" type="number" min="1" :disabled="busy">
      </label>
      <label>
        <span>{{ t('maintenance.inventory.transfer.fields.targetLocation') }}</span>
        <input v-model.number="form.target_location_id" type="number" min="1" :disabled="busy">
      </label>
      <label>
        <span>{{ t('maintenance.inventory.transfer.fields.referenceType') }}</span>
        <input v-model="form.reference_type" type="text" :disabled="busy">
      </label>
      <label>
        <span>{{ t('maintenance.inventory.transfer.fields.referenceId') }}</span>
        <input v-model="form.reference_id" type="text" :disabled="busy">
      </label>
      <label class="transfer-workflow__wide">
        <span>{{ t('maintenance.inventory.transfer.fields.reason') }}</span>
        <textarea v-model="form.reason" :disabled="busy" />
      </label>
      <footer class="transfer-workflow__actions transfer-workflow__wide">
        <button type="submit" :disabled="busy || !permissions.transferInventory">
          {{ t('maintenance.inventory.transfer.actions.create') }}
        </button>
      </footer>
    </form>

    <template v-else>
      <div class="transfer-workflow__lifecycle-actions">
        <button
          v-for="action in availableActions"
          :key="action"
          type="button"
          :disabled="busy"
          @click="selectAction(action)"
        >
          {{ t(`maintenance.inventory.transfer.actions.${action}`) }}
        </button>
      </div>

      <section v-if="activeAction === 'receive' && receivable" class="transfer-workflow__receive">
        <h3>{{ t('maintenance.inventory.transfer.receiveTitle') }}</h3>
        <table>
          <thead><tr><th>ID</th><th>{{ t('maintenance.inventory.detail.requestedQuantity') }}</th><th>{{ t('maintenance.inventory.detail.receivedQuantity') }}</th><th>{{ t('maintenance.inventory.transfer.fields.receiveQuantity') }}</th></tr></thead>
          <tbody>
            <tr v-for="line in currentTransfer.lines" :key="line.id">
              <td>#{{ line.id }}</td>
              <td>{{ line.requested_quantity }}</td>
              <td>{{ line.received_quantity }}</td>
              <td><input v-model="receiveQuantities[line.id]" type="text" inputmode="decimal" placeholder="1.0000" :disabled="busy"></td>
            </tr>
          </tbody>
        </table>
        <footer class="transfer-workflow__actions">
          <button type="button" :disabled="busy" @click="activeAction = null">{{ t('maintenance.inventory.transfer.actions.back') }}</button>
          <button type="button" :disabled="busy" @click="previewReceive">{{ t('maintenance.inventory.transfer.actions.previewReceive') }}</button>
        </footer>
      </section>
    </template>

    <InventoryOperationPreviewDialog
      :open="preview !== null"
      :command-summary="commandSummary"
      :preview="preview"
      :busy="busy"
      :can-execute="inventory.canExecutePreview"
      :error="localError"
      @close="closePreview"
      @execute="executePreview"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  InventoryBalanceRead,
  InventoryOperationPreviewRead,
  InventoryTransferRead,
} from '@/api/maintenance/inventory'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'
import InventoryOperationPreviewDialog from './InventoryOperationPreviewDialog.vue'
import {
  isPositiveDecimal18_4,
  transferActions,
  type TransferUiAction,
} from './inventory-workflow'

interface CreateTransferLine {
  balance: InventoryBalanceRead
  quantity: string
}

interface TransferCreateForm {
  target_warehouse_id: number | null
  target_location_id: number | null
  reference_type: string
  reference_id: string
  reason: string
}

const props = withDefaults(defineProps<{
  transfer?: InventoryTransferRead | null
  sourceBalances?: InventoryBalanceRead[]
  closable?: boolean
}>(), {
  transfer: null,
  sourceBalances: () => [],
  closable: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved', value: InventoryTransferRead): void
}>()

const { t } = useI18n()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()
const permissions = computed(() => permissionStore.permissions)
const sourceBalances = computed(() => props.sourceBalances ?? [])
const createdTransfer = ref<InventoryTransferRead | null>(null)
const currentTransfer = computed(() => props.transfer ?? createdTransfer.value)
const availableActions = computed(() => (
  currentTransfer.value === null
    ? []
    : transferActions(currentTransfer.value.status, permissions.value)
))
const receivable = computed(() => (
  currentTransfer.value?.status === 'DISPATCHED'
  || currentTransfer.value?.status === 'PARTIALLY_RECEIVED'
))
const busy = computed(() => inventory.commandState.phase === 'running')
const conflictMessage = computed(() => (
  inventory.commandState.phase === 'conflicted'
    ? inventory.commandState.error.message
    : ''
))

const form = reactive<TransferCreateForm>({
  target_warehouse_id: null,
  target_location_id: null,
  reference_type: '',
  reference_id: '',
  reason: '',
})
const selectedSourceBalanceId = ref<number | null>(null)
const createLines = reactive<CreateTransferLine[]>([])
const receiveQuantities = reactive<Record<number, string>>({})
const activeAction = ref<TransferUiAction | null>(null)
const preview = ref<InventoryOperationPreviewRead | null>(null)
const previewKind = ref<'dispatch' | 'receive' | null>(null)
const commandSummary = ref('')
const localError = ref('')

watch(
  () => sourceBalances.value,
  (balances) => {
    if (selectedSourceBalanceId.value === null && balances.length > 0) {
      selectedSourceBalanceId.value = balances[0].id
    }
    if (createLines.length === 0 && balances.length === 1) {
      createLines.push({ balance: balances[0], quantity: '' })
    }
  },
  { immediate: true, deep: true },
)

watch(
  currentTransfer,
  (transfer) => {
    if (transfer === null) return
    for (const line of transfer.lines) {
      if (receiveQuantities[line.id] === undefined) receiveQuantities[line.id] = ''
    }
  },
  { immediate: true },
)

function addSourceLine(): void {
  const balance = sourceBalances.value.find((candidate) => candidate.id === selectedSourceBalanceId.value)
  if (balance === undefined || createLines.some((line) => line.balance.id === balance.id)) return
  createLines.push({ balance, quantity: '' })
}

function validateCreate(): string | null {
  if (createLines.length === 0) return t('maintenance.inventory.transfer.validation.sourceLine')
  const source = createLines[0].balance
  if (createLines.some((line) => line.balance.warehouse_id !== source.warehouse_id || line.balance.location_id !== source.location_id)) {
    return t('maintenance.inventory.transfer.validation.sourceContext')
  }
  if (form.target_warehouse_id === null || form.target_location_id === null) {
    return t('maintenance.inventory.transfer.validation.target')
  }
  if (!form.reason.trim()) return t('maintenance.inventory.transfer.validation.reason')
  if (createLines.some((line) => !isPositiveDecimal18_4(line.quantity))) {
    return t('maintenance.inventory.transfer.validation.quantity')
  }
  return null
}

async function submitCreate(): Promise<void> {
  localError.value = ''
  const validation = validateCreate()
  if (validation !== null) {
    localError.value = validation
    return
  }

  const source = createLines[0].balance
  try {
    const result = await inventory.createTransfer({
      source_warehouse_id: source.warehouse_id,
      source_location_id: source.location_id,
      target_warehouse_id: form.target_warehouse_id as number,
      target_location_id: form.target_location_id as number,
      reference_type: form.reference_type.trim() || null,
      reference_id: form.reference_id.trim() || null,
      reason: form.reason.trim(),
      lines: createLines.map((line) => ({
        spare_part_id: line.balance.spare_part_id,
        source_balance_id: line.balance.id,
        lot_id: line.balance.lot_id,
        serial_item_id: line.balance.serial_item_id,
        quantity: line.quantity,
        expected_source_version: line.balance.version,
      })),
    })
    createdTransfer.value = result
    emit('saved', result)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : t('maintenance.inventory.transfer.validation.commandFailed')
  }
}

function selectAction(action: TransferUiAction): void {
  localError.value = ''
  if (action === 'dispatch') {
    void previewDispatch()
    return
  }
  if (action === 'cancel') {
    void cancelTransfer()
    return
  }
  activeAction.value = action
}

async function previewDispatch(): Promise<void> {
  const transfer = currentTransfer.value
  if (transfer === null) return
  localError.value = ''
  try {
    preview.value = await inventory.previewTransferDispatch(transfer.id, {
      expected_version: transfer.version,
    })
    previewKind.value = 'dispatch'
    commandSummary.value = JSON.stringify({
      action: 'TRANSFER_DISPATCH',
      transfer_id: transfer.id,
      expected_version: transfer.version,
    }, null, 2)
  } catch (error) {
    preview.value = null
    localError.value = error instanceof Error ? error.message : t('maintenance.inventory.transfer.validation.commandFailed')
  }
}

async function previewReceive(): Promise<void> {
  const transfer = currentTransfer.value
  if (transfer === null || !receivable.value) return
  localError.value = ''
  const lines = transfer.lines
    .map((line) => ({
      transfer_line_id: line.id,
      quantity: receiveQuantities[line.id] ?? '',
    }))
    .filter((line) => line.quantity.trim().length > 0)

  if (lines.length === 0 || lines.some((line) => !isPositiveDecimal18_4(line.quantity))) {
    localError.value = t('maintenance.inventory.transfer.validation.receiveQuantity')
    return
  }

  try {
    preview.value = await inventory.previewTransferReceive(transfer.id, {
      expected_version: transfer.version,
      lines,
    })
    previewKind.value = 'receive'
    commandSummary.value = JSON.stringify({
      action: 'TRANSFER_RECEIVE',
      transfer_id: transfer.id,
      expected_version: transfer.version,
      lines,
    }, null, 2)
  } catch (error) {
    preview.value = null
    localError.value = error instanceof Error ? error.message : t('maintenance.inventory.transfer.validation.commandFailed')
  }
}

async function executePreview(): Promise<void> {
  localError.value = ''
  try {
    let result: InventoryTransferRead
    if (previewKind.value === 'dispatch') {
      result = await inventory.executeTransferDispatch()
    } else if (previewKind.value === 'receive') {
      result = await inventory.executeTransferReceive()
    } else {
      return
    }
    createdTransfer.value = result
    preview.value = null
    previewKind.value = null
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    preview.value = null
    previewKind.value = null
    localError.value = error instanceof Error ? error.message : t('maintenance.inventory.transfer.validation.commandFailed')
  }
}

async function cancelTransfer(): Promise<void> {
  const transfer = currentTransfer.value
  if (transfer === null) return
  localError.value = ''
  try {
    const result = await inventory.cancelTransfer(transfer.id, {
      expected_version: transfer.version,
    })
    createdTransfer.value = result
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    localError.value = error instanceof Error ? error.message : t('maintenance.inventory.transfer.validation.commandFailed')
  }
}

function closePreview(): void {
  preview.value = null
  previewKind.value = null
}
</script>

<style scoped>
.transfer-workflow { margin-top: 20px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.transfer-workflow__header, .transfer-workflow__source-picker, .transfer-workflow__actions, .transfer-workflow__lifecycle-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.transfer-workflow__header p { margin: 0; color: var(--td-text-color-secondary); font-size: 11px; letter-spacing: .08em; }
.transfer-workflow__header h2 { margin: 4px 0 0; font-size: 18px; }
.transfer-workflow__form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.transfer-workflow__form label { display: grid; gap: 6px; }
.transfer-workflow__wide { grid-column: 1 / -1; }
.transfer-workflow__source-picker label { flex: 1; }
.transfer-workflow__lines { overflow-x: auto; }
.transfer-workflow table { width: 100%; border-collapse: collapse; }
.transfer-workflow th, .transfer-workflow td { padding: 8px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
.transfer-workflow__lifecycle-actions { justify-content: flex-start; margin-top: 16px; }
.transfer-workflow__receive { margin-top: 16px; }
.transfer-workflow__actions { justify-content: flex-end; margin-top: 14px; }
.transfer-workflow__error { color: var(--td-error-color); }
</style>
