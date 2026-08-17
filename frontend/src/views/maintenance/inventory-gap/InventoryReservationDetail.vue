<template>
  <main class="inventory-detail">
    <button type="button" class="inventory-detail__back" @click="back">← {{ t('maintenance.inventory.detail.back') }}</button>
    <MaintenanceEmptyState v-if="invalidRoute" :title="t('maintenance.inventory.detail.invalid')" :description="t('maintenance.inventory.detail.missingDescription')" />
    <template v-else>
      <MaintenanceErrorState v-if="inventory.reservationDetail.error" :error="inventory.reservationDetail.error" :locale="locale" @retry="load" />
      <div v-if="inventory.reservationDetail.loading && !current" class="inventory-detail__loading">{{ t('maintenance.inventory.detail.loading') }}</div>
      <MaintenanceEmptyState v-else-if="!current && !inventory.reservationDetail.loading && !inventory.reservationDetail.error" :title="t('maintenance.inventory.detail.missing')" :description="t('maintenance.inventory.detail.missingDescription')" />
      <template v-if="current">
        <MaintenancePageHeader :title="`Reservation #${current.id}`" :description="`${t('maintenance.inventory.detail.version')}: ${current.version}`">
          <template #secondaryActions><MaintenanceStatusTag :status="current.status" /></template>
          <template #primaryActions>
            <button v-if="canManageReservation" type="button" @click="reservationOpen = true">
              {{ t('maintenance.inventory.reservation.manage') }}
            </button>
          </template>
        </MaintenancePageHeader>
        <section class="inventory-detail__facts">
          <article><span>{{ t('maintenance.inventory.columns.owner') }}</span><strong>{{ current.owner_type }} / {{ current.owner_id }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.expiresAt') }}</span><strong>{{ current.expires_at || '—' }}</strong></article>
          <article><span>{{ t('maintenance.inventory.detail.requestedQuantity') }}</span><strong>{{ current.requested_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.detail.reservedQuantity') }}</span><strong>{{ current.reserved_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.detail.issuedQuantity') }}</span><strong>{{ current.issued_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.detail.releasedQuantity') }}</span><strong>{{ current.released_quantity }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.version') }}</span><strong>{{ current.version }}</strong></article>
        </section>
        <FEFOAllocationEvidence :reservation="current" />
        <section class="inventory-detail__section">
          <h2>{{ t('maintenance.inventory.detail.lines') }}</h2>
          <div class="inventory-detail__table-wrap"><table><thead><tr><th>ID</th><th>{{ t('maintenance.inventory.columns.part') }}</th><th>balance_id</th><th>lot_id</th><th>serial_item_id</th><th>{{ t('maintenance.inventory.detail.requestedQuantity') }}</th><th>{{ t('maintenance.inventory.detail.reservedQuantity') }}</th><th>{{ t('maintenance.inventory.detail.issuedQuantity') }}</th><th>{{ t('maintenance.inventory.detail.releasedQuantity') }}</th><th>fefo_rank</th><th>{{ t('maintenance.inventory.columns.version') }}</th></tr></thead><tbody><tr v-for="line in current.lines" :key="line.id"><td>#{{ line.id }}</td><td>#{{ line.spare_part_id }}</td><td>#{{ line.balance_id }}</td><td>{{ idLabel(line.lot_id) }}</td><td>{{ idLabel(line.serial_item_id) }}</td><td>{{ line.requested_quantity }}</td><td>{{ line.reserved_quantity }}</td><td>{{ line.issued_quantity }}</td><td>{{ line.released_quantity }}</td><td>{{ line.fefo_rank }}</td><td>{{ line.version }}</td></tr></tbody></table></div>
        </section>
        <ReservationDialog
          :open="reservationOpen"
          :reservation="current"
          @close="reservationOpen = false"
          @saved="handleReservationSaved"
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
import FEFOAllocationEvidence from '@/components/maintenance/inventory/FEFOAllocationEvidence.vue'
import ReservationDialog from '@/components/maintenance/inventory/ReservationDialog.vue'
import {
  positiveInventoryRouteId,
  reservationActions,
} from '@/components/maintenance/inventory/inventory-workflow'
import { useInventoryStore } from '@/stores/maintenance/inventory'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const inventory = useInventoryStore()
const permissionStore = useMaintenancePermissionsStore()
const reservationOpen = ref(false)
const routeId = computed(() => positiveInventoryRouteId(route.params.reservationId))
const invalidRoute = computed(() => routeId.value === null)
const current = computed(() => inventory.reservationDetail.item)
const canManageReservation = computed(() => (
  current.value !== null
  && reservationActions(
    current.value.status,
    permissionStore.permissions,
  ).length > 0
))
function idLabel(value: number | null): string { return value === null ? '—' : `#${value}` }
function handleReservationSaved(): void {
  if (current.value !== null) void inventory.fetchReservationDetail(current.value.id)
}
function load(): void { if (routeId.value !== null) void inventory.fetchReservationDetail(routeId.value) }
function back(): void { void router.push({ name: 'maintenanceInventoryGap' }) }
watch(() => route.params.reservationId, load, { immediate: true })
</script>

<style scoped>
.inventory-detail { max-width: 1280px; margin: 0 auto; padding: 32px; }
.inventory-detail__back { margin-bottom: 18px; border: 0; background: transparent; color: var(--td-brand-color); cursor: pointer; }
.inventory-detail__loading { padding: 24px; color: var(--td-text-color-secondary); }
.inventory-detail__facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.inventory-detail__facts article { display: grid; gap: 6px; padding: 14px; border: 1px solid var(--td-component-stroke); border-radius: 7px; background: var(--td-bg-color-container); }
.inventory-detail__facts span { color: var(--td-text-color-secondary); font-size: 11px; }
.inventory-detail__section { margin-top: 22px; }
.inventory-detail__table-wrap { overflow-x: auto; }
.inventory-detail table { width: 100%; border-collapse: collapse; white-space: nowrap; }
.inventory-detail th, .inventory-detail td { padding: 9px 10px; border-bottom: 1px solid var(--td-component-stroke); text-align: left; font-size: 12px; }
</style>
