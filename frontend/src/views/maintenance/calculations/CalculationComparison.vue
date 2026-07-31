<template>
  <main class="calculation-comparison">
    <MaintenancePageHeader
      :title="t('maintenance.calculation.list.openComparison')"
      :description="t('maintenance.calculation.progress.description')"
    />
  </main>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'

const { t } = useI18n()
</script>

<style scoped>
.calculation-comparison {
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px;
}
</style>
