<template>
  <section v-if="open" class="reservation-dialog" role="dialog" aria-modal="true">
    <div class="reservation-dialog__panel">
      <header class="reservation-dialog__header">
        <div>
          <p>{{ t('maintenance.inventory.reservation.eyebrow') }}</p>
          <h2>
            {{ reservation
              ? t('maintenance.inventory.reservation.manageTitle', { id: reservation.id })
              : t('maintenance.inventory.reservation.createTitle') }}
          </h2>
        </div>
        <button type="button" @click="close">{{ t('maintenance.inventory.reservation.close') }}</button>
      </header>

      <p v-if="localError" class="reservation-dialog__error" role="alert">
        {{ localError }}
      </p>

      <section v-if="conflictError" class="reservation-dialog__conflict" role="alert">
        <h3>{{ t('maintenance.inventory.reservation.conflict.title') }}</h3>
        <p>{{ conflictError.message }}</p>
        <dl>
          <template v-if="conflictField('expected_version') !== undefined">
            <dt>expected_version</dt><dd>{{ conflictField('expected_version') }}</dd>
          </template>
          <template v-if="conflictField('actual_version') !== undefined">
            <dt>actual_version</dt><dd>{{ conflictField('actual_version') }}</dd>
          </template>
          <template v-if="conflictField('affected_lines') !== undefined">
            <dt>affected_lines</dt><dd><code>{{ jsonValue(conflictField('affected_lines')) }}</code></dd>
          </template>
          <template v-if="conflictField('suggested_action') !== undefined">
            <dt>suggested_action</dt><dd>{{ conflictField('suggested_action') }}</dd>
          </template>
        </dl>
        <button type="button" :disabled="busy" @click="reloadAuthority">
          {{ t('maintenance.inventory.reservation.conflict.reload') }}
        </button>
      </section>

      <form v-if="!reservation" class="reservation-dialog__form" @submit.prevent="submitReservation">
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.ownerType') }}</span>
          <input v-model="form.owner_type" type="text" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.ownerId') }}</span>
          <input v-model="form.owner_id" type="text" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.sparePartId') }}</span>
          <input v-model.number="form.spare_part_id" type="number" min="1" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.warehouseId') }}</span>
          <input v-model.number="form.warehouse_id" type="number" min="1" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.quantity') }}</span>
          <input v-model="form.requested_quantity" type="text" inputmode="decimal" placeholder="1.0000" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.asOf') }}</span>
          <input v-model="form.as_of" type="text" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.expiresAt') }}</span>
          <input v-model="form.expires_at" type="text" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.locationId') }}</span>
          <input v-model.number="form.location_id" type="number" min="1" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.lotId') }}</span>
          <input v-model.number="form.lot_id" type="number" min="1" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.reservation.fields.serialItemId') }}</span>
          <input v-model.number="form.serial_item_id" type="number" min="1" :disabled="busy">
        </label>
        <label class="reservation-dialog__wide">
          <span>{{ t('maintenance.inventory.reservation.fields.overrideReason') }}</span>
          <textarea v-model="form.fefo_override_reason" :disabled="busy" />
        </label>
        <label class="reservation-dialog__check reservation-dialog__wide">
          <input v-model="form.allow_partial" type="checkbox" :disabled="busy">
          <span>{{ t('maintenance.inventory.reservation.fields.allowPartial') }}</span>
        </label>
        <footer class="reservation-dialog__actions reservation-dialog__wide">
          <button type="button" :disabled="busy" @click="close">{{ t('maintenance.inventory.reservation.close') }}</button>
          <button type="submit" :disabled="busy || !permissions.reserveInventory">
            {{ busy ? t('maintenance.inventory.reservation.submitting') : t('maintenance.inventory.reservation.reserve') }}
          </button>
        </footer>
      </form>

      <template v-else>
        <div class="reservation-dialog__lifecycle-actions">
          <button
            v-for="action in availableActions"
            :key="action"
            type="button"
            :class="{ 'is-active': activeAction === action }"
            :disabled="busy"
            @click="selectAction(action)"
          >
            {{ t(`maintenance.inventory.reservation.actions.${action}`) }}
          </button>
        </div>

        <section v-if="activeAction && activeAction !== 'cancel'" class="reservation-dialog__lines">
          <label v-if="activeAction === 'release'" class="reservation-dialog__check">
            <input v-model="releaseAll" type="checkbox" :disabled="busy">
            <span>{{ t('maintenance.inventory.reservation.releaseAll') }}</span>
          </label>

          <table v-if="!(activeAction === 'release' && releaseAll)">
            <thead><tr><th></th><th>ID</th><th>balance_id</th><th>{{ t('maintenance.inventory.reservation.fields.quantity') }}</th></tr></thead>
            <tbody>
              <tr v-for="line in reservation.lines" :key="line.id">
                <td><input v-model="selectedLineIds" type="checkbox" :value="line.id" :disabled="busy"></td>
                <td>#{{ line.id }}</td>
                <td>#{{ line.balance_id }}</td>
                <td><input v-model="lineQuantities[line.id]" type="text" inputmode="decimal" placeholder="1.0000" :disabled="busy"></td>
              </tr>
            </tbody>
          </table>

          <template v-if="activeAction === 'return'">
            <div class="reservation-dialog__return-tools">
              <button type="button" :disabled="busy || issueTransactionsLoading" @click="loadIssueTransactions">
                {{ issueTransactionsLoading
                  ? t('maintenance.inventory.reservation.return.loadingIssues')
                  : t('maintenance.inventory.reservation.return.reloadIssues') }}
              </button>
              <label>
                <span>issue_transaction_id</span>
                <select v-model="selectedIssueTransactionId" :disabled="busy || issueTransactionsLoading">
                  <option :value="null">{{ t('maintenance.inventory.reservation.return.chooseIssue') }}</option>
                  <option v-for="transaction in issueTransactions" :key="transaction.id" :value="transaction.id">
                    #{{ transaction.id }} · {{ transaction.completed_at || transaction.status }}
                  </option>
                </select>
              </label>
            </div>
          </template>
        </section>

        <footer v-if="activeAction" class="reservation-dialog__actions">
          <button type="button" :disabled="busy" @click="activeAction = null">{{ t('maintenance.inventory.reservation.back') }}</button>
          <button type="button" :disabled="busy" @click="submitLifecycleAction">
            {{ t(`maintenance.inventory.reservation.actions.${activeAction}`) }}
          </button>
        </footer>
      </template>

      <FEFOAllocationEvidence v-if="evidenceReservation" :reservation="evidenceReservation" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  InventoryBalanceListQuery,
  InventoryBalanceRead,
  InventoryReservationRead,
  InventoryTransactionListQuery,
  InventoryTransactionRead,
} from '@/api/maintenance/inventory'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'
import FEFOAllocationEvidence from './FEFOAllocationEvidence.vue'
import {
  isZeroDecimal18_4,
  POSITIVE_DECIMAL_18_4,
  reservationActions,
  requiresFefoOverrideReason,
  type ReservationUiAction,
} from './inventory-workflow'

