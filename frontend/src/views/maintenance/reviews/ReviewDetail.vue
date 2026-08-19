<template>
  <main class="review-detail">
    <header class="review-detail__header">
      <div>
        <button
          type="button"
          @click="backToList"
        >
          ← {{ t('maintenance.review.actions.back') }}
        </button>
        <p class="review-detail__eyebrow">
          {{ t('maintenance.review.eyebrow') }}
        </p>
        <h1>
          {{
            review
              ? t('maintenance.review.detail.title', { id: review.id })
              : t('maintenance.review.detail.loadingTitle')
          }}
        </h1>
      </div>
      <button
        type="button"
        :disabled="loading"
        @click="load"
      >
        {{ t('maintenance.review.actions.refresh') }}
      </button>
    </header>

    <p
      v-if="invalidRoute"
      class="review-detail__error"
      role="alert"
    >
      {{ t('maintenance.review.detail.invalidRoute') }}
    </p>

    <p
      v-else-if="errorMessage"
      class="review-detail__error"
      role="alert"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="loading && !review"
      class="review-detail__loading"
    >
      {{ t('maintenance.review.detail.loading') }}
    </div>

    <template v-if="review">
      <ReviewSummary :review="review" />

      <section class="review-detail__source">
        <div>
          <span>{{ t('maintenance.review.detail.source') }}</span>
          <strong>
            #{{ review.source_demand_list_id }}
            · v{{ review.source_demand_list_version }}
          </strong>
        </div>
        <div>
          <span>{{ t('maintenance.review.detail.ruleSet') }}</span>
          <strong>{{ review.rule_set_version }}</strong>
        </div>
        <div>
          <span>{{ t('maintenance.review.detail.version') }}</span>
          <strong>{{ review.version }}</strong>
        </div>
      </section>

      <section
        v-if="commandState.phase === 'conflicted'"
        class="review-detail__conflict"
        role="alert"
      >
        <div>
          <h2>{{ t('maintenance.review.conflict.title') }}</h2>
          <p>{{ commandState.error.message }}</p>
        </div>
        <dl>
          <div>
            <dt>{{ t('maintenance.review.conflict.expected') }}</dt>
            <dd>{{ expectedVersion }}</dd>
          </div>
          <div>
            <dt>{{ t('maintenance.review.conflict.actual') }}</dt>
            <dd>{{ actualVersion }}</dd>
          </div>
          <div>
            <dt>{{ t('maintenance.review.conflict.suggested') }}</dt>
            <dd>{{ suggestedAction }}</dd>
          </div>
        </dl>
        <button
          type="button"
          :disabled="loading"
          @click="reloadAfterConflict"
        >
          {{ t('maintenance.review.conflict.reload') }}
        </button>
      </section>

      <section class="review-detail__workspace">
        <header>
          <div>
            <h2>{{ t('maintenance.review.finding.title') }}</h2>
            <p>{{ t('maintenance.review.finding.description') }}</p>
          </div>
          <button
            type="button"
            :disabled="!canBatchDecide"
            @click="startBatchDecision"
          >
            {{
              t('maintenance.review.actions.batchDecide', {
                count: selectedFindingIds.length,
              })
            }}
          </button>
        </header>

        <FindingTable
          :findings="review.findings"
          :selected-ids="selectedFindingIds"
          :can-handle="permissionStore.permissions.handleReview"
          @update:selected-ids="selectedFindingIds = $event"
          @decide="startSingleDecision"
        />
      </section>

      <section class="review-detail__derive">
        <div>
          <h2>{{ t('maintenance.review.derive.title') }}</h2>
          <p>{{ t('maintenance.review.derive.description') }}</p>
        </div>
        <button
          type="button"
          :disabled="!canDerive"
          @click="derive"
        >
          {{
            mutating
              ? t('maintenance.review.actions.saving')
              : t('maintenance.review.actions.derive')
          }}
        </button>
      </section>
    </template>

    <FindingDecisionDialog
      :open="decisionOpen"
      :finding="decisionTarget"
      :busy="mutating"
      :confirm-high-risk="permissionStore.permissions.confirmHighRisk"
      @cancel="closeDecision"
      @submit="submitDecision"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { normalizeMaintenanceError } from '@/api/maintenance/client'
import type {
  DemandReviewDecisionAction,
  DemandReviewFindingRead,
} from '@/api/maintenance/demand-reviews'
import FindingDecisionDialog from '@/components/maintenance/reviews/FindingDecisionDialog.vue'
import FindingTable from '@/components/maintenance/reviews/FindingTable.vue'
import ReviewSummary from '@/components/maintenance/reviews/ReviewSummary.vue'
import { useDemandReviewStore } from '@/stores/maintenance/demandReview'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

