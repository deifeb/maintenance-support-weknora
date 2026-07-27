<template>
  <section class="maintenance-placeholder">
    <h1>{{ t('maintenance.pages.reviews') }}</h1>
    <p>{{ t('maintenance.placeholder') }}</p>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
.maintenance-placeholder {
  max-width: 960px;
  margin: 0 auto;
  padding: 40px 32px;
}

.maintenance-placeholder h1 {
  margin: 0 0 12px;
  color: var(--td-text-color-primary);
  font-size: 28px;
  line-height: 1.3;
}

.maintenance-placeholder p {
  margin: 0;
  color: var(--td-text-color-secondary);
  font-size: 14px;
  line-height: 1.6;
}
</style>
