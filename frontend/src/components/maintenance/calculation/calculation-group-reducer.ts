import type {
  CalculationGroup,
  CalculationGroupEvent,
  ChildCalculationStatus,
} from '../../../api/maintenance/calculation-groups'

export interface CalculationGroupEventState {
  groupId: number
  lastSequence: number
  group: CalculationGroup | null
  requiresReload: boolean
}

export function initialCalculationGroupEventState(
  groupId: number,
  group: CalculationGroup | null = null,
): CalculationGroupEventState {
  return {
    groupId,
    lastSequence: group?.last_event_sequence ?? 0,
    group,
    requiresReload: false,
  }
}

function payloadString(
  event: CalculationGroupEvent,
  key: string,
): string | undefined {
  const value = event.payload[key]
  return typeof value === 'string'
    ? value
    : undefined
}

function childStatus(
  event: CalculationGroupEvent,
): ChildCalculationStatus | undefined {
  if (event.event_type === 'child.started') {
    return 'RUNNING'
  }
  if (event.event_type === 'child.failed') {
    return 'FAILED'
  }
  if (event.event_type === 'child.cancelled') {
    return 'CANCELLED'
  }
  if (event.event_type === 'child.interrupted') {
    return 'INTERRUPTED'
  }
  if (event.event_type === 'child.completed') {
    const status = payloadString(event, 'status')
    return status === 'PARTIAL_SUCCESS'
      ? 'PARTIAL_SUCCESS'
      : 'SUCCEEDED'
  }
  return undefined
}

export function reduceGroupEvent(
  state: CalculationGroupEventState,
  event: CalculationGroupEvent,
): CalculationGroupEventState {
  if (
    event.group_id !== state.groupId
    || event.sequence <= state.lastSequence
  ) {
    return state
  }

  let group = state.group
  let requiresReload = state.requiresReload
  if (group !== null) {
    const status = childStatus(event)
    if (
      event.child_id !== null
      && (
        status !== undefined
        || event.event_type === 'child.progress'
      )
    ) {
      group = {
        ...group,
        current_children: group.current_children.map(
          (child) => (
            child.id === event.child_id
              ? {
                  ...child,
                  calculation_status: (
                    status ?? child.calculation_status
                  ),
                  progress_percent: (
                    payloadString(
                      event,
                      'progress_percent',
                    )
                    ?? child.progress_percent
                  ),
                }
              : child
          ),
        ),
      }
    }
    if (event.event_type === 'group.status_changed') {
      const nextStatus = payloadString(event, 'to')
      if (nextStatus !== undefined) {
        group = {
          ...group,
          status: nextStatus as CalculationGroup['status'],
        }
      }
    }
    group = {
      ...group,
      last_event_sequence: event.sequence,
    }
  }
  if (event.event_type === 'child.queued') {
    requiresReload = true
  }

  return {
    groupId: state.groupId,
    lastSequence: event.sequence,
    group,
    requiresReload,
  }
}
