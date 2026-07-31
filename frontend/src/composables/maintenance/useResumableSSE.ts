import { fetchEventSource } from '@microsoft/fetch-event-source'

import {
  calculationGroupApi,
  calculationGroupEventStreamUrl,
  type CalculationGroupEvent,
} from '../../api/maintenance/calculation-groups'

export interface ResumableSSEEvent {
  groupId: number
  childId?: number | null
  sequence: number
  type: string
  payload: Record<string, unknown>
  occurredAt?: string
}

export interface ResumableSSEConnectionOptions {
  groupId: number
  lastSequence: number
  signal: AbortSignal
  onOpen(): void
  onEvent(event: ResumableSSEEvent): void
}

export interface ResumableSSEEnvironment {
  connect(
    options: ResumableSSEConnectionOptions,
  ): Promise<void>
  poll(
    groupId: number,
    afterSequence: number,
  ): Promise<CalculationGroupEvent[]>
  setTimeout(
    callback: () => void,
    delayMs: number,
  ): unknown
  clearTimeout(handle: unknown): void
}

export type ResumableSSEConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'polling'
  | 'paused'
  | 'stopped'

export interface ResumableSSEStartOptions {
  groupId: number
  lastSequence?: number
  onEvent(event: ResumableSSEEvent): void
  onStateChange?(
    state: ResumableSSEConnectionState,
  ): void
  onError?(error: unknown): void
}

export interface ResumableSSEController {
  start(options: ResumableSSEStartOptions): void
  stop(): void
  setVisible(visible: boolean): void
  setActive(active: boolean): void
  lastSequence(): number
}

const defaultEnvironment: ResumableSSEEnvironment = {
  async connect(options) {
    await fetchEventSource(
      calculationGroupEventStreamUrl(
        options.groupId,
        options.lastSequence,
      ),
      {
        method: 'GET',
        credentials: 'include',
        signal: options.signal,
        openWhenHidden: true,
        headers: {
          'Last-Event-ID': String(
            options.lastSequence,
          ),
        },
        async onopen(response) {
          if (!response.ok) {
            throw new Error(
              `SSE connection failed (${response.status})`,
            )
          }
          options.onOpen()
        },
        onmessage(message) {
          if (!message.id) return
          const sequence = Number(message.id)
          if (!Number.isSafeInteger(sequence)) return
          const decoded = message.data
              ? JSON.parse(message.data) as {
                child_id?: number | null
                payload?: Record<string, unknown>
                occurred_at?: string
              }
            : {}
          options.onEvent({
            groupId: options.groupId,
            childId: decoded.child_id,
            sequence,
            type: message.event || 'message',
            payload: decoded.payload ?? {},
            occurredAt: decoded.occurred_at,
          })
        },
        onerror(error) {
          throw error
        },
      },
    )
  },
  async poll(groupId, afterSequence) {
    const response = await calculationGroupApi.getEvents(
      groupId,
      afterSequence,
    )
    return response.data
  },
  setTimeout(callback, delayMs) {
    return globalThis.setTimeout(callback, delayMs)
  },
  clearTimeout(handle) {
    globalThis.clearTimeout(
      handle as ReturnType<typeof globalThis.setTimeout>,
    )
  },
}

const RECONNECT_DELAYS = [
  250,
  500,
  1_000,
  2_000,
  5_000,
] as const
const POLL_INTERVAL_MS = 3_000
const FALLBACK_AFTER_FAILURES = 3