interface DecisionPayload {
  action: DemandReviewDecisionAction
  final_quantity: string | null
  reason: string | null
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const reviewStore = useDemandReviewStore()
const permissionStore = useMaintenancePermissionsStore()

const selectedFindingIds = ref<number[]>([])
const decisionOpen = ref(false)
const decisionTarget = ref<DemandReviewFindingRead | null>(null)
const batchMode = ref(false)
const mutating = ref(false)
const localError = ref('')

const reviewId = computed(() => {
  const value = Array.isArray(route.params.reviewId)
    ? route.params.reviewId[0]
    : route.params.reviewId
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0
    ? parsed
    : null
})

const invalidRoute = computed(() => reviewId.value === null)
const review = computed(() => reviewStore.reviewDetail.item)
const loading = computed(() => reviewStore.reviewDetail.loading)
const commandState = computed(() => reviewStore.commandState)

const errorMessage = computed(() => (
  localError.value
  || reviewStore.reviewDetail.error?.message
  || ''
))

const selectedPendingFindings = computed(() => {
  const selected = new Set(selectedFindingIds.value)
  return (
    review.value?.findings.filter(
      (finding) => (
        selected.has(finding.id)
        && finding.decision_status === 'PENDING'
      ),
    ) ?? []
  )
})

const canBatchDecide = computed(() => (
  permissionStore.permissions.handleReview
  && selectedPendingFindings.value.length > 0
  && !mutating.value
))

const canDerive = computed(() => (
  Boolean(review.value)
  && review.value?.status === 'READY_TO_DERIVE'
  && permissionStore.permissions.finalizeReview
  && !mutating.value
))

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

const conflictDetails = computed<Record<string, unknown> | null>(() => {
  const state = commandState.value
  if (
    state.phase !== 'conflicted'
    || !isRecord(state.error.details)
  ) {
    return null
  }
  return state.error.details
})

const expectedVersion = computed(() => {
  const details = conflictDetails.value
  const value = details?.expected_version
  return typeof value === 'number' || typeof value === 'string'
    ? String(value)
    : '—'
})

const actualVersion = computed(() => {
  const details = conflictDetails.value
  const value = details?.actual_version
  return typeof value === 'number' || typeof value === 'string'
    ? String(value)
    : '—'
})

const suggestedAction = computed(() => {
  const details = conflictDetails.value
  const value = details?.suggested_action ?? details?.suggestedAction
  return typeof value === 'string' && value.trim()
    ? value
    : t('maintenance.review.conflict.reloadHint')
})

async function load(): Promise<void> {
  if (reviewId.value === null) return
  localError.value = ''
  try {
    await reviewStore.fetchReviewDetail(reviewId.value)
    selectedFindingIds.value = selectedFindingIds.value.filter(
      (id) => review.value?.findings.some(
        (finding) => (
          finding.id === id
          && finding.decision_status === 'PENDING'
        ),
      ) ?? false,
    )
  } catch (value) {
    localError.value = normalizeMaintenanceError(value).message
  }
}

function backToList(): void {
  void router.push({
    name: 'maintenanceReviews',
  })
}

function startSingleDecision(
  finding: DemandReviewFindingRead,
): void {
  if (
    !permissionStore.permissions.handleReview
    || finding.decision_status !== 'PENDING'
  ) {
    return
  }
  batchMode.value = false
  decisionTarget.value = finding
  decisionOpen.value = true
}

function startBatchDecision(): void {
  if (!canBatchDecide.value) return
  batchMode.value = true
  decisionTarget.value = selectedPendingFindings.value[0] ?? null
  decisionOpen.value = decisionTarget.value !== null
}

function closeDecision(): void {
  if (mutating.value) return
  decisionOpen.value = false
  decisionTarget.value = null
  batchMode.value = false
}

function highRiskBlocked(
  findings: DemandReviewFindingRead[],
  action: DemandReviewDecisionAction,
): boolean {
  return (
    action !== 'REJECTED'
    && findings.some(
      (finding) => finding.requires_admin_acceptance,
    )
    && !permissionStore.permissions.confirmHighRisk
  )
}

async function submitDecision(
  payload: DecisionPayload,
): Promise<void> {
  const current = review.value
  const target = decisionTarget.value
  if (
    !current
    || !target
    || !permissionStore.permissions.handleReview
  ) {
    return
  }

  const targets = batchMode.value
    ? selectedPendingFindings.value
    : [target]

  if (
    targets.length === 0
    || highRiskBlocked(targets, payload.action)
  ) {
    return
  }

  mutating.value = true
  localError.value = ''

  try {
    if (batchMode.value) {
      await reviewStore.batchDecide(
        current.id,
        {
          expected_review_version: current.version,
          decisions: targets.map((finding) => ({
            finding_id: finding.id,
            expected_finding_version: finding.version,
            action: payload.action,
            final_quantity: payload.final_quantity,
            reason: payload.reason,
          })),
        },
      )
    } else {
      await reviewStore.decideFinding(
        current.id,
        target.id,
        {
          expected_review_version: current.version,
          expected_finding_version: target.version,
          action: payload.action,
          final_quantity: payload.final_quantity,
          reason: payload.reason,
        },
      )
    }

    decisionOpen.value = false
    decisionTarget.value = null
    batchMode.value = false
    selectedFindingIds.value = []
    await reviewStore.fetchReviewDetail(current.id)
  } catch (value) {
    localError.value = normalizeMaintenanceError(value).message
  } finally {
    mutating.value = false
  }
}

async function derive(): Promise<void> {
  const current = review.value
  if (
    !current
    || current.status !== 'READY_TO_DERIVE'
    || !permissionStore.permissions.finalizeReview
  ) {
    return
  }

  const confirmation = window.confirm(
    t('maintenance.review.derive.confirmation'),
  )
  if (!confirmation) return

  mutating.value = true
  localError.value = ''

  try {
    const derived = await reviewStore.deriveReview(
      current.id,
      {
        expected_review_version: current.version,
      },
    )

    if (derived.derived_demand_list_id !== null) {
      await router.push({
        name: 'maintenanceDemandListDetail',
        params: {
          listId: String(derived.derived_demand_list_id),
        },
      })
      return
    }

    await reviewStore.fetchReviewDetail(current.id)
  } catch (value) {
    localError.value = normalizeMaintenanceError(value).message
  } finally {
    mutating.value = false
  }
}

async function reloadAfterConflict(): Promise<void> {
  await load()
}

watch(
  reviewId,
  (next, previous) => {
    if (next === previous) return
    selectedFindingIds.value = []
    decisionOpen.value = false
    decisionTarget.value = null
    batchMode.value = false
    if (next !== null) {
      void load()
    }
  },
)

onMounted(() => {
  void load()
})
</script>

<style scoped>
.review-detail {
  display: grid;
  gap: 20px;
  max-width: 1280px;
  margin: 0 auto;
  padding: 32px;
}

.review-detail__header,
.review-detail__source,
.review-detail__workspace,
.review-detail__derive,
.review-detail__conflict {
  border: 1px solid var(--td-component-border);
  border-radius: 12px;
  background: var(--td-bg-color-container);
}

.review-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px;
}

