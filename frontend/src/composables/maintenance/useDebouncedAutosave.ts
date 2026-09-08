export type AutosaveStatus =
  | 'idle'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'error'
  | 'conflict'

export interface AutosaveResult {
  version: number
}

export interface AutosaveState<T> {
  status: AutosaveStatus
  dirty: boolean
  pendingValue?: T
  error?: unknown
  version?: number
  lastSavedAt?: number
}

export interface AutosaveTimerAdapter {
  setTimeout(
    callback: () => void | Promise<void>,
    delayMs: number,
  ): unknown
  clearTimeout(handle: unknown): void
}

export interface AutosaveControllerOptions<T> {
  delayMs: number
  save: (value: T) => Promise<AutosaveResult>
  timers?: AutosaveTimerAdapter
  onStateChange?: (state: AutosaveState<T>) => void
  now?: () => number
}

export interface AutosaveController<T> {
  schedule(value: T): void
  flush(): Promise<void>
  retry(): Promise<void>
  reset(): void
  dispose(): void
  state(): AutosaveState<T>
}

const defaultTimers: AutosaveTimerAdapter = {
  setTimeout(callback, delayMs) {
    return globalThis.setTimeout(() => {
      void callback()
    }, delayMs)
  },
  clearTimeout(handle) {
    globalThis.clearTimeout(
      handle as ReturnType<typeof globalThis.setTimeout>,
    )
  },
}

function isConflict(error: unknown): boolean {
  if (
    typeof error !== 'object'
    || error === null
  ) {
    return false
  }
  const record = error as Record<string, unknown>
  if (
    record.code
    === 'SCENARIO_DRAFT_VERSION_CONFLICT'
  ) {
    return true
  }
  const nested = record.error
  return (
    typeof nested === 'object'
    && nested !== null
    && (
      nested as Record<string, unknown>
    ).code === 'SCENARIO_DRAFT_VERSION_CONFLICT'
  )
}

export function createAutosaveController<T>(
  options: AutosaveControllerOptions<T>,
): AutosaveController<T> {
  if (
    !Number.isFinite(options.delayMs)
    || options.delayMs < 0
  ) {
    throw new Error(
      'Autosave delay must be zero or greater',
    )
  }

  const timers = options.timers ?? defaultTimers
  const now = options.now ?? Date.now
  let snapshot: AutosaveState<T> = {
    status: 'idle',
    dirty: false,
  }
  let timerHandle: unknown
  let pendingValue: T | undefined
  let hasPending = false
  let generation = 0
  let epoch = 0
  let disposed = false
  let runner: Promise<void> | undefined

  function copyState(): AutosaveState<T> {
    return { ...snapshot }
  }

  function emit(
    patch: Partial<AutosaveState<T>>,
  ): void {
    snapshot = {
      ...snapshot,
      ...patch,
    }
    if (!snapshot.dirty) {
      delete snapshot.pendingValue
    }
    if (
      snapshot.status !== 'error'
      && snapshot.status !== 'conflict'
    ) {
      delete snapshot.error
    }
    options.onStateChange?.(copyState())
  }

  function clearTimer(): void {
    if (timerHandle === undefined) return
    timers.clearTimeout(timerHandle)
    timerHandle = undefined
  }

  async function executeLoop(
    runEpoch: number,
  ): Promise<void> {
    while (
      !disposed
      && runEpoch === epoch
      && hasPending
    ) {
      const value = pendingValue as T
      const savingGeneration = generation
      emit({
        status: 'saving',
        dirty: true,
        pendingValue: value,
      })

      try {
        const result = await options.save(value)
        if (
          disposed
          || runEpoch !== epoch
        ) {
          return
        }
        const stillLatest = (
          savingGeneration === generation
        )
        emit({
          version: result.version,
          lastSavedAt: now(),
        })
        if (stillLatest) {
          hasPending = false
          pendingValue = undefined
          emit({
            status: 'saved',
            dirty: false,
          })
          return
        }
      } catch (error) {
        if (
          disposed
          || runEpoch !== epoch
        ) {
          return
        }
        emit({
          status: (
            isConflict(error)
              ? 'conflict'
              : 'error'
          ),
          dirty: true,
          pendingValue,
          error,
        })
        return
      }
    }
  }

  function requestRun(): Promise<void> {
    clearTimer()
    if (
      disposed
      || !hasPending
      || snapshot.status === 'conflict'
    ) {
      return Promise.resolve()
    }
    if (runner) {
      return runner.then(() => {
        if (
          !disposed
          && hasPending
          && snapshot.status !== 'error'
          && snapshot.status !== 'conflict'
        ) {
          return requestRun()
        }
      })
    }

    const active = executeLoop(epoch)
    runner = active
    void active.finally(() => {
      if (runner === active) {
        runner = undefined
      }
    })
    return active
  }

  function schedule(value: T): void {
    if (disposed) return
    pendingValue = value
    hasPending = true
    generation += 1
    const conflicted = (
      snapshot.status === 'conflict'
    )
    emit({
      status: conflicted ? 'conflict' : 'dirty',
      dirty: true,
      pendingValue: value,
    })
    clearTimer()
    if (conflicted) return
    timerHandle = timers.setTimeout(() => {
      timerHandle = undefined
      return requestRun()
    }, options.delayMs)
  }

  function resetState(): void {
    clearTimer()
    epoch += 1
    generation = 0
    hasPending = false
    pendingValue = undefined
    snapshot = {
      status: 'idle',
      dirty: false,
    }
    options.onStateChange?.(copyState())
  }

  return {
    schedule,
    flush: requestRun,
    async retry(): Promise<void> {
      if (disposed || !hasPending) return
      emit({
        status: 'dirty',
        dirty: true,
        pendingValue,
      })
      await requestRun()
    },
    reset(): void {
      if (disposed) return
      resetState()
    },
    dispose(): void {
      if (disposed) return
      disposed = true
      resetState()
    },
    state: copyState,
  }
}