export function createResumableSSE(
  environment: ResumableSSEEnvironment =
    defaultEnvironment,
): ResumableSSEController {
  let generation = 0
  let started = false
  let visible = true
  let active = true
  let failures = 0
  let sequence = 0
  let options: ResumableSSEStartOptions | null = null
  let abortController: AbortController | null = null
  let reconnectTimer: unknown
  let pollTimer: unknown

  function state(
    value: ResumableSSEConnectionState,
  ): void {
    options?.onStateChange?.(value)
  }

  function canConnect(): boolean {
    return started && visible && active && options !== null
  }

  function clearReconnect(): void {
    if (reconnectTimer !== undefined) {
      environment.clearTimeout(reconnectTimer)
      reconnectTimer = undefined
    }
  }

  function clearPoll(): void {
    if (pollTimer !== undefined) {
      environment.clearTimeout(pollTimer)
      pollTimer = undefined
    }
  }

  function abortConnection(): void {
    abortController?.abort()
    abortController = null
  }

  function acceptEvent(
    event: ResumableSSEEvent,
    expectedGeneration: number,
  ): void {
    if (
      expectedGeneration !== generation
      || options === null
      || event.groupId !== options.groupId
      || event.sequence <= sequence
    ) {
      return
    }
    sequence = event.sequence
    options.onEvent(event)
  }

  function schedulePoll(
    expectedGeneration: number,
    delayMs = POLL_INTERVAL_MS,
  ): void {
    clearPoll()
    if (
      expectedGeneration !== generation
      || !canConnect()
    ) {
      return
    }
    state('polling')
    pollTimer = environment.setTimeout(() => {
      pollTimer = undefined
      if (
        expectedGeneration !== generation
        || options === null
        || !canConnect()
      ) {
        return
      }
      void environment.poll(
        options.groupId,
        sequence,
      ).then((events) => {
        for (const event of events) {
          acceptEvent({
            groupId: event.group_id,
            sequence: event.sequence,
            type: event.event_type,
            payload: event.payload,
            occurredAt: event.occurred_at,
          }, expectedGeneration)
        }
      }).catch((error) => {
        options?.onError?.(error)
      }).finally(() => {
        schedulePoll(expectedGeneration)
      })
    }, delayMs)
  }

  function scheduleReconnect(
    expectedGeneration: number,
  ): void {
    clearReconnect()
    if (
      expectedGeneration !== generation
      || !canConnect()
    ) {
      return
    }
    const index = Math.min(
      failures - 1,
      RECONNECT_DELAYS.length - 1,
    )
    reconnectTimer = environment.setTimeout(() => {
      reconnectTimer = undefined
      connect(expectedGeneration)
    }, RECONNECT_DELAYS[Math.max(0, index)])
  }

  function connect(expectedGeneration: number): void {
    if (
      expectedGeneration !== generation
      || !canConnect()
      || options === null
    ) {
      return
    }
    abortConnection()
    clearReconnect()
    const controller = new AbortController()
    abortController = controller
    const targetGroup = options.groupId
    state('connecting')
    void environment.connect({
      groupId: targetGroup,
      lastSequence: sequence,
      signal: controller.signal,
      onOpen() {
        if (expectedGeneration !== generation) return
        failures = 0
        clearPoll()
        state('open')
      },
      onEvent(event) {
        acceptEvent(event, expectedGeneration)
      },
    }).then(() => {
      if (
        expectedGeneration === generation
        && !controller.signal.aborted
      ) {
        scheduleReconnect(expectedGeneration)
      }
    }).catch((error) => {
      if (
        expectedGeneration !== generation
        || controller.signal.aborted
      ) {
        return
      }
      failures += 1
      options?.onError?.(error)
      if (failures >= FALLBACK_AFTER_FAILURES) {
        schedulePoll(expectedGeneration, 0)
      }
      scheduleReconnect(expectedGeneration)
    })
  }

  function pause(): void {
    abortConnection()
    clearReconnect()
    clearPoll()
    state('paused')
  }

  function start(
    nextOptions: ResumableSSEStartOptions,
  ): void {
    generation += 1
    abortConnection()
    clearReconnect()
    clearPoll()
    failures = 0
    sequence = nextOptions.lastSequence ?? 0
    options = nextOptions
    started = true
    connect(generation)
  }

  function stop(): void {
    generation += 1
    started = false
    abortConnection()
    clearReconnect()
    clearPoll()
    state('stopped')
    options = null
  }

  function setVisible(nextVisible: boolean): void {
    if (visible === nextVisible) return
    visible = nextVisible
    if (!visible) {
      pause()
    } else if (canConnect()) {
      connect(generation)
    }
  }

  function setActive(nextActive: boolean): void {
    if (active === nextActive) return
    active = nextActive
    if (!active) {
      pause()
    } else if (canConnect()) {
      connect(generation)
    }
  }

  return {
    start,
    stop,
    setVisible,
    setActive,
    lastSequence: () => sequence,
  }
}
