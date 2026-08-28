import { ref } from 'vue'

import type {
  AllocationSimulationStatus,
  AllocationSimulationSummaryRead,
} from '../../api/maintenance/allocations'
import {
  useAllocationStore,
} from '../../stores/maintenance/allocation'
import {
  createPollingController,
  usePageVisibilityPolling,
  type PollingController,
  type PollingTimerAdapter,
} from './usePageVisibilityPolling'

export const ALLOCATION_SIMULATION_POLL_INTERVAL_MS = 2000

const TERMINAL_SIMULATION_STATUSES:
  ReadonlySet<AllocationSimulationStatus> = new Set([
    'COMPLETED',
    'FAILED',
    'CANCELLED',
  ])

function isTerminalSimulation(
  simulation: AllocationSimulationSummaryRead | null,
): boolean {
  return (
    simulation !== null
    && TERMINAL_SIMULATION_STATUSES.has(
      simulation.status,
    )
  )
}

export interface AllocationSimulationPollingOptions {
  load: () => Promise<
    AllocationSimulationSummaryRead | null
  >
  onError?: (error: unknown) => void
  intervalMs?: number
  timers?: PollingTimerAdapter
}

export function createAllocationSimulationPolling(
  options: AllocationSimulationPollingOptions,
): PollingController {
  let controller: PollingController

  controller = createPollingController({
    intervalMs: (
      options.intervalMs
      ?? ALLOCATION_SIMULATION_POLL_INTERVAL_MS
    ),
    timers: options.timers,
    run: async () => {
      try {
        const simulation = await options.load()

        if (isTerminalSimulation(simulation)) {
          controller.setActive(false)
        }
      } catch (error) {
        options.onError?.(error)
      }
    },
  })

  return controller
}

export interface AllocationSimulationRefreshSource {
  refreshRuleSimulation(
    ruleId: number,
    lineageId: string,
  ): Promise<AllocationSimulationSummaryRead | null>
}

export interface UseAllocationSimulationPollingOptions {
  ruleId: number
  lineageId: string
  source?: AllocationSimulationRefreshSource
  onError?: (error: unknown) => void
}

export function useAllocationSimulationPolling(
  options: UseAllocationSimulationPollingOptions,
): PollingController {
  const source = options.source ?? useAllocationStore()
  const active = ref(true)

  return usePageVisibilityPolling({
    intervalMs: ALLOCATION_SIMULATION_POLL_INTERVAL_MS,
    isActive: () => active.value,
    run: async () => {
      try {
        const simulation =
          await source.refreshRuleSimulation(
            options.ruleId,
            options.lineageId,
          )

        if (isTerminalSimulation(simulation)) {
          active.value = false
        }
      } catch (error) {
        options.onError?.(error)
      }
    },
  })
}