interface ReservationForm {
  owner_type: string
  owner_id: string
  spare_part_id: number | null
  warehouse_id: number | null
  requested_quantity: string
  allow_partial: boolean
  as_of: string
  expires_at: string
  location_id: number | null
  lot_id: number | null
  serial_item_id: number | null
  fefo_override_reason: string
}

const props = withDefaults(defineProps<{
  open: boolean
  balance?: InventoryBalanceRead | null
  reservation?: InventoryReservationRead | null
}>(), {
  balance: null,
  reservation: null,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved', value: InventoryReservationRead): void
}>()

const { t } = useI18n()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()
const permissions = computed(() => permissionStore.permissions)
const reservation = computed(() => props.reservation ?? null)
const busy = computed(() => inventory.commandState.phase === 'running')
const conflictError = computed(() => (
  inventory.commandState.phase === 'conflicted'
    ? inventory.commandState.error
    : null
))
const availableActions = computed(() => (
  reservation.value === null
    ? []
    : reservationActions(reservation.value.status, permissions.value)
))

const form = reactive<ReservationForm>({
  owner_type: '',
  owner_id: '',
  spare_part_id: null,
  warehouse_id: null,
  requested_quantity: '',
  allow_partial: false,
  as_of: '',
  expires_at: '',
  location_id: null,
  lot_id: null,
  serial_item_id: null,
  fefo_override_reason: '',
})
const initializedBalanceId = ref<number | null>(null)
const initializedReservationId = ref<number | null>(null)
const localError = ref('')
const lastReservation = ref<InventoryReservationRead | null>(null)
const activeAction = ref<ReservationUiAction | null>(null)
const selectedLineIds = ref<number[]>([])
const lineQuantities = reactive<Record<number, string>>({})
const releaseAll = ref(true)
const issueTransactions = ref<InventoryTransactionRead[]>([])
const issueTransactionsLoading = ref(false)
const selectedIssueTransactionId = ref<number | null>(null)
const evidenceReservation = computed(() => lastReservation.value ?? reservation.value)

watch(
  () => props.balance ?? null,
  (balance) => {
    if (balance === null || initializedBalanceId.value === balance.id) return
    initializedBalanceId.value = balance.id
    form.spare_part_id = balance.spare_part_id
    form.warehouse_id = balance.warehouse_id
    form.location_id = balance.location_id
    form.lot_id = balance.lot_id
    form.serial_item_id = balance.serial_item_id
    form.as_of = new Date().toISOString()
  },
  { immediate: true },
)

watch(
  () => props.reservation ?? null,
  (value) => {
    if (value === null || initializedReservationId.value === value.id) return
    initializedReservationId.value = value.id
    selectedLineIds.value = []
    for (const line of value.lines) lineQuantities[line.id] = '1.0000'
  },
  { immediate: true },
)

function close(): void {
  emit('close')
}

function optionalPositiveId(value: number | null): number | undefined {
  return value !== null && Number.isInteger(value) && value > 0
    ? value
    : undefined
}

function validateCreateForm(): string | null {
  if (!form.owner_type.trim() || !form.owner_id.trim()) {
    return t('maintenance.inventory.reservation.validation.owner')
  }
  if (form.spare_part_id === null || form.warehouse_id === null) {
    return t('maintenance.inventory.reservation.validation.inventoryContext')
  }
  if (
    !POSITIVE_DECIMAL_18_4.test(form.requested_quantity)
    || isZeroDecimal18_4(form.requested_quantity)
  ) {
    return t('maintenance.inventory.reservation.validation.quantity')
  }
  if (!form.as_of.trim()) {
    return t('maintenance.inventory.reservation.validation.asOf')
  }
  if (
    requiresFefoOverrideReason({
      lot_id: optionalPositiveId(form.lot_id),
      serial_item_id: optionalPositiveId(form.serial_item_id),
      location_id: optionalPositiveId(form.location_id),
    })
    && form.fefo_override_reason.trim().length === 0
  ) {
    return t('maintenance.inventory.reservation.validation.overrideReason')
  }
  return null
}

async function submitReservation(): Promise<void> {
  localError.value = ''
  const validation = validateCreateForm()
  if (validation !== null) {
    localError.value = validation
    return
  }

  const query: InventoryBalanceListQuery = {
    warehouse_id: form.warehouse_id as number,
    spare_part_id: form.spare_part_id as number,
    ...(optionalPositiveId(form.location_id) !== undefined
      ? { location_id: optionalPositiveId(form.location_id) }
      : {}),
    ...(optionalPositiveId(form.lot_id) !== undefined
      ? { lot_id: optionalPositiveId(form.lot_id) }
      : {}),
    ...(optionalPositiveId(form.serial_item_id) !== undefined
      ? { serial_item_id: optionalPositiveId(form.serial_item_id) }
      : {}),
  }

  try {
    const expected_balance_versions = await inventory.collectReservationBalanceVersions(query)
    if (Object.keys(expected_balance_versions).length === 0) {
      localError.value = t('maintenance.inventory.reservation.validation.reloadFilter')
      return
    }
    const result = await inventory.createReservation({
      owner_type: form.owner_type.trim(),
      owner_id: form.owner_id.trim(),
      spare_part_id: form.spare_part_id as number,
      warehouse_id: form.warehouse_id as number,
      requested_quantity: form.requested_quantity,
      allow_partial: form.allow_partial,
      expected_balance_versions,
      as_of: form.as_of.trim(),
      location_id: form.location_id,
      lot_id: form.lot_id,
      serial_item_id: form.serial_item_id,
      expires_at: form.expires_at.trim() || null,
      fefo_override_reason: form.fefo_override_reason.trim() || null,
    })
    lastReservation.value = result
    emit('saved', result)
  } catch (error) {
    localError.value = error instanceof Error
      ? error.message
      : t('maintenance.inventory.reservation.validation.commandFailed')
  }
}

function selectAction(action: ReservationUiAction): void {
  activeAction.value = action
  localError.value = ''
  if (action === 'release') releaseAll.value = true
  if (action === 'return') void loadIssueTransactions()
}

function selectedQuantityLines(): Array<{ reservation_line_id: number; quantity: string }> | null {
  const value = reservation.value
  if (value === null) return null
  const selected = value.lines.filter((line) => selectedLineIds.value.includes(line.id))
  if (selected.length === 0) {
    localError.value = t('maintenance.inventory.reservation.validation.selectLines')
    return null
  }
  const lines = selected.map((line) => ({
    reservation_line_id: line.id,
    quantity: lineQuantities[line.id] ?? '',
  }))
  if (lines.some((line) => !POSITIVE_DECIMAL_18_4.test(line.quantity) || isZeroDecimal18_4(line.quantity))) {
    localError.value = t('maintenance.inventory.reservation.validation.quantity')
    return null
  }
  return lines
}

async function loadIssueTransactions(): Promise<void> {
  if (props.reservation == null) return
  issueTransactionsLoading.value = true
  localError.value = ''
  const reservation = props.reservation
  const query: InventoryTransactionListQuery = {
    operation_type: 'ISSUE',
    reference_type: 'INVENTORY_RESERVATION',
    reference_id: String(reservation.id),
    sort_by: 'id',
    sort_order: 'desc',
    page: 1,
    page_size: 100,
  }
  let page = query.page as number
  let pages = 1
  const all: InventoryTransactionRead[] = []
  try {
    do {
      await inventory.fetchTransactions({ ...query, page })
      all.push(...inventory.transactions.items)
      pages = inventory.transactions.pages
      page += 1
    } while (page <= pages)
    issueTransactions.value = all
    if (
      selectedIssueTransactionId.value !== null
      && !all.some((item) => item.id === selectedIssueTransactionId.value)
    ) {
      selectedIssueTransactionId.value = null
    }
  } catch (error) {
    localError.value = error instanceof Error
      ? error.message
      : t('maintenance.inventory.reservation.return.loadFailed')
  } finally {
    issueTransactionsLoading.value = false
  }
}

async function submitLifecycleAction(): Promise<void> {
  const value = reservation.value
  const action = activeAction.value
  if (value === null || action === null) return
  localError.value = ''

  try {
    let result: InventoryReservationRead
    if (action === 'cancel') {
      result = await inventory.cancelReservation(value.id, {
        expected_version: value.version,
      })
    } else if (action === 'release' && releaseAll.value) {
      result = await inventory.releaseReservation(value.id, {
        expected_version: value.version,
        lines: [],
      })
    } else {
      const lines = selectedQuantityLines()
      if (lines === null) return
      if (action === 'issue') {
        result = await inventory.issueReservation(value.id, {
          expected_version: value.version,
          lines,
        })
      } else if (action === 'release') {
        result = await inventory.releaseReservation(value.id, {
          expected_version: value.version,
          lines,
        })
      } else {
        if (selectedIssueTransactionId.value === null) {
          localError.value = t('maintenance.inventory.reservation.validation.selectIssue')
          return
        }
        const issue_transaction_id = selectedIssueTransactionId.value
        result = await inventory.returnReservation(value.id, {
          expected_version: value.version,
          lines: lines.map((line) => ({ ...line, issue_transaction_id })),
        })
      }
    }
    lastReservation.value = result
    emit('saved', result)
  } catch (error) {
    localError.value = error instanceof Error
      ? error.message
      : t('maintenance.inventory.reservation.validation.commandFailed')
  }
}

function conflictField(key: string): unknown {
  const details = conflictError.value?.details
  if (details === null || typeof details !== 'object') return undefined
  return (details as Record<string, unknown>)[key]
}

function jsonValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value)
}

