import type { ImportTaskView } from '@/api/maintenance/imports'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import { isTerminalImportStatus } from './import-state'

export interface ImportTaskPollingTimerAdapter {
  setTimeout(
    callback: () => void | Promise<void>,
    delayMs: number,
  ): unknown
  clearTimeout(handle: unknown): void
}

export interface ImportTaskPollingOptions {
  load: () => Promise<ImportTaskView>
  onTask: (task: ImportTaskView) => void
  onError: (error: MaintenanceClientError) => void
  intervalMs?: number
  timers?: ImportTaskPollingTimerAdapter
  setTimeout?: ImportTaskPollingTimerAdapter['setTimeout']
  clearTimeout?: ImportTaskPollingTimerAdapter['clearTimeout']
  initialVisible?: boolean
  initialActive?: boolean
}

export interface ImportTaskPolling {
  start(): Promise<void>
  stop(): void
  setVisible(visible: boolean): void
  setActive(active: boolean): void
}

const DEFAULT_INTERVAL_MS = 2_000

const defaultTimers: ImportTaskPollingTimerAdapter = {
  setTimeout(callback, delayMs) {
    return globalThis.setTimeout(() => {
      void callback()
    }, delayMs)
  },
  clearTimeout(handle) {
    globalThis.clearTimeout(handle as ReturnType<typeof globalThis.setTimeout>)
  },
}

function timerAdapter(
  options: ImportTaskPollingOptions,
): ImportTaskPollingTimerAdapter {
  if (options.timers) {
    return options.timers
  }
  if (options.setTimeout && options.clearTimeout) {
    return {
      setTimeout: options.setTimeout,
      clearTimeout: options.clearTimeout,
    }
  }
  return defaultTimers
}

export function createImportTaskPolling(
  options: ImportTaskPollingOptions,
): ImportTaskPolling {
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error('Polling interval must be greater than zero')
  }

  const timers = timerAdapter(options)
  let started = false
  let halted = false
  let loading = false
  let visible = options.initialVisible ?? true
  let active = options.initialActive ?? true
  let refreshAfterLoad = false
  let timerHandle: unknown

  function canLoad(): boolean {
    return started && !halted && visible && active
  }

  function clearScheduledLoad(): void {
    if (timerHandle !== undefined) {
      timers.clearTimeout(timerHandle)
      timerHandle = undefined
    }
  }

  function schedule(): void {
    clearScheduledLoad()
    if (!canLoad() || loading) {
      return
    }
    timerHandle = timers.setTimeout(async () => {
      timerHandle = undefined
      await loadNow()
    }, intervalMs)
  }

  async function loadNow(): Promise<void> {
    if (!canLoad()) {
      return
    }
    if (loading) {
      refreshAfterLoad = true
      return
    }

    clearScheduledLoad()
    loading = true
    let terminal = false
    let failed = false

    try {
      const task = await options.load()
      terminal = isTerminalImportStatus(task.status)
      if (terminal) {
        halted = true
        refreshAfterLoad = false
      }
      options.onTask(task)
    } catch (error) {
      failed = true
      halted = true
      refreshAfterLoad = false
      options.onError(error as MaintenanceClientError)
    } finally {
      loading = false
      const refresh = refreshAfterLoad
      refreshAfterLoad = false

      if (!canLoad() || terminal || failed) {
        return
      }
      if (refresh) {
        await loadNow()
        return
      }
      schedule()
    }
  }

  async function start(): Promise<void> {
    if (started || halted) {
      return
    }
    started = true
    await loadNow()
  }

  function stop(): void {
    started = false
    refreshAfterLoad = false
    clearScheduledLoad()
  }

  function resumeIfPossible(): void {
    if (!canLoad()) {
      return
    }
    if (loading) {
      refreshAfterLoad = true
      return
    }
    void loadNow()
  }

  function setVisible(nextVisible: boolean): void {
    if (visible === nextVisible) {
      return
    }
    visible = nextVisible
    if (!visible) {
      clearScheduledLoad()
      return
    }
    resumeIfPossible()
  }

  function setActive(nextActive: boolean): void {
    if (active === nextActive) {
      return
    }
    active = nextActive
    if (!active) {
      clearScheduledLoad()
      return
    }
    resumeIfPossible()
  }

  return { start, stop, setVisible, setActive }
}
