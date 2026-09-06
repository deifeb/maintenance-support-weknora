<template>
  <main class="allocation-rule-list">
    <header class="allocation-rule-list__header">
      <div>
        <p>Allocation assurance</p>
        <h1>Allocation rules</h1>
      </div>

      <button
        type="button"
        :disabled="allocationStore.rules.loading"
        @click="fetchRules"
      >
        Refresh
      </button>
    </header>

    <RuleEditor
      v-if="canContribute"
      @draft="createRule"
    />

    <p v-if="actionError" role="alert">
      {{ actionError }}
    </p>

    <p v-if="allocationStore.rules.error" role="alert">
      {{ allocationStore.rules.error.message }}
    </p>

    <p v-if="allocationStore.rules.loading && allocationStore.rules.items.length === 0">
      Loading allocation rules…
    </p>

    <p v-else-if="allocationStore.rules.items.length === 0">
      No allocation rules.
    </p>

    <template v-else>
      <article
        v-for="rule in allocationStore.rules.items"
        :key="rule.id"
        class="allocation-rule-list__rule"
      >
      <header>
        <div>
          <strong>#{{ rule.id }} · {{ rule.lineage_id }}</strong>
          <span>{{ rule.status }}</span>
          <span>v{{ rule.version_number }}</span>
        </div>

        <div class="allocation-rule-list__actions">
          <template v-if="actionsFor(rule).includes('simulate')">
            <input
              v-model.trim="simulationSourceDemandListId[rule.id]"
              :aria-label="`Source demand list for rule ${rule.id}`"
              inputmode="numeric"
              placeholder="Demand list ID"
            >
            <button
              type="button"
              :disabled="!hasSimulationSource(rule.id)"
              @click="simulateRule(rule)"
            >
              Simulate
            </button>
          </template>

          <button
            v-if="actionsFor(rule).includes('publish')"
            type="button"
            @click="publishRule(rule)"
          >
            Publish
          </button>

          <button
            v-if="actionsFor(rule).includes('retire')"
            type="button"
            @click="retireRule(rule)"
          >
            Retire
          </button>
        </div>
      </header>

      <dl>
        <div>
          <dt>Change reason</dt>
          <dd>{{ rule.change_reason }}</dd>
        </div>
        <div>
          <dt>Weights</dt>
          <dd><code>{{ JSON.stringify(rule.weights) }}</code></dd>
        </div>
      </dl>

      <SimulationComparison
        :simulation="rule.latest_simulation"
      />

        <RulePollingBridge
          v-if="
            rule.latest_simulation
              && !isAllocationSimulationTerminal(rule.latest_simulation.status)
          "
          :key="`${rule.id}:${rule.latest_simulation.id}`"
          :rule-id="rule.id"
          :lineage-id="rule.lineage_id"
        />
      </article>
    </template>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  defineComponent,
  h,
  onMounted,
  reactive,
  ref,
} from 'vue'

import type {
  AllocationRuleDraftRequest,
  AllocationRuleRead,
} from '@/api/maintenance/allocations'
import {
  useAllocationSimulationPolling,
} from '@/composables/maintenance/useAllocationSimulationPolling'
import RuleEditor from '@/components/maintenance/allocation/RuleEditor.vue'
import SimulationComparison from '@/components/maintenance/allocation/SimulationComparison.vue'
import {
  allocationRuleActions,
  isAllocationSimulationTerminal,
  positiveAllocationRouteId,
} from '@/components/maintenance/allocation/allocation-workflow'
import {
  useAllocationStore,
} from '@/stores/maintenance/allocation'
import {
  useMaintenancePermissionsStore,
} from '@/stores/maintenance/permissions'

const allocationStore = useAllocationStore()
const permissionsStore = useMaintenancePermissionsStore()

const actionError = ref<string | null>(null)
const simulationSourceDemandListId = reactive<Record<number, string>>({})

const canContribute = computed(
  () => permissionsStore.can('editDemandList'),
)
const canPublishRules = computed(
  () => permissionsStore.can('publishRules'),
)

const RulePollingBridge = defineComponent({
  name: 'AllocationRulePollingBridge',
  props: {
    ruleId: {
      type: Number,
      required: true,
    },
    lineageId: {
      type: String,
      required: true,
    },
  },
  setup(props) {
    useAllocationSimulationPolling({
      ruleId: props.ruleId,
      lineageId: props.lineageId,
      onError: (error) => {
        actionError.value = errorMessage(error)
      },
    })

    return () => h('span', {
      hidden: true,
      'aria-hidden': 'true',
    })
  },
})

function errorMessage(value: unknown): string {
  if (
    typeof value === 'object'
    && value !== null
    && 'message' in value
    && typeof value.message === 'string'
  ) {
    return value.message
  }
  return 'Allocation action failed'
}

function actionsFor(rule: AllocationRuleRead) {
  return allocationRuleActions(
    rule.status,
    {
      canContribute: canContribute.value,
      canPublishRules: canPublishRules.value,
    },
  )
}

async function withAction(
  action: () => Promise<void>,
): Promise<void> {
  actionError.value = null
  try {
    await action()
  } catch (error) {
    actionError.value = errorMessage(error)
  }
}

async function fetchRules(): Promise<void> {
  await withAction(async () => {
    await allocationStore.fetchRules()
  })
}

async function createRule(
  request: AllocationRuleDraftRequest,
): Promise<void> {
  await withAction(async () => {
    await allocationStore.createRule(request)
    await allocationStore.fetchRules()
  })
}

function simulationSourceId(ruleId: number): number | null {
  return positiveAllocationRouteId(
    simulationSourceDemandListId[ruleId],
  )
}

function hasSimulationSource(ruleId: number): boolean {
  return simulationSourceId(ruleId) !== null
}

async function simulateRule(
  rule: AllocationRuleRead,
): Promise<void> {
  const sourceDemandListId = simulationSourceId(rule.id)
  if (sourceDemandListId === null) return

  await withAction(async () => {
    await allocationStore.simulateRule(
      rule.id,
      {
        expected_rule_version: rule.version,
        source_demand_list_id: sourceDemandListId,
      },
    )
  })
}

async function publishRule(
  rule: AllocationRuleRead,
): Promise<void> {
  if (!canPublishRules.value) return

  await withAction(async () => {
    await allocationStore.publishRule(
      rule.id,
      {
        expected_version: rule.version,
      },
    )
  })
}

async function retireRule(
  rule: AllocationRuleRead,
): Promise<void> {
  if (!canPublishRules.value) return

  await withAction(async () => {
    await allocationStore.retireRule(
      rule.id,
      {
        expected_version: rule.version,
      },
    )
  })
}

onMounted(() => {
  void fetchRules()
})
</script>
