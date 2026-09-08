<template>
  <div
    v-if="open && finding"
    class="decision-dialog__backdrop"
  >
    <section
      class="decision-dialog"
      role="dialog"
      aria-modal="true"
      :aria-label="t('maintenance.review.decision.title')"
    >
      <header>
        <div>
          <p>{{ finding.finding_key }}</p>
          <h2>{{ t('maintenance.review.decision.title') }}</h2>
        </div>
        <button
          type="button"
          :disabled="busy"
          @click="$emit('cancel')"
        >
          ×
        </button>
      </header>

      <p
        v-if="finding.requires_admin_acceptance"
        class="decision-dialog__risk"
      >
        {{ t('maintenance.review.decision.highRisk') }}
      </p>

      <fieldset :disabled="busy">
        <legend>{{ t('maintenance.review.decision.action') }}</legend>

        <label>
          <input
            v-model="action"
            type="radio"
            value="ACCEPTED"
            :disabled="highRiskAcceptanceBlocked"
          >
          ACCEPTED
        </label>

        <label>
          <input
            v-model="action"
            type="radio"
            value="REJECTED"
          >
          REJECTED
        </label>

        <label>
          <input
            v-model="action"
            type="radio"
            value="EDIT_ACCEPTED"
            :disabled="highRiskAcceptanceBlocked"
          >
          EDIT_ACCEPTED
        </label>
      </fieldset>

      <label v-if="action === 'EDIT_ACCEPTED'">
        <span>{{ t('maintenance.review.decision.finalQuantity') }}</span>
        <input
          v-model="finalQuantity"
          type="text"
          inputmode="decimal"
          autocomplete="off"
        >
      </label>

      <label>
        <span>{{ t('maintenance.review.decision.reason') }}</span>
        <textarea
          v-model="reason"
          maxlength="1000"
        />
      </label>

      <p
        v-if="validationMessage"
        class="decision-dialog__validation"
        role="alert"
      >
        {{ validationMessage }}
      </p>

      <footer>
        <button
          type="button"
          :disabled="busy"
          @click="$emit('cancel')"
        >
          {{ t('common.cancel') }}
        </button>
        <button
          type="button"
          :disabled="busy || !canSubmit"
          @click="submit"
        >
          {{
            busy
              ? t('maintenance.review.actions.saving')
              : t('maintenance.review.actions.confirm')
          }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  DemandReviewDecisionAction,
  DemandReviewFindingRead,
} from '@/api/maintenance/demand-reviews'

const props = defineProps<{
  open: boolean
  finding: DemandReviewFindingRead | null
  busy: boolean
  confirmHighRisk: boolean
}>()

const emit = defineEmits<{
  cancel: []
  submit: [payload: {
    action: DemandReviewDecisionAction
    final_quantity: string | null
    reason: string | null
  }]
}>()

const { t } = useI18n()

const action = ref<DemandReviewDecisionAction>('REJECTED')
const finalQuantity = ref('')
const reason = ref('')

const highRiskAcceptanceBlocked = computed(() => (
  Boolean(props.finding?.requires_admin_acceptance)
  && !props.confirmHighRisk
))

const numericQuantity = computed(() => (
  Number(finalQuantity.value.trim())
))

const validationMessage = computed(() => {
  if (
    (action.value === 'ACCEPTED' || action.value === 'EDIT_ACCEPTED')
    && highRiskAcceptanceBlocked.value
  ) {
    return t('maintenance.review.validation.adminRequired')
  }

  if (action.value !== 'EDIT_ACCEPTED') {
    return ''
  }

  if (!reason.value.trim()) {
    return t('maintenance.review.validation.reasonRequired')
  }

  if (
    !Number.isFinite(numericQuantity.value)
    || numericQuantity.value <= 0
  ) {
    return t('maintenance.review.validation.positiveQuantity')
  }

  return ''
})

const canSubmit = computed(() => validationMessage.value === '')

watch(
  () => [
    props.open,
    props.finding?.id ?? null,
  ] as const,
  ([open]) => {
    if (!open) return
    action.value = 'REJECTED'
    finalQuantity.value = ''
    reason.value = ''
  },
)

function submit(): void {
  if (!props.finding || !canSubmit.value) return

  const normalizedReason = reason.value.trim()
  emit('submit', {
    action: action.value,
    final_quantity: action.value === 'EDIT_ACCEPTED'
      ? finalQuantity.value.trim()
      : null,
    reason: normalizedReason || null,
  })
}
</script>

<style scoped>
.decision-dialog__backdrop {
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(0 0 0 / 45%);
}

.decision-dialog {
  display: grid;
  gap: 16px;
  width: min(560px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  padding: 22px;
  border-radius: 12px;
  background: var(--td-bg-color-container);
  box-shadow: var(--td-shadow-3);
}

.decision-dialog > header,
.decision-dialog > footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.decision-dialog h2,
.decision-dialog p {
  margin: 0;
}

.decision-dialog label {
  display: grid;
  gap: 7px;
}

.decision-dialog fieldset {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 14px;
  border: 1px solid var(--td-component-border);
  border-radius: 8px;
}

.decision-dialog fieldset label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.decision-dialog textarea {
  min-height: 96px;
  resize: vertical;
}

.decision-dialog__risk,
.decision-dialog__validation {
  padding: 10px 12px;
  border-radius: 8px;
}

.decision-dialog__risk {
  background: var(--td-warning-color-light-9);
  color: var(--td-warning-color);
}

.decision-dialog__validation {
  background: var(--td-error-color-light-9);
  color: var(--td-error-color);
}
</style>
