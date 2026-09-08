import {
  onBeforeUnmount,
  onMounted,
  watch,
  type WatchStopHandle,
} from 'vue'

export interface PollingTimerAdapter {
  setTimeout(
    callback: () => void | Promise<void>,
    delayMs: number,
  ): unknown
  clearTimeout(handle: unknown): void
}

export interface PollingControllerOptions {
  intervalMs: number
  run: () => void | Promise<void>
  timers?: PollingTimerAdapter
  initialVisible?: boolean
  initialActive?: boolean
}

export interface PollingController {
  start(): Promise<void>
  stop(): void
  setVisible(visible: boolean): void
  setActive(active: boolean): void
}

const defaultTimers: PollingTimerAdapter = {
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

export function createPollingController(
  options: PollingControllerOptions,
): PollingController {
  if (!Number.isFinite(options.intervalMs) || options.intervalMs <= 0) {
    throw new Error('Polling interval must be greater than zero')
  }

  const timers = options.timers ?? defaultTimers
  let started = false
  let running = false
  let visible = options.initialVisible ?? true
  let active = options.initialActive ?? true
  let timerHandle: unknown

  function canRun(): boolean {
    return started && visible && active
  }

  function clearTimer(): void {
    if (timerHandle !== undefined) {
      timers.clearTimeout(timerHandle)
      timerHandle = undefined
    }
  }

  function schedule(): void {
    clearTimer()

    if (!canRun()) {
      return
    }

    timerHandle = timers.setTimeout(async () => {
      timerHandle = undefined
      await execute()
    }, options.intervalMs)
  }

  async function execute(): Promise<void> {
    if (!canRun() || running) {
      return
    }

    clearTimer()
    running = true

    try {
      await options.run()
    } finally {
      running = false
      schedule()
    }
  }

  async function start(): Promise<void> {
    if (started) {
      return
    }

    started = true
    await execute()
  }

  function stop(): void {
    started = false
    clearTimer()
  }

  function setVisible(nextVisible: boolean): void {
    if (visible === nextVisible) {
      return
    }

    visible = nextVisible

    if (!visible) {
      clearTimer()
      return
    }

    if (canRun()) {
      void execute()
    }
  }

  function setActive(nextActive: boolean): void {
    if (active === nextActive) {
      return
    }

    active = nextActive

    if (!active) {
      clearTimer()
      return
    }

    if (canRun()) {
      void execute()
    }
  }

  return {
    start,
    stop,
    setVisible,
    setActive,
  }
}

export interface PageVisibilityPollingOptions {
  intervalMs: number
  run: () => void | Promise<void>
  isActive: () => boolean
}

export function usePageVisibilityPolling(
  options: PageVisibilityPollingOptions,
): PollingController {
  const hasDocument = typeof document !== 'undefined'
  const controller = createPollingController({
    intervalMs: options.intervalMs,
    run: options.run,
    initialActive: options.isActive(),
    initialVisible: (
      !hasDocument
      || document.visibilityState === 'visible'
    ),
  })

  let stopActiveWatch: WatchStopHandle | undefined

  function syncVisibility(): void {
    controller.setVisible(
      !hasDocument
      || document.visibilityState === 'visible',
    )
  }

  onMounted(() => {
    stopActiveWatch = watch(
      options.isActive,
      (isActive) => controller.setActive(isActive),
      { flush: 'sync' },
    )

    if (hasDocument) {
      document.addEventListener(
        'visibilitychange',
        syncVisibility,
      )
    }

    controller.setActive(options.isActive())
    syncVisibility()
    void controller.start()
  })

  onBeforeUnmount(() => {
    stopActiveWatch?.()

    if (hasDocument) {
      document.removeEventListener(
        'visibilitychange',
        syncVisibility,
      )
    }

    controller.stop()
  })

  return controller
}
