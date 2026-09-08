<template>
  <main class="inventory-detail">
    <button type="button" class="inventory-detail__back" @click="back">← {{ t('maintenance.inventory.detail.back') }}</button>
    <MaintenanceEmptyState v-if="invalidRoute" :title="t('maintenance.inventory.detail.invalid')" :description="t('maintenance.inventory.detail.missingDescription')" />
    <template v-else>
      <MaintenanceErrorState v-if="inventory.transactionDetail.error" :error="inventory.transactionDetail.error" :locale="locale" @retry="load" />
      <div v-if="inventory.transactionDetail.loading && !current" class="inventory-detail__loading">{{ t('maintenance.inventory.detail.loading') }}</div>
      <MaintenanceEmptyState v-else-if="!current && !inventory.transactionDetail.loading && !inventory.transactionDetail.error" :title="t('maintenance.inventory.detail.missing')" :description="t('maintenance.inventory.detail.missingDescription')" />
      <template v-if="current">
        <MaintenancePageHeader :title="`Transaction #${current.id}`" :description="`${t('maintenance.inventory.detail.version')}: ${current.version}`">
          <template #primaryActions>
            <button v-if="canReverse" type="button" @click="reverseOpen = !reverseOpen">
              {{ t('maintenance.inventory.operations.actions.reverse') }}
            </button>
          </template>
          <template #secondaryActions><MaintenanceStatusTag :status="current.status" /></template>
        </MaintenancePageHeader>
        <section class="inventory-detail__facts">
          <article><span>{{ t('maintenance.inventory.columns.operationType') }}</span><strong>{{ current.operation_type }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.completedAt') }}</span><strong>{{ current.completed_at || '—' }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.version') }}</span><strong>{{ current.version }}</strong></article>
          <article><span>reason</span><strong>{{ current.reason }}</strong></article>
        </section>

        <section v-if="reverseOpen" class="inventory-detail__reverse">
          <h2>{{ t('maintenance.inventory.operations.reverseTitle') }}</h2>
          <label>
            <span>{{ t('maintenance.inventory.operations.fields.reason') }}</span>
            <textarea v-model="reverseReason" :disabled="commandBusy" />
          </label>
          <p v-if="reverseError" class="inventory-detail__error" role="alert">{{ reverseError }}</p>
          <div class="inventory-detail__actions">
            <button type="button" :disabled="commandBusy" @click="reverseOpen = false">{{ t('maintenance.inventory.operations.actions.cancel') }}</button>
            <button type="button" :disabled="commandBusy" @click="previewReverse">{{ t('maintenance.inventory.operations.actions.preview') }}</button>
          </div>
        </section>

        <section class="inventory-detail__section">
          <h2>{{ t('maintenance.inventory.detail.entries') }}</h2>
          <article v-for="entry in current.entries" :key="entry.id" class="inventory-detail__entry">
            <header><strong>#{{ entry.id }}</strong><span>balance #{{ entry.balance_id }}</span><span>{{ t('maintenance.inventory.detail.beforeVersion') }} {{ entry.before_balance_version }}</span><span>{{ t('maintenance.inventory.detail.resultingVersion') }} {{ entry.resulting_balance_version }}</span></header>
            <div class="inventory-detail__deltas">
              <span>on_hand {{ entry.on_hand_delta }}</span><span>reserved {{ entry.reserved_delta }}</span><span>damaged {{ entry.damaged_delta }}</span><span>quarantined {{ entry.quarantined_delta }}</span><span>in_transit {{ entry.in_transit_delta }}</span>
            </div>
            <div class="inventory-detail__states">
              <div><h3>{{ t('maintenance.inventory.detail.stateBefore') }} · state_before_json</h3><pre>{{ formatJson(entry.state_before_json) }}</pre></div>
              <div><h3>{{ t('maintenance.inventory.detail.stateAfter') }} · state_after_json</h3><pre>{{ formatJson(entry.state_after_json) }}</pre></div>
            </div>
          </article>
        </section>

        <InventoryOperationPreviewDialog
          :open="reversePreview !== null"
          :command-summary="reverseSummary"
          :preview="reversePreview"
          :busy="commandBusy"
          :can-execute="inventory.canExecutePreview"
          :error="reverseError"
          @close="closeReversePreview"
          @execute="executeReverse"
        />
      </template>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import InventoryOperationPreviewDialog from '@/components/maintenance/inventory/InventoryOperationPreviewDialog.vue'
