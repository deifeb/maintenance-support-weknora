<template>
  <main class="allocation-plan-detail">
    <button type="button" class="allocation-plan-detail__back" @click="back">
      ← Inventory gap
    </button>

    <section v-if="invalidRoute" class="allocation-plan-detail__notice">
      Invalid allocation plan ID.
    </section>

    <template v-else>
      <p v-if="allocationStore.planDetail.loading && !current">
        Loading allocation plan…
      </p>

      <section
        v-if="allocationStore.planDetail.error"
        class="allocation-plan-detail__error"
        role="alert"
      >
        <strong>{{ allocationStore.planDetail.error.code }}</strong>
        <span>{{ allocationStore.planDetail.error.message }}</span>
        <button type="button" @click="load">Retry</button>
      </section>

      <template v-if="current">
        <header class="allocation-plan-detail__header">
          <div>
            <p>Allocation assurance</p>
            <h1>Allocation plan #{{ current.id }}</h1>
            <p>
              Status: <strong>{{ current.status }}</strong>
              · Version {{ current.version }}
            </p>
          </div>

          <div class="allocation-plan-detail__actions">
            <button
              v-if="hasAction('preview')"
              type="button"
              @click="previewPlan"
            >
              Preview
            </button>
            <button
              v-if="hasAction('confirm')"
              type="button"
              @click="confirmPlan"
            >
              Confirm
            </button>
            <button
              v-if="hasAction('execute')"
              type="button"
              @click="executePlan"
            >
              Execute
            </button>
            <button
              v-if="hasAction('void')"
              type="button"
              @click="voidPlan"
            >
              Void
            </button>
            <button
              v-if="hasAction('regenerate')"
              type="button"
              @click="regeneratePlan"
            >
              Regenerate
            </button>
          </div>
        </header>

        <dl class="allocation-plan-detail__facts">
          <div>
            <dt>Source demand list</dt>
            <dd>#{{ current.source_demand_list_id }} v{{ current.source_demand_list_version }}</dd>
          </div>
          <div>
            <dt>Rule</dt>
            <dd>#{{ current.rule_id }}</dd>
          </div>
          <div>
            <dt>Inventory fingerprint</dt>
            <dd><code>{{ current.inventory_fingerprint }}</code></dd>
          </div>
        </dl>

        <section
          v-if="actionError"
          class="allocation-plan-detail__error"
          role="alert"
        >
          <strong>{{ errorMessage(actionError) }}</strong>
          <dl v-if="conflictEvidence">
            <div><dt>Code</dt><dd>{{ evidenceLabel(conflictEvidence.code) }}</dd></div>
            <div><dt>Request</dt><dd>{{ evidenceLabel(conflictEvidence.requestId) }}</dd></div>
            <div><dt>Expected version</dt><dd>{{ evidenceLabel(conflictEvidence.expectedVersion) }}</dd></div>
            <div><dt>Actual version</dt><dd>{{ evidenceLabel(conflictEvidence.actualVersion) }}</dd></div>
            <div><dt>Retryable</dt><dd>{{ evidenceLabel(conflictEvidence.retryable) }}</dd></div>
            <div><dt>Suggested action</dt><dd>{{ evidenceLabel(conflictEvidence.suggestedAction) }}</dd></div>
            <div><dt>Fact</dt><dd>{{ evidenceLabel(conflictEvidence.fact) }}</dd></div>
            <div><dt>Regenerate</dt><dd>{{ evidenceLabel(conflictEvidence.regenerate) }}</dd></div>
          </dl>
        </section>

        <section class="allocation-plan-detail__section">
          <h2>Plan lines</h2>
          <AllocationPlanTable
            :lines="current.lines"
            :editable="hasAction('edit-line')"
            @edit="openLineEdit"
          />
        </section>

        <section
          v-if="editingLine"
          class="allocation-plan-detail__editor"
          aria-label="Allocation line editor"
        >
          <h2>Edit line #{{ editingLine.id }}</h2>
          <form @submit.prevent="saveLineEdit">
            <label>
              <span>Allocated quantity</span>
              <input
                v-model.trim="allocatedQuantity"
                inputmode="decimal"
                required
              >
            </label>
            <label>
              <span>Reason</span>
              <textarea v-model.trim="editReason" required />
            </label>
            <div>
              <button type="submit">Save</button>
              <button type="button" @click="closeLineEdit">Cancel</button>
            </div>
          </form>
        </section>

        <PlanExecutionSummary
          :execution="executionResult"
          :can-regenerate="hasAction('regenerate')"
          @regenerate="regeneratePlan"
        />
      </template>
    </template>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  ref,
  watch,
} from 'vue'
import {
  useRoute,
  useRouter,
} from 'vue-router'

