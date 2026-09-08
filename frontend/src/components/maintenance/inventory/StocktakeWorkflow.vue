<template>
  <section class="stocktake-workflow">
    <header class="stocktake-workflow__header">
      <div>
        <p>{{ t('maintenance.inventory.stocktake.eyebrow') }}</p>
        <h2>{{ t('maintenance.inventory.stocktake.manageTitle', { id: stocktake.id }) }}</h2>
      </div>
      <button v-if="closable" type="button" :disabled="busy" @click="emit('close')">
        {{ t('maintenance.inventory.stocktake.close') }}
      </button>
    </header>

    <p class="stocktake-workflow__authority-note">
      {{ t('maintenance.inventory.stocktake.backendAuthority') }}
    </p>
    <p v-if="localError" class="stocktake-workflow__error" role="alert">{{ localError }}</p>
    <p v-if="conflictMessage" class="stocktake-workflow__error" role="alert">{{ conflictMessage }}</p>

    <details v-if="permissions.createStocktake" class="stocktake-workflow__create">
      <summary>{{ t('maintenance.inventory.stocktake.createTitle') }}</summary>
      <form class="stocktake-workflow__create-form" @submit.prevent="createStocktake">
        <label>
          <span>{{ t('maintenance.inventory.stocktake.fields.warehouseId') }}</span>
          <input v-model.number="createForm.warehouse_id" type="number" min="1" :disabled="busy">
        </label>
        <label>
          <span>{{ t('maintenance.inventory.stocktake.fields.locationId') }}</span>
          <input v-model.number="createForm.location_id" type="number" min="1" :disabled="busy">
        </label>
        <button type="submit" :disabled="busy">
          {{ t('maintenance.inventory.stocktake.actions.create') }}
        </button>
      </form>
    </details>

    <div class="stocktake-workflow__lifecycle-actions">
      <button
        v-for="action in availableActions"
        :key="action"
        type="button"
        :disabled="busy"
        @click="selectAction(action)"
      >
        {{ t(`maintenance.inventory.stocktake.actions.${action}`) }}
      </button>
    </div>

    <section v-if="activeAction === 'count'" class="stocktake-workflow__panel">
      <h3>{{ t('maintenance.inventory.stocktake.countTitle') }}</h3>
      <div class="stocktake-workflow__table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>{{ t('maintenance.inventory.detail.systemQuantity') }}</th>
              <th>{{ t('maintenance.inventory.stocktake.fields.expectedLineVersion') }}</th>
              <th>{{ t('maintenance.inventory.stocktake.fields.countedQuantity') }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in lineRows" :key="line.id">
              <td>#{{ line.id }}</td>
              <td>{{ line.systemQuantity }}</td>
              <td>{{ line.version }}</td>
              <td>
                <input
                  v-model="line.countInput"
                  type="text"
                  inputmode="decimal"
                  placeholder="12.5000"
                  :disabled="busy"
                >
              </td>
              <td>
                <button type="button" :disabled="busy" @click="countLine(line)">
                  {{ t('maintenance.inventory.stocktake.actions.saveCount') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="stocktake.lines.some((line) => line.conflict_details !== null)" class="stocktake-workflow__panel">
      <h3>{{ t('maintenance.inventory.stocktake.conflicts.title') }}</h3>
      <article
        v-for="line in stocktake.lines.filter((candidate) => candidate.conflict_details !== null)"
        :key="line.id"
        class="stocktake-workflow__conflict"
      >
        <header>
          <strong>#{{ line.id }}</strong>
          <span>{{ line.resolution }}</span>
        </header>
        <pre>{{ formatConflictDetails(line.conflict_details) }}</pre>
      </article>
    </section>

    <section v-if="activeAction === 'rebase'" class="stocktake-workflow__panel">
      <h3>{{ t('maintenance.inventory.stocktake.rebaseTitle') }}</h3>
      <div class="stocktake-workflow__table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t('maintenance.inventory.stocktake.fields.select') }}</th>
              <th>ID</th>
              <th>{{ t('maintenance.inventory.detail.resolution') }}</th>
              <th>{{ t('maintenance.inventory.stocktake.fields.rebaseAction') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="line in lineRows" :key="line.id">
              <td>
                <input
                  v-model="line.selected"
                  type="checkbox"
                  :disabled="busy || line.resolution === 'ADJUSTED' || line.resolution !== 'CONFLICTED'"
                >
              </td>
              <td>#{{ line.id }}</td>
              <td>{{ line.resolution }}</td>
              <td>
                <select
                  v-model="line.rebaseAction"
                  :disabled="busy || line.resolution === 'ADJUSTED' || line.resolution !== 'CONFLICTED'"
                >
                  <option value="RECOUNT">{{ t('maintenance.inventory.stocktake.rebaseActions.RECOUNT') }}</option>
                  <option value="BASELINE_ACCEPT">{{ t('maintenance.inventory.stocktake.rebaseActions.BASELINE_ACCEPT') }}</option>
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="stocktake-workflow__actions">
        <button type="button" :disabled="busy" @click="activeAction = null">
          {{ t('maintenance.inventory.stocktake.actions.back') }}
        </button>
        <button type="button" :disabled="busy || selectedConflictLines.length === 0" @click="rebaseStocktake">
          {{ t('maintenance.inventory.stocktake.actions.rebase') }}
        </button>
      </footer>
    </section>

    <section v-if="confirmPreview !== null" class="stocktake-workflow__preview" role="dialog" aria-modal="true">
      <h3>{{ t('maintenance.inventory.stocktake.confirmTitle') }}</h3>
      <section>
        <h4>{{ t('maintenance.inventory.operations.preview.commandSummary') }}</h4>
        <pre>{{ confirmSummary }}</pre>
      </section>
      <section>
        <h4>{{ t('maintenance.inventory.operations.preview.serverMetadata') }}</h4>
        <dl>
          <div><dt>transaction_id</dt><dd>{{ confirmPreview.transaction_id }}</dd></div>
          <div><dt>operation_type</dt><dd>{{ confirmPreview.operation_type }}</dd></div>
          <div><dt>transaction_version</dt><dd>{{ confirmPreview.transaction_version }}</dd></div>
          <div><dt>confirmation_expires_at</dt><dd>{{ confirmPreview.confirmation_expires_at }}</dd></div>
        </dl>
      </section>
      <footer class="stocktake-workflow__actions">
        <button type="button" :disabled="busy" @click="confirmPreview = null">
          {{ t('maintenance.inventory.operations.preview.close') }}
        </button>
        <button type="button" :disabled="busy || !inventory.canExecutePreview" @click="executeConfirm">
          {{ t('maintenance.inventory.operations.preview.execute') }}
        </button>
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'
import {
  POSITIVE_DECIMAL_18_4,
  stocktakeActions,
  type StocktakeUiAction,
} from './inventory-workflow'

type InventoryStore = ReturnType<typeof useInventoryStore>
type StocktakeRead = Awaited<ReturnType<InventoryStore['createStocktake']>>
type ConfirmPreviewRead = Awaited<ReturnType<InventoryStore['previewStocktakeConfirm']>>
type ConfirmPreviewMetadata = Pick<
  ConfirmPreviewRead,
  'transaction_id' | 'operation_type' | 'transaction_version' | 'confirmation_expires_at'
>
type RebaseAction = Parameters<InventoryStore['rebaseStocktake']>[1]['lines'][number]['action']

interface StocktakeLineUi {
  id: number
  version: number
  resolution: string
  systemQuantity: string
  countInput: string
  selected: boolean
  rebaseAction: RebaseAction
}

const props = withDefaults(defineProps<{
  stocktake: StocktakeRead
  closable?: boolean
}>(), {
  closable: false,
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'saved', value: StocktakeRead): void
  (event: 'created', value: StocktakeRead): void
}>()

const { t } = useI18n()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()
const permissions = computed(() => permissionStore.permissions)
const busy = computed(() => inventory.commandState.phase === 'running')
const conflictMessage = computed(() => (
  inventory.commandState.phase === 'conflicted'
    ? inventory.commandState.error.message
    : ''
))
const canConfirmHighRisk = computed(() => (
  permissions.value.confirmStocktake
  && permissions.value.confirmHighRisk
))
const availableActions = computed(() => (
  stocktakeActions(props.stocktake.status, permissions.value)
    .filter((action) => action !== 'confirm' || canConfirmHighRisk.value)
))

const createForm = reactive({
  warehouse_id: props.stocktake.warehouse_id,
  location_id: props.stocktake.location_id,
})
const activeAction = ref<StocktakeUiAction | null>(null)
const lineRows = ref<StocktakeLineUi[]>([])
const confirmPreview = ref<ConfirmPreviewMetadata | null>(null)
const confirmSummary = ref('')
const localError = ref('')

const selectedConflictLines = computed(() => (
  lineRows.value.filter((line) => (
    line.resolution === 'CONFLICTED' && line.selected
  ))
))

watch(
  () => props.stocktake.lines,
  (lines) => {
    const previous = new Map(lineRows.value.map((line) => [line.id, line]))
    lineRows.value = lines.map((line) => {
      const existing = previous.get(line.id)
      return {
        id: line.id,
        version: line.version,
        resolution: line.resolution,
        systemQuantity: line.system_quantity,
        countInput: existing?.countInput ?? line.counted_quantity ?? '',
        selected: line.resolution === 'CONFLICTED' ? (existing?.selected ?? false) : false,
        rebaseAction: existing?.rebaseAction ?? 'RECOUNT',
      }
    })
  },
  { immediate: true, deep: true },
)

watch(
  () => [props.stocktake.warehouse_id, props.stocktake.location_id] as const,
  ([warehouseId, locationId]) => {
    createForm.warehouse_id = warehouseId
    createForm.location_id = locationId
  },
)

function setError(error: unknown): void {
  localError.value = error instanceof Error
    ? error.message
    : t('maintenance.inventory.stocktake.validation.commandFailed')
  if (inventory.commandState.phase === 'conflicted') {
    void inventory.fetchStocktakeDetail(props.stocktake.id)
  }
}

async function createStocktake(): Promise<void> {
  localError.value = ''
  if (
    !Number.isInteger(createForm.warehouse_id)
    || createForm.warehouse_id <= 0
    || !Number.isInteger(createForm.location_id)
    || createForm.location_id <= 0
  ) {
    localError.value = t('maintenance.inventory.stocktake.validation.location')
    return
  }

  try {
    const result = await inventory.createStocktake({
      warehouse_id: createForm.warehouse_id,
      location_id: createForm.location_id,
    })
    emit('created', result)
  } catch (error) {
    setError(error)
  }
}

function selectAction(action: StocktakeUiAction): void {
  localError.value = ''
  if (action === 'start') {
    void startStocktake()
    return
  }
  if (action === 'review') {
    void reviewStocktake()
    return
  }
  if (action === 'confirm') {
    void previewStocktakeConfirm()
    return
  }
  if (action === 'cancel') {
    void cancelStocktake()
    return
  }
  activeAction.value = action
}

async function startStocktake(): Promise<void> {
  try {
    const result = await inventory.startStocktake(props.stocktake.id, {
      expected_version: props.stocktake.version,
    })
    emit('saved', result)
  } catch (error) {
    setError(error)
  }
}

async function countLine(line: StocktakeLineUi): Promise<void> {
  localError.value = ''
  if (!POSITIVE_DECIMAL_18_4.test(line.countInput)) {
    localError.value = t('maintenance.inventory.stocktake.validation.countedQuantity')
    return
  }

  const stocktake = props.stocktake
  try {
    const result = await inventory.updateStocktakeLine(stocktake.id, line.id, {
      expected_version: stocktake.version,
      expected_line_version: line.version,
      counted_quantity: line.countInput,
    })
    emit('saved', result)
  } catch (error) {
    setError(error)
  }
}

async function reviewStocktake(): Promise<void> {
  try {
    const result = await inventory.reviewStocktake(props.stocktake.id, {
      expected_version: props.stocktake.version,
    })
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    setError(error)
  }
}

async function previewStocktakeConfirm(): Promise<void> {
  if (!canConfirmHighRisk.value) return
  localError.value = ''
  try {
    const {
      transaction_id,
      operation_type,
      transaction_version,
      confirmation_expires_at,
    } = await inventory.previewStocktakeConfirm(props.stocktake.id, {
      expected_version: props.stocktake.version
    })
    confirmPreview.value = {
      transaction_id,
      operation_type,
      transaction_version,
      confirmation_expires_at,
    }
    confirmSummary.value = JSON.stringify({
      action: 'STOCKTAKE_CONFIRM',
      stocktake_id: props.stocktake.id,
      expected_version: props.stocktake.version,
    }, null, 2)
  } catch (error) {
    confirmPreview.value = null
    setError(error)
  }
}

async function executeConfirm(): Promise<void> {
  if (!canConfirmHighRisk.value || confirmPreview.value === null) return
  localError.value = ''
  try {
    const result = await inventory.executeStocktakeConfirm()
    confirmPreview.value = null
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    confirmPreview.value = null
    setError(error)
  }
}

async function rebaseStocktake(): Promise<void> {
  localError.value = ''
  if (selectedConflictLines.value.length === 0) {
    localError.value = t('maintenance.inventory.stocktake.validation.rebaseLines')
    return
  }

  try {
    const result = await inventory.rebaseStocktake(props.stocktake.id, {
      expected_version: props.stocktake.version,
      lines: selectedConflictLines.value.map((line) => ({
        line_id: line.id,
        action: line.rebaseAction,
      })),
    })
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    setError(error)
  }
}

async function cancelStocktake(): Promise<void> {
  try {
    const result = await inventory.cancelStocktake(props.stocktake.id, {
      expected_version: props.stocktake.version,
    })
    activeAction.value = null
    emit('saved', result)
  } catch (error) {
    setError(error)
  }
}

function formatConflictDetails(value: unknown): string {
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2)
  }
  return String(value ?? '')
}
</script>

<style scoped>
.stocktake-workflow { margin-top: 20px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.stocktake-workflow__header, .stocktake-workflow__lifecycle-actions, .stocktake-workflow__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.stocktake-workflow__header p { margin: 0; color: var(--td-text-color-secondary); font-size: 11px; letter-spacing: .08em; }
.stocktake-workflow__header h2 { margin: 4px 0 0; font-size: 18px; }
.stocktake-workflow__authority-note { color: var(--td-text-color-secondary); font-size: 12px; }
.stocktake-workflow__create { margin-top: 16px; }
.stocktake-workflow__create-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)) auto; align-items: end; gap: 12px; margin-top: 12px; }
.stocktake-workflow__create-form label { display: grid; gap: 6px; }
.stocktake-workflow__lifecycle-actions { justify-content: flex-start; flex-wrap: wrap; margin-top: 16px; }
.stocktake-workflow__panel { margin-top: 18px; }
.stocktake-workflow__table-wrap { overflow-x: auto; }
.stocktake-workflow table { width: 100%; border-collapse: collapse; }
.stocktake-workflow th, .stocktake-workflow td { padding: 8px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
.stocktake-workflow__conflict { margin-top: 10px; padding: 12px; border: 1px solid var(--td-component-stroke); border-radius: 6px; }
.stocktake-workflow__conflict header { display: flex; gap: 12px; }
.stocktake-workflow__conflict pre, .stocktake-workflow__preview pre { overflow: auto; padding: 10px; border-radius: 6px; background: var(--td-bg-color-page); white-space: pre-wrap; }
.stocktake-workflow__preview { margin-top: 18px; padding: 16px; border: 1px solid var(--td-component-stroke); border-radius: 8px; }
.stocktake-workflow__preview dl { display: grid; gap: 8px; }
.stocktake-workflow__preview dl div { display: grid; grid-template-columns: minmax(160px, .7fr) 1fr; gap: 10px; }
.stocktake-workflow__preview dd { margin: 0; }
.stocktake-workflow__actions { justify-content: flex-end; margin-top: 14px; }
.stocktake-workflow__error { color: var(--td-error-color); }
</style>
