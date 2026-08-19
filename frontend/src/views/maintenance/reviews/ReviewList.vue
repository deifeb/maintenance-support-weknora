<template>
  <main class="review-list">
    <header class="review-list__header">
      <div>
        <p class="review-list__eyebrow">
          {{ t('maintenance.review.eyebrow') }}
        </p>
        <h1>{{ t('maintenance.review.list.title') }}</h1>
        <p>{{ t('maintenance.review.list.description') }}</p>
      </div>
      <button
        type="button"
        :disabled="reviewStore.reviews.loading || sourceLoading"
        @click="refreshAll"
      >
        {{ t('maintenance.review.actions.refresh') }}
      </button>
    </header>

    <section class="review-list__run-panel">
      <div>
        <h2>{{ t('maintenance.review.source.title') }}</h2>
        <p>{{ t('maintenance.review.source.description') }}</p>
      </div>

      <label>
        <span>{{ t('maintenance.review.source.currentPublished') }}</span>
        <select
          v-model.number="selectedSourceId"
          :disabled="sourceLoading || running"
        >
          <option :value="0">
            {{ t('maintenance.review.source.select') }}
          </option>
          <option
            v-for="source in currentPublishedLists"
            :key="source.id"
            :value="source.id"
          >
            #{{ source.id }} · {{ source.name }} · v{{ source.version_number }}
          </option>
        </select>
      </label>

      <div
        v-if="selectedSource"
        class="review-list__source-facts"
      >
        <span>
          {{ t('maintenance.review.source.status') }}:
          <strong>{{ selectedSource.status }}</strong>
        </span>
        <span>
          {{ t('maintenance.review.source.version') }}:
          <strong>{{ selectedSource.version }}</strong>
        </span>
        <span>
          {{ t('maintenance.review.source.current') }}:
          <strong>{{ selectedSource.is_current ? t('common.yes') : t('common.no') }}</strong>
        </span>
      </div>

      <button
        type="button"
        :disabled="!canRunSelected"
        @click="runSelectedReview"
      >
        {{
          running
            ? t('maintenance.review.actions.running')
            : t('maintenance.review.actions.run')
        }}
      </button>
    </section>

    <p
      v-if="errorMessage"
      class="review-list__error"
      role="alert"
    >
      {{ errorMessage }}
    </p>

    <section class="review-list__table-card">
      <header>
        <div>
          <h2>{{ t('maintenance.review.list.register') }}</h2>
          <p>
            {{
              t('maintenance.review.list.total', {
                count: reviewStore.reviews.total,
              })
            }}
          </p>
        </div>
      </header>

      <div
        v-if="reviewStore.reviews.loading"
        class="review-list__loading"
      >
        {{ t('maintenance.review.list.loading') }}
      </div>

      <div
        v-else-if="reviewStore.reviews.items.length === 0"
        class="review-list__empty"
      >
        {{ t('maintenance.review.list.empty') }}
      </div>

      <div
        v-else
        class="review-list__table-wrap"
      >
        <table>
          <thead>
            <tr>
              <th>{{ t('maintenance.review.list.id') }}</th>
              <th>{{ t('maintenance.review.list.source') }}</th>
              <th>{{ t('maintenance.review.summary.status') }}</th>
              <th>{{ t('maintenance.review.summary.total') }}</th>
              <th>{{ t('maintenance.review.summary.blocking') }}</th>
              <th>{{ t('maintenance.review.summary.pending') }}</th>
              <th>{{ t('maintenance.review.summary.pendingBlocking') }}</th>
              <th>{{ t('maintenance.review.list.updated') }}</th>
              <th>{{ t('maintenance.review.list.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="review in reviewStore.reviews.items"
              :key="review.id"
            >
              <td>#{{ review.id }}</td>
              <td>
                #{{ review.source_demand_list_id }}
                · v{{ review.source_demand_list_version }}
              </td>
              <td>{{ review.status }}</td>
              <td>{{ review.total_finding_count }}</td>
              <td>{{ review.blocking_finding_count }}</td>
              <td>{{ review.pending_finding_count }}</td>
              <td>{{ review.pending_blocking_finding_count }}</td>
              <td>{{ formatDate(review.updated_at) }}</td>
              <td>
                <button
                  type="button"
                  @click="openReview(review.id)"
                >
                  {{ t('maintenance.review.actions.open') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import {
  demandListApi,
  type DemandListSummary,
} from '@/api/maintenance/demand-lists'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import { useDemandReviewStore } from '@/stores/maintenance/demandReview'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const { t } = useI18n()
const router = useRouter()
const reviewStore = useDemandReviewStore()
const permissionStore = useMaintenancePermissionsStore()

const currentPublishedLists = ref<DemandListSummary[]>([])
const selectedSourceId = ref(0)
const sourceLoading = ref(false)
const running = ref(false)
const localError = ref('')

const selectedSource = computed(() => (
  currentPublishedLists.value.find(
    (item) => item.id === selectedSourceId.value,
  ) ?? null
))

const canRunSelected = computed(() => {
  const source = selectedSource.value
  return Boolean(
    source
    && source.status === 'PUBLISHED'
    && source.is_current
    && permissionStore.permissions.handleReview
    && !sourceLoading.value
    && !running.value,
  )
})

const errorMessage = computed(() => (
  localError.value
  || reviewStore.reviews.error?.message
  || ''
))

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString()
}

async function loadCurrentPublishedLists(): Promise<void> {
  sourceLoading.value = true
  localError.value = ''

  try {
    const first = await demandListApi.list({
      page: 1,
      page_size: 100,
      status: 'PUBLISHED',
    })
    const items = [...first.data.items]

    for (let page = 2; page <= first.data.pages; page += 1) {
      const response = await demandListApi.list({
        page,
        page_size: 100,
        status: 'PUBLISHED',
      })
      items.push(...response.data.items)
    }

    currentPublishedLists.value = items.filter(
      (item) => item.status === 'PUBLISHED' && item.is_current,
    )

    if (
      selectedSourceId.value !== 0
      && !currentPublishedLists.value.some(
        (item) => item.id === selectedSourceId.value,
      )
    ) {
      selectedSourceId.value = 0
    }
  } catch (value) {
    localError.value = normalizeMaintenanceError(value).message
    throw value
  } finally {
    sourceLoading.value = false
  }
}

async function loadReviews(): Promise<void> {
  await reviewStore.fetchReviews({
    page: 1,
    page_size: 50,
    sort_by: 'updated_at',
    sort_order: 'desc',
  })
}

async function refreshAll(): Promise<void> {
  localError.value = ''
  await Promise.all([
    loadCurrentPublishedLists(),
    loadReviews(),
  ]).catch(() => undefined)
}

async function runSelectedReview(): Promise<void> {
  const source = selectedSource.value
  if (
    !source
    || source.status !== 'PUBLISHED'
    || !source.is_current
    || !permissionStore.permissions.handleReview
  ) {
    return
  }

  running.value = true
  localError.value = ''

  try {
    const created = await reviewStore.runReview(
      source.id,
      {
        expected_source_version: source.version,
      },
    )
    await loadReviews()
    await router.push({
      name: 'maintenanceReviewDetail',
      params: {
        reviewId: String(created.id),
      },
    })
  } catch (value) {
    localError.value = normalizeMaintenanceError(value).message
  } finally {
    running.value = false
  }
}

function openReview(reviewId: number): void {
  void router.push({
    name: 'maintenanceReviewDetail',
    params: {
      reviewId: String(reviewId),
    },
  })
}

onMounted(() => {
  void refreshAll()
})
</script>

<style scoped>
.review-list {
  display: grid;
  gap: 20px;
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px;
}

.review-list__header,
.review-list__run-panel,
.review-list__table-card {
  border: 1px solid var(--td-component-border);
  border-radius: 12px;
  background: var(--td-bg-color-container);
}

.review-list__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 24px;
}

.review-list__header h1,
.review-list__run-panel h2,
.review-list__table-card h2 {
  margin: 0;
}

.review-list__header p,
.review-list__run-panel p,
.review-list__table-card p {
  color: var(--td-text-color-secondary);
}

.review-list__eyebrow {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.review-list__run-panel {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(260px, 1fr) auto;
  align-items: end;
  gap: 18px;
  padding: 20px 24px;
}

.review-list__run-panel label {
  display: grid;
  gap: 8px;
}

.review-list__run-panel select,
.review-list button {
  min-height: 36px;
}

.review-list__source-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  grid-column: 2 / -1;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.review-list__error {
  margin: 0;
  padding: 12px 16px;
  border: 1px solid var(--td-error-color);
  border-radius: 8px;
  color: var(--td-error-color);
}

.review-list__table-card > header {
  padding: 20px 24px 0;
}

.review-list__table-wrap {
  overflow-x: auto;
  padding: 16px 24px 24px;
}

.review-list table {
  width: 100%;
  border-collapse: collapse;
}

.review-list th,
.review-list td {
  padding: 12px 10px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  white-space: nowrap;
}

.review-list th {
  color: var(--td-text-color-secondary);
  font-size: 12px;
  font-weight: 600;
}

.review-list__loading,
.review-list__empty {
  padding: 32px 24px;
  color: var(--td-text-color-secondary);
}

@media (max-width: 900px) {
  .review-list {
    padding: 20px;
  }

  .review-list__header,
  .review-list__run-panel {
    grid-template-columns: 1fr;
  }

  .review-list__header {
    display: grid;
  }

  .review-list__source-facts {
    grid-column: auto;
  }
}
</style>