import type {
  AllocationPlanExecutionResult,
  AllocationPlanLineRead,
} from '@/api/maintenance/allocations'
import AllocationPlanTable from '@/components/maintenance/allocation/AllocationPlanTable.vue'
import PlanExecutionSummary from '@/components/maintenance/allocation/PlanExecutionSummary.vue'
import {
  allocationConflictDisplay,
  allocationPlanActions,
  positiveAllocationRouteId,
  type AllocationPlanUiAction,
} from '@/components/maintenance/allocation/allocation-workflow'
import {
  useAllocationStore,
} from '@/stores/maintenance/allocation'
import {
  useMaintenancePermissionsStore,
} from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const allocationStore = useAllocationStore()
const permissionsStore = useMaintenancePermissionsStore()

const actionError = ref<unknown>(null)
const editingLine = ref<AllocationPlanLineRead | null>(null)
const allocatedQuantity = ref('')
const editReason = ref('')
const executionResult = ref<AllocationPlanExecutionResult | null>(null)

const routeId = computed(
  () => positiveAllocationRouteId(route.params.planId),
)
const invalidRoute = computed(() => routeId.value === null)
const current = computed(() => {
  const planId = routeId.value
  const item = allocationStore.planDetail.item

  return (
    planId !== null
    && item !== null
    && item.id === planId
  )
    ? item
    : null
})
const canContribute = computed(
  () => permissionsStore.can('editDemandList'),
)
const availableActions = computed(() => (
  current.value === null
    ? []
    : allocationPlanActions(
      current.value.status,
      {
        canContribute: canContribute.value,
        canPublishRules: false,
      },
    )
))
const conflictEvidence = computed(() => (
  actionError.value === null
    ? null
    : allocationConflictDisplay(actionError.value)
))

function hasAction(action: AllocationPlanUiAction): boolean {
  return availableActions.value.includes(action)
}

function errorMessage(value: unknown): string {
  if (
    typeof value === 'object'
    && value !== null
    && 'message' in value
    && typeof value.message === 'string'
  ) {
    return value.message
  }
  return 'Allocation plan action failed'
}

