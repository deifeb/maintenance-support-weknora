<template>
  <form class="allocation-rule-editor" @submit.prevent="submitDraft">
    <fieldset>
      <legend>Rule identity</legend>

      <label>
        <span>Lineage ID</span>
        <input v-model.trim="lineageId" name="lineage_id" required>
      </label>

      <label>
        <span>Change reason</span>
        <textarea v-model.trim="changeReason" name="change_reason" required />
      </label>

      <label>
        <span>Effective from</span>
        <input v-model="effectiveFrom" type="datetime-local">
      </label>

      <label>
        <span>Effective to</span>
        <input v-model="effectiveTo" type="datetime-local">
      </label>
    </fieldset>

    <fieldset>
      <legend>Scope</legend>
      <textarea
        v-model="scopeJson"
        aria-label="Allocation rule scope JSON"
        rows="5"
      />
    </fieldset>

    <fieldset>
      <legend>Hard rules</legend>

      <label>
        <input v-model="hardRules.exclude_frozen" type="checkbox">
        Exclude frozen inventory
      </label>
      <label>
        <input v-model="hardRules.exclude_expired" type="checkbox">
        Exclude expired inventory
      </label>
      <label>
        <input v-model="hardRules.require_available" type="checkbox">
        Require available inventory
      </label>
    </fieldset>

    <fieldset>
      <legend>Weights and normalization</legend>

      <div
        v-for="(row, index) in metricRows"
        :key="index"
        class="allocation-rule-editor__metric"
      >
        <input
          v-model.trim="row.metric"
          :aria-label="`Metric ${index + 1}`"
          placeholder="metric"
        >
        <input
          v-model.trim="row.weight"
          :aria-label="`Weight ${index + 1}`"
          inputmode="decimal"
          placeholder="0.500000"
        >
        <input
          v-model.trim="row.min"
          :aria-label="`Normalization minimum ${index + 1}`"
          inputmode="decimal"
          placeholder="0"
        >
        <input
          v-model.trim="row.max"
          :aria-label="`Normalization maximum ${index + 1}`"
          inputmode="decimal"
          placeholder="100"
        >
        <button
          type="button"
          :disabled="metricRows.length === 1"
          @click="removeMetric(index)"
        >
          Remove
        </button>
      </div>

      <button type="button" @click="addMetric">
        Add metric
      </button>
    </fieldset>

    <ul v-if="errors.length > 0" role="alert">
      <li v-for="error in errors" :key="error">
        {{ error }}
      </li>
    </ul>

    <button type="submit">
      Create draft
    </button>
  </form>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'

import type {
  AllocationRuleDraftRequest,
  AllocationRuleNormalizationBounds,
} from '@/api/maintenance/allocations'
import {
  validateAllocationRuleMetrics,
  type AllocationRuleMetricInput,
} from './allocation-workflow'

const emit = defineEmits<{
  draft: [request: AllocationRuleDraftRequest]
}>()

const lineageId = ref('')
const changeReason = ref('')
const effectiveFrom = ref('')
const effectiveTo = ref('')
const scopeJson = ref('{}')
const errors = ref<string[]>([])

const hardRules = reactive({
  exclude_frozen: true,
  exclude_expired: true,
  require_available: true,
})

const metricRows = reactive<AllocationRuleMetricInput[]>([
  {
    metric: 'availability',
    weight: '1.000000',
    min: '0',
    max: '100',
  },
])

function addMetric(): void {
  metricRows.push({
    metric: '',
    weight: '0.000000',
    min: '0',
    max: '1',
  })
}

function removeMetric(index: number): void {
  if (metricRows.length === 1) return
  metricRows.splice(index, 1)
}

function parseObject(
  value: string,
  label: string,
): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value) as unknown
    if (
      typeof parsed === 'object'
      && parsed !== null
      && !Array.isArray(parsed)
    ) {
      return parsed as Record<string, unknown>
    }
  } catch {
    errors.value.push(`${label} must be valid JSON`)
    return null
  }

  errors.value.push(`${label} must be a JSON object`)
  return null
}

function submitDraft(): void {
  errors.value = []

  const scope = parseObject(scopeJson.value, 'Scope')
  if (scope === null) return

  if (!lineageId.value) {
    errors.value.push('Lineage ID is required')
  }
  if (!changeReason.value) {
    errors.value.push('Change reason is required')
  }

  const validation = validateAllocationRuleMetrics(metricRows)
  errors.value.push(...validation.errors)

  if (errors.value.length > 0) return

  const weights: Record<string, string> = {}
  const normalization: Record<
    string,
    AllocationRuleNormalizationBounds
  > = {}

  for (const row of metricRows) {
    const metric = row.metric.trim()
    weights[metric] = row.weight
    normalization[metric] = {
      min: row.min,
      max: row.max,
    }
  }

  const request: AllocationRuleDraftRequest = {
    scope,
    effective_from: effectiveFrom.value || null,
    effective_to: effectiveTo.value || null,
    hard_rules: {
      exclude_frozen: hardRules.exclude_frozen,
      exclude_expired: hardRules.exclude_expired,
      require_available: hardRules.require_available,
    },
    weights,
    normalization,
    lineage_id: lineageId.value,
    change_reason: changeReason.value,
  }

  emit('draft', request)
}
</script>
