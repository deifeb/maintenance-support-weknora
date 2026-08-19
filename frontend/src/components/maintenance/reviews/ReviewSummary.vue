<template>
  <section class="review-summary">
    <article>
      <span>{{ t('maintenance.review.summary.status') }}</span>
      <strong>{{ review.status }}</strong>
    </article>
    <article>
      <span>{{ t('maintenance.review.summary.total') }}</span>
      <strong>{{ review.total_finding_count }}</strong>
    </article>
    <article>
      <span>{{ t('maintenance.review.summary.blocking') }}</span>
      <strong>{{ review.blocking_finding_count }}</strong>
    </article>
    <article>
      <span>{{ t('maintenance.review.summary.pending') }}</span>
      <strong>{{ review.pending_finding_count }}</strong>
    </article>
    <article>
      <span>{{ t('maintenance.review.summary.pendingBlocking') }}</span>
      <strong>{{ review.pending_blocking_finding_count }}</strong>
    </article>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type {
  DemandReviewSummaryRead,
} from '@/api/maintenance/demand-reviews'

defineProps<{
  review: DemandReviewSummaryRead
}>()

const { t } = useI18n()
</script>

<style scoped>
.review-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 12px;
}

.review-summary article {
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--td-component-border);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.review-summary span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.review-summary strong {
  font-size: 20px;
}

@media (max-width: 900px) {
  .review-summary {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
</style>
