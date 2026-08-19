<template>
  <section class="finding-table">
    <header class="finding-table__filters">
      <label>
        <span>{{ t('maintenance.review.finding.severity') }}</span>
        <select v-model="severityFilter">
          <option value="">
            {{ t('maintenance.review.finding.all') }}
          </option>
          <option
            v-for="severity in severities"
            :key="severity"
            :value="severity"
          >
            {{ severity }}
          </option>
        </select>
      </label>

      <label>
        <span>{{ t('maintenance.review.finding.decision') }}</span>
        <select v-model="decisionFilter">
          <option value="">
            {{ t('maintenance.review.finding.all') }}
          </option>
          <option
            v-for="status in decisionStatuses"
            :key="status"
            :value="status"
          >
            {{ status }}
          </option>
        </select>
      </label>

      <label>
        <span>{{ t('maintenance.review.finding.blocking') }}</span>
        <select v-model="blockingFilter">
          <option value="all">
            {{ t('maintenance.review.finding.all') }}
          </option>
          <option value="blocking">
            {{ t('maintenance.review.finding.blockingOnly') }}
          </option>
          <option value="non-blocking">
            {{ t('maintenance.review.finding.nonBlockingOnly') }}
          </option>
        </select>
      </label>
    </header>

    <div class="finding-table__wrap">
      <table>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                :checked="allFilteredSelected"
                :disabled="!canHandle || filteredFindings.length === 0"
                @change="toggleAllFromEvent"
              >
            </th>
            <th>{{ t('maintenance.review.finding.key') }}</th>
            <th>{{ t('maintenance.review.finding.rule') }}</th>
            <th>{{ t('maintenance.review.finding.severity') }}</th>
            <th>{{ t('maintenance.review.finding.blocking') }}</th>
            <th>{{ t('maintenance.review.finding.admin') }}</th>
            <th>{{ t('maintenance.review.finding.decision') }}</th>
            <th>{{ t('maintenance.review.finding.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="finding in filteredFindings"
            :key="finding.id"
          >
            <td>
              <input
                type="checkbox"
                :checked="selectedIds.includes(finding.id)"
                :disabled="!canHandle || finding.decision_status !== 'PENDING'"
                @change="toggleFromEvent(finding.id, $event)"
              >
            </td>
            <td>
              <strong>{{ finding.finding_key }}</strong>
              <span>{{ finding.finding_type }}</span>
            </td>
            <td>{{ finding.rule_code }}</td>
            <td>{{ finding.severity }}</td>
            <td>{{ finding.blocking ? t('common.yes') : t('common.no') }}</td>
            <td>
              {{
                finding.requires_admin_acceptance
                  ? t('common.yes')
                  : t('common.no')
              }}
            </td>
            <td>{{ finding.decision_status }}</td>
            <td>
              <button
                type="button"
                :disabled="!canHandle || finding.decision_status !== 'PENDING'"
                @click="$emit('decide', finding)"
              >
                {{ t('maintenance.review.actions.decide') }}
              </button>
            </td>
          </tr>
          <tr v-if="filteredFindings.length === 0">
            <td colspan="8">
              {{ t('maintenance.review.finding.empty') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  DemandReviewDecisionStatus,
  DemandReviewFindingRead,
  DemandReviewSeverity,
} from '@/api/maintenance/demand-reviews'

const props = defineProps<{
  findings: DemandReviewFindingRead[]
  selectedIds: number[]
  canHandle: boolean
}>()

const emit = defineEmits<{
  'update:selectedIds': [value: number[]]
  decide: [finding: DemandReviewFindingRead]
}>()

const { t } = useI18n()

const severities: DemandReviewSeverity[] = [
  'LOW',
  'MEDIUM',
  'HIGH',
  'CRITICAL',
]
const decisionStatuses: DemandReviewDecisionStatus[] = [
  'PENDING',
  'ACCEPTED',
  'REJECTED',
  'EDIT_ACCEPTED',
]

const severityFilter = ref<DemandReviewSeverity | ''>('')
const decisionFilter = ref<DemandReviewDecisionStatus | ''>('')
const blockingFilter = ref<'all' | 'blocking' | 'non-blocking'>('all')

const filteredFindings = computed(() => (
  props.findings.filter((finding) => {
    if (
      severityFilter.value
      && finding.severity !== severityFilter.value
    ) {
      return false
    }
    if (
      decisionFilter.value
      && finding.decision_status !== decisionFilter.value
    ) {
      return false
    }
    if (
      blockingFilter.value === 'blocking'
      && !finding.blocking
    ) {
      return false
    }
    if (
      blockingFilter.value === 'non-blocking'
      && finding.blocking
    ) {
      return false
    }
    return true
  })
))

const selectableFilteredIds = computed(() => (
  filteredFindings.value
    .filter((finding) => finding.decision_status === 'PENDING')
    .map((finding) => finding.id)
))

const allFilteredSelected = computed(() => (
  selectableFilteredIds.value.length > 0
  && selectableFilteredIds.value.every(
    (id) => props.selectedIds.includes(id),
  )
))

function checkedFromEvent(event: Event): boolean {
  return (
    event.target instanceof HTMLInputElement
    && event.target.checked
  )
}

function toggleFromEvent(
  findingId: number,
  event: Event,
): void {
  const next = new Set(props.selectedIds)
  if (checkedFromEvent(event)) {
    next.add(findingId)
  } else {
    next.delete(findingId)
  }
  emit('update:selectedIds', [...next])
}

function toggleAllFromEvent(event: Event): void {
  const next = new Set(props.selectedIds)
  if (checkedFromEvent(event)) {
    selectableFilteredIds.value.forEach((id) => next.add(id))
  } else {
    selectableFilteredIds.value.forEach((id) => next.delete(id))
  }
  emit('update:selectedIds', [...next])
}
</script>

<style scoped>
.finding-table {
  display: grid;
  gap: 14px;
}

.finding-table__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.finding-table__filters label {
  display: grid;
  gap: 6px;
  min-width: 180px;
}

.finding-table__wrap {
  overflow-x: auto;
  border: 1px solid var(--td-component-border);
  border-radius: 10px;
}

.finding-table table {
  width: 100%;
  border-collapse: collapse;
}

.finding-table th,
.finding-table td {
  padding: 12px 10px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  vertical-align: top;
}

.finding-table th {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.finding-table td strong,
.finding-table td span {
  display: block;
}

.finding-table td span {
  margin-top: 4px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}
</style>
