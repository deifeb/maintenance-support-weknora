<template>
  <section class="recommendation-panel">
    <header>
      <div>
        <span class="recommendation-panel__eyebrow">
          {{ t('maintenance.calculation.recommendation.eyebrow') }}
        </span>
        <h2>{{ t('maintenance.calculation.recommendation.title') }}</h2>
      </div>
      <code v-if="recommendation">
        {{ recommendation.rule_version }}
      </code>
    </header>

    <p v-if="loading" class="recommendation-panel__message">
      {{ t('maintenance.calculation.recommendation.loading') }}
    </p>
    <p
      v-else-if="!recommendation?.primary"
      class="recommendation-panel__message"
    >
      {{ t('maintenance.calculation.recommendation.empty') }}
    </p>
    <article v-else class="recommendation-panel__primary">
      <div>
        <span>{{ t('maintenance.calculation.recommendation.primary') }}</span>
        <strong>{{ recommendation.primary.candidate_key }}</strong>
      </div>
      <dl>
        <div>
          <dt>{{ t('maintenance.calculation.fields.score') }}</dt>
          <dd>{{ recommendation.primary.score }}</dd>
        </div>
        <div>
          <dt>{{ t('maintenance.calculation.fields.risk') }}</dt>
          <dd>{{ recommendation.primary.risk }}</dd>
        </div>
      </dl>
      <ul>
        <li
          v-for="reason in recommendation.primary.reasons"
          :key="reason"
        >
          {{ reason }}
        </li>
      </ul>
    </article>

    <div
      v-if="recommendation?.warnings.length"
      class="recommendation-panel__warnings"
    >
      <strong>{{ t('maintenance.calculation.fields.warnings') }}</strong>
      <span>{{ recommendation.warnings.length }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type {
  ModelRecommendationSet,
} from '@/api/maintenance/model-recommendations'

withDefaults(
  defineProps<{
    recommendation: ModelRecommendationSet | null
    loading?: boolean
  }>(),
  {
    loading: false,
  },
)

const { t } = useI18n()
</script>

<style scoped>
.recommendation-panel {
  padding: 20px;
  border: 1px solid var(--td-component-stroke);
  border-left: 4px solid var(--td-brand-color);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.recommendation-panel > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.recommendation-panel__eyebrow {
  color: var(--td-brand-color);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}

.recommendation-panel h2 {
  margin: 4px 0 0;
  color: var(--td-text-color-primary);
  font-size: 18px;
}

.recommendation-panel code {
  padding: 5px 8px;
  border-radius: 4px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-size: 10px;
}

.recommendation-panel__message {
  margin: 20px 0 0;
  color: var(--td-text-color-secondary);
}

.recommendation-panel__primary {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: 14px 24px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--td-component-stroke);
}

.recommendation-panel__primary span,
.recommendation-panel dt {
  display: block;
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  letter-spacing: .05em;
  text-transform: uppercase;
}

.recommendation-panel__primary strong {
  display: block;
  margin-top: 5px;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 15px;
}

.recommendation-panel dl {
  display: flex;
  gap: 22px;
  margin: 0;
}

.recommendation-panel dd {
  margin: 5px 0 0;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-weight: 700;
}

.recommendation-panel ul {
  grid-column: 1 / -1;
  margin: 0;
  padding-left: 18px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
  line-height: 1.7;
}

.recommendation-panel__warnings {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 5px;
  background: var(--td-warning-color-1);
  color: var(--td-warning-color);
  font-size: 12px;
}
</style>
