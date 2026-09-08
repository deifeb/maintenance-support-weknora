<template>
  <main class="inventory-detail">
    <button type="button" class="inventory-detail__back" @click="back">← {{ t('maintenance.inventory.detail.back') }}</button>
    <MaintenanceEmptyState v-if="invalidRoute" :title="t('maintenance.inventory.detail.invalid')" :description="t('maintenance.inventory.detail.missingDescription')" />
    <template v-else>
      <MaintenanceErrorState v-if="inventory.stocktakeDetail.error" :error="inventory.stocktakeDetail.error" :locale="locale" @retry="load" />
      <div v-if="inventory.stocktakeDetail.loading && !current" class="inventory-detail__loading">{{ t('maintenance.inventory.detail.loading') }}</div>
      <MaintenanceEmptyState v-else-if="!current && !inventory.stocktakeDetail.loading && !inventory.stocktakeDetail.error" :title="t('maintenance.inventory.detail.missing')" :description="t('maintenance.inventory.detail.missingDescription')" />
      <template v-if="current">
        <MaintenancePageHeader :title="`Stocktake #${current.id}`" :description="`${t('maintenance.inventory.detail.version')}: ${current.version}`">
          <template #secondaryActions><MaintenanceStatusTag :status="current.status" /></template>
        </MaintenancePageHeader>
        <section class="inventory-detail__facts">
          <article><span>{{ t('maintenance.inventory.columns.warehouse') }}</span><strong>#{{ current.warehouse_id }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.location') }}</span><strong>#{{ current.location_id }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.snapshotAt') }}</span><strong>{{ current.snapshot_at }}</strong></article>
          <article><span>{{ t('maintenance.inventory.columns.version') }}</span><strong>{{ current.version }}</strong></article>
        </section>
        <section class="inventory-detail__section">
          <h2>{{ t('maintenance.inventory.detail.lines') }}</h2>
          <div class="inventory-detail__table-wrap"><table><thead><tr><th>ID</th><th>balance_id</th><th>{{ t('maintenance.inventory.columns.part') }}</th><th>lot_id</th><th>serial_item_id</th><th>{{ t('maintenance.inventory.detail.systemQuantity') }}</th><th>{{ t('maintenance.inventory.detail.countedQuantity') }}</th><th>{{ t('maintenance.inventory.detail.varianceQuantity') }}</th><th>{{ t('maintenance.inventory.detail.resolution') }}</th><th>{{ t('maintenance.inventory.columns.version') }}</th></tr></thead><tbody><tr v-for="line in current.lines" :key="line.id"><td>#{{ line.id }}</td><td>#{{ line.balance_id }}</td><td>#{{ line.spare_part_id }}</td><td>{{ idLabel(line.lot_id) }}</td><td>{{ idLabel(line.serial_item_id) }}</td><td>{{ line.system_quantity }}</td><td>{{ line.counted_quantity === null ? '—' : line.counted_quantity }}</td><td>{{ line.variance_quantity === null ? '—' : line.variance_quantity }}</td><td>{{ line.resolution }}</td><td>{{ line.version }}</td></tr></tbody></table></div>
        </section>

        <StocktakeWorkflow
          :stocktake="current"
          @saved="handleSaved"
          @created="handleCreated"
        />
      </template>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import StocktakeWorkflow from '@/components/maintenance/inventory/StocktakeWorkflow.vue'
import { positiveInventoryRouteId } from '@/components/maintenance/inventory/inventory-workflow'
import { useInventoryStore } from '@/stores/maintenance/inventory'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const inventory = useInventoryStore()
const routeId = computed(() => positiveInventoryRouteId(route.params.stocktakeId))
const invalidRoute = computed(() => routeId.value === null)
const current = computed(() => inventory.stocktakeDetail.item)
type StocktakeRead = NonNullable<typeof current.value>
function idLabel(value: number | null): string { return value === null ? '—' : `#${value}` }
function handleSaved(_value: StocktakeRead): void {}
function handleCreated(value: StocktakeRead): void {
  void router.push({
    name: 'maintenanceInventoryStocktakeDetail',
    params: { stocktakeId: value.id },
  })
}
function load(): void { if (routeId.value !== null) void inventory.fetchStocktakeDetail(routeId.value) }
function back(): void { void router.push({ name: 'maintenanceInventoryGap' }) }
watch(() => route.params.stocktakeId, load, { immediate: true })
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