.review-detail__header h1,
.review-detail__workspace h2,
.review-detail__derive h2,
.review-detail__conflict h2 {
  margin: 0;
}

.review-detail__eyebrow {
  margin: 12px 0 5px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.review-detail__source {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 18px 22px;
}

.review-detail__source div {
  display: grid;
  gap: 6px;
}

.review-detail__source span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.review-detail__workspace,
.review-detail__derive,
.review-detail__conflict {
  padding: 20px 22px;
}

.review-detail__workspace > header,
.review-detail__derive {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.review-detail__workspace > header {
  margin-bottom: 16px;
}

.review-detail__workspace p,
.review-detail__derive p,
.review-detail__conflict p {
  color: var(--td-text-color-secondary);
}

.review-detail__conflict {
  border-color: var(--td-warning-color);
}

.review-detail__conflict dl {
  display: flex;
  gap: 28px;
}

.review-detail__conflict dl div {
  display: grid;
  gap: 4px;
}

.review-detail__conflict dt {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.review-detail__error {
  margin: 0;
  padding: 12px 16px;
  border: 1px solid var(--td-error-color);
  border-radius: 8px;
  color: var(--td-error-color);
}

.review-detail__loading {
  padding: 32px;
  color: var(--td-text-color-secondary);
}

@media (max-width: 900px) {
  .review-detail {
    padding: 20px;
  }

  .review-detail__source {
    grid-template-columns: 1fr;
  }

  .review-detail__header,
  .review-detail__workspace > header,
  .review-detail__derive {
    display: grid;
  }
}
</style>