import {
  canExecuteHighRisk,
  positiveInventoryRouteId,
} from '@/components/maintenance/inventory/inventory-workflow'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()

type ReversePreview = Awaited<ReturnType<typeof inventory.previewReverse>>
const routeId = computed(() => positiveInventoryRouteId(route.params.transactionId))
const invalidRoute = computed(() => routeId.value === null)
const current = computed(() => inventory.transactionDetail.item)
const canReverse = computed(() => canExecuteHighRisk('reverse', permissionStore.permissions))
const commandBusy = computed(() => inventory.commandState.phase === 'running')
const reverseOpen = ref(false)
const reverseReason = ref('')
const reverseError = ref('')
const reversePreview = ref<ReversePreview | null>(null)
const reverseSummary = ref('')

function formatJson(value: Record<string, unknown>): string { return JSON.stringify(value, null, 2) }
function load(): void { if (routeId.value !== null) void inventory.fetchTransactionDetail(routeId.value) }
function back(): void { void router.push({ name: 'maintenanceInventoryGap' }) }

async function previewReverse(): Promise<void> {
  const transaction = current.value
  if (transaction === null || !canReverse.value) return
  const reason = reverseReason.value.trim()
  if (!reason) {
    reverseError.value = t('maintenance.inventory.operations.validation.reason')
    return
  }

  const request = {
    expected_transaction_version: transaction.version,
    reason,
  }
  reverseSummary.value = JSON.stringify({
    action: 'REVERSE',
    transaction_id: transaction.id,
    ...request,
  }, null, 2)
  reverseError.value = ''
  try {
    reversePreview.value = await inventory.previewReverse(transaction.id, request)
  } catch (error) {
    reversePreview.value = null
    reverseError.value = error instanceof Error ? error.message : t('maintenance.inventory.operations.validation.commandFailed')
  }
}

async function executeReverse(): Promise<void> {
  reverseError.value = ''
  try {
    await inventory.executeReverse()
    reversePreview.value = null
    reverseOpen.value = false
    reverseReason.value = ''
  } catch (error) {
    reversePreview.value = null
    reverseError.value = error instanceof Error ? error.message : t('maintenance.inventory.operations.validation.commandFailed')
  }
}

function closeReversePreview(): void {
  reversePreview.value = null
}

watch(() => route.params.transactionId, load, { immediate: true })
</script>

<style scoped>
.inventory-detail { max-width: 1280px; margin: 0 auto; padding: 32px; }
.inventory-detail__back { margin-bottom: 18px; border: 0; background: transparent; color: var(--td-brand-color); cursor: pointer; }
.inventory-detail__loading { padding: 24px; color: var(--td-text-color-secondary); }
.inventory-detail__facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.inventory-detail__facts article { display: grid; gap: 6px; padding: 14px; border: 1px solid var(--td-component-stroke); border-radius: 7px; background: var(--td-bg-color-container); }
.inventory-detail__facts span { color: var(--td-text-color-secondary); font-size: 11px; }
.inventory-detail__reverse { margin-top: 20px; padding: 18px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.inventory-detail__reverse label { display: grid; gap: 6px; }
.inventory-detail__actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 12px; }
.inventory-detail__error { color: var(--td-error-color); }
.inventory-detail__section { margin-top: 22px; }
.inventory-detail__entry { margin-top: 12px; padding: 16px; border: 1px solid var(--td-component-stroke); border-radius: 8px; background: var(--td-bg-color-container); }
.inventory-detail__entry header, .inventory-detail__deltas { display: flex; flex-wrap: wrap; gap: 12px; }
.inventory-detail__deltas { margin-top: 10px; font-family: "Roboto Mono", monospace; font-size: 12px; }
.inventory-detail__states { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 12px; }
.inventory-detail__states pre { overflow: auto; padding: 12px; border-radius: 6px; background: var(--td-bg-color-page); font-size: 11px; }
</style>