async function reloadAuthority(): Promise<void> {
  localError.value = ''
  if (reservation.value !== null) {
    await inventory.fetchReservationDetail(reservation.value.id)
    return
  }
  if (props.balance != null) await inventory.fetchBalanceDetail(props.balance.id)
}
</script>

<style scoped>
.reservation-dialog { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 24px; background: rgb(0 0 0 / 42%); }
.reservation-dialog__panel { width: min(960px, 100%); max-height: 90vh; overflow: auto; padding: 22px; border-radius: 10px; background: var(--td-bg-color-container); box-shadow: var(--td-shadow-3); }
.reservation-dialog__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.reservation-dialog__header p { margin: 0; color: var(--td-text-color-secondary); font-size: 11px; letter-spacing: .08em; }
.reservation-dialog__header h2 { margin: 4px 0 0; font-size: 22px; }
.reservation-dialog button, .reservation-dialog input, .reservation-dialog textarea, .reservation-dialog select { min-height: 36px; border: 1px solid var(--td-component-stroke); border-radius: 5px; background: var(--td-bg-color-container); color: var(--td-text-color-primary); font: inherit; }
.reservation-dialog button { padding: 0 13px; cursor: pointer; }
.reservation-dialog input, .reservation-dialog textarea, .reservation-dialog select { padding: 7px 9px; }
.reservation-dialog__form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.reservation-dialog__form label { display: grid; gap: 5px; color: var(--td-text-color-secondary); font-size: 11px; }
.reservation-dialog__wide { grid-column: 1 / -1; }
.reservation-dialog__check { display: flex !important; align-items: center; gap: 8px; }
.reservation-dialog__check input { min-height: auto; }
.reservation-dialog__actions, .reservation-dialog__lifecycle-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.reservation-dialog__lifecycle-actions { justify-content: flex-start; }
.reservation-dialog__lifecycle-actions .is-active { border-color: var(--td-brand-color); color: var(--td-brand-color); }
.reservation-dialog__error { margin: 16px 0 0; padding: 10px 12px; border-radius: 6px; background: var(--td-error-color-1); color: var(--td-error-color); }
.reservation-dialog__conflict { margin-top: 16px; padding: 14px; border: 1px solid var(--td-warning-color-3); border-radius: 7px; background: var(--td-warning-color-1); }
.reservation-dialog__conflict h3 { margin: 0; font-size: 15px; }
.reservation-dialog__conflict dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 12px; font-size: 12px; }
.reservation-dialog__conflict dt { color: var(--td-text-color-secondary); }
.reservation-dialog__conflict dd { margin: 0; overflow-wrap: anywhere; }
.reservation-dialog__lines { margin-top: 18px; }
.reservation-dialog__lines table { width: 100%; margin-top: 12px; border-collapse: collapse; }
.reservation-dialog__lines th, .reservation-dialog__lines td { padding: 8px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
.reservation-dialog__return-tools { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-top: 14px; }
.reservation-dialog__return-tools label { display: grid; gap: 4px; min-width: 320px; }
@media (max-width: 720px) { .reservation-dialog__form { grid-template-columns: 1fr; } .reservation-dialog__wide { grid-column: auto; } }
</style>