function evidenceLabel(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function load(): Promise<void> {
  const planId = routeId.value
  if (planId === null) return

  actionError.value = null
  try {
    await allocationStore.fetchPlanDetail(planId)
  } catch (error) {
    actionError.value = error
  }
}

function back(): void {
  void router.push({ name: 'maintenanceInventoryGap' })
}

function openLineEdit(line: AllocationPlanLineRead): void {
  if (!hasAction('edit-line')) return
  editingLine.value = line
  allocatedQuantity.value = line.allocated_quantity
  editReason.value = ''
  actionError.value = null
}

function closeLineEdit(): void {
  editingLine.value = null
  allocatedQuantity.value = ''
  editReason.value = ''
}

async function saveLineEdit(): Promise<void> {
  const plan = current.value
  const line = editingLine.value
  if (plan === null || line === null || !hasAction('edit-line')) return
  if (!allocatedQuantity.value || !editReason.value.trim()) return

  actionError.value = null
  try {
    await allocationStore.editPlanLine(plan.id, line.id, {
      expected_plan_version: plan.version,
      expected_line_version: line.version,
      allocated_quantity: allocatedQuantity.value,
      reason: editReason.value.trim(),
    })
    await allocationStore.fetchPlanDetail(plan.id)
    closeLineEdit()
  } catch (error) {
    actionError.value = error
  }
}

function confirmIntent(message: string): boolean {
  return typeof window !== 'undefined' && window.confirm(message)
}

async function runPlanAction(
  action: () => Promise<void>,
): Promise<void> {
  actionError.value = null
  try {
    await action()
  } catch (error) {
    actionError.value = error
  }
}

async function previewPlan(): Promise<void> {
  const plan = current.value
  if (plan === null || !hasAction('preview')) return
  if (!confirmIntent(`Preview allocation plan #${plan.id}?`)) return

  await runPlanAction(async () => {
    await allocationStore.previewPlan(plan.id, {
      expected_version: plan.version,
    })
    await allocationStore.fetchPlanDetail(plan.id)
  })
}

async function confirmPlan(): Promise<void> {
  const plan = current.value
  if (plan === null || !hasAction('confirm')) return
  if (!confirmIntent(`Confirm allocation plan #${plan.id}?`)) return

  await runPlanAction(async () => {
    await allocationStore.confirmPlan(plan.id, {
      expected_version: plan.version,
    })
    await allocationStore.fetchPlanDetail(plan.id)
  })
}

async function executePlan(): Promise<void> {
  const plan = current.value
  if (plan === null || !hasAction('execute')) return
  if (!confirmIntent(`Execute allocation plan #${plan.id}?`)) return

  await runPlanAction(async () => {
    executionResult.value = await allocationStore.executePlan(
      plan.id,
      { expected_version: plan.version },
    )
    await allocationStore.fetchPlanDetail(plan.id)
  })
}

async function voidPlan(): Promise<void> {
  const plan = current.value
  if (plan === null || !hasAction('void')) return
  if (!confirmIntent(`Void allocation plan #${plan.id}?`)) return

  await runPlanAction(async () => {
    await allocationStore.voidPlan(plan.id, {
      expected_version: plan.version,
    })
    await allocationStore.fetchPlanDetail(plan.id)
  })
}

async function regeneratePlan(): Promise<void> {
  const plan = current.value
  if (plan === null || !hasAction('regenerate')) return
  if (!confirmIntent(`Regenerate allocation plan #${plan.id}?`)) return

  await runPlanAction(async () => {
    const result = await allocationStore.regeneratePlan(
      plan.id,
      { expected_version: plan.version },
    )
    executionResult.value = null
    await router.replace({
      name: 'maintenanceAllocationPlanDetail',
      params: { planId: result.new_plan_id },
    })
  })
}

watch(
  () => route.params.planId,
  () => {
    editingLine.value = null
    executionResult.value = null
    void load()
  },
  { immediate: true },
)
</script>

<style scoped>
.allocation-plan-detail {
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px;
}

.allocation-plan-detail__back {
  margin-bottom: 18px;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  cursor: pointer;
}

.allocation-plan-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.allocation-plan-detail__header h1,
.allocation-plan-detail__header p {
  margin: 0 0 6px;
}

.allocation-plan-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.allocation-plan-detail__facts,
.allocation-plan-detail__error dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.allocation-plan-detail__facts > div,
.allocation-plan-detail__error,
.allocation-plan-detail__editor {
  padding: 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
}

.allocation-plan-detail__facts dt,
.allocation-plan-detail__error dt {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.allocation-plan-detail__facts dd,
.allocation-plan-detail__error dd {
  margin: 5px 0 0;
  word-break: break-word;
}

.allocation-plan-detail__section,
.allocation-plan-detail__editor,
.allocation-plan-detail__error {
  margin-top: 20px;
}

.allocation-plan-detail__editor form,
.allocation-plan-detail__editor label {
  display: grid;
  gap: 8px;
}

.allocation-plan-detail__editor form {
  gap: 14px;
}

.allocation-plan-detail__editor textarea {
  min-height: 90px;
}
</style>
