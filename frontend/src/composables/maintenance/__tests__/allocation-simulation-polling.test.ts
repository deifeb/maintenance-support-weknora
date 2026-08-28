import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import type {
  PollingTimerAdapter,
} from '../usePageVisibilityPolling.ts'

const here = dirname(fileURLToPath(import.meta.url))
const modulePath = resolve(
  here,
  '../useAllocationSimulationPolling.ts',
)
const moduleUrl = pathToFileURL(modulePath).href
const modulePresent = existsSync(modulePath)

interface ScheduledTask {
  dueAt: number
  callback: () => void | Promise<void>
}

interface SimulationLike {
  id: number
  status:
    | 'PENDING'
    | 'RUNNING'
    | 'COMPLETED'
    | 'FAILED'
    | 'CANCELLED'
}

class FakeTimers implements PollingTimerAdapter {
  now = 0
  private nextId = 1
  private readonly tasks = new Map<number, ScheduledTask>()

  setTimeout(
    callback: () => void | Promise<void>,
    delayMs: number,
  ): number {
    const id = this.nextId
    this.nextId += 1
    this.tasks.set(id, {
      dueAt: this.now + delayMs,
      callback,
    })
    return id
  }

  clearTimeout(handle: unknown): void {
    this.tasks.delete(Number(handle))
  }

  pendingCount(): number {
    return this.tasks.size
  }

  async advanceBy(milliseconds: number): Promise<void> {
    const target = this.now + milliseconds

    while (true) {
      const next = [...this.tasks.entries()]
        .filter(([, task]) => task.dueAt <= target)
        .sort((left, right) => {
          if (left[1].dueAt !== right[1].dueAt) {
            return left[1].dueAt - right[1].dueAt
          }
          return left[0] - right[0]
        })[0]

      if (!next) {
        break
      }

      const [id, task] = next
      this.tasks.delete(id)
      this.now = task.dueAt
      await task.callback()
    }

    this.now = target
  }
}

function simulation(
  id: number,
  status: SimulationLike['status'],
): SimulationLike {
  return { id, status }
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return { promise, resolve, reject }
}

async function flushAsync(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

async function loadModule(): Promise<Record<string, any>> {
  return import(moduleUrl)
}

test('allocation simulation polling production module is present', () => {
  assert.equal(
    modulePresent,
    true,
    (
      'Task 7 GREEN C must create '
      + 'frontend/src/composables/maintenance/'
      + 'useAllocationSimulationPolling.ts'
    ),
  )
})

test(
  'allocation simulation polling is REST-only with a 2000 ms default interval',
  { skip: !modulePresent },
  async () => {
    const source = readFileSync(modulePath, 'utf8')
    const module = await loadModule()

    assert.equal(
      module.ALLOCATION_SIMULATION_POLL_INTERVAL_MS,
      2000,
    )
    assert.doesNotMatch(source, /\bEventSource\b/)
    assert.doesNotMatch(source, /\buseResumableSSE\b/)
    assert.doesNotMatch(source, /\bfetchEventSource\b/)
    assert.doesNotMatch(
      source,
      /@microsoft\/fetch-event-source/,
    )
  },
)

test(
  'polling starts immediately and continues for PENDING and RUNNING',
  { skip: !modulePresent },
  async () => {
    const { createAllocationSimulationPolling } =
      await loadModule()

    const timers = new FakeTimers()
    const statuses: SimulationLike['status'][] = [
      'PENDING',
      'RUNNING',
      'RUNNING',
    ]
    let calls = 0

    const controller = createAllocationSimulationPolling({
      load: async () => {
        const status = statuses[calls] ?? 'RUNNING'
        calls += 1
        return simulation(calls, status)
      },
      timers,
    })

    await controller.start()
    assert.equal(calls, 1)
    assert.equal(timers.pendingCount(), 1)

    await timers.advanceBy(2000)
    assert.equal(calls, 2)
    assert.equal(timers.pendingCount(), 1)
  },
)

for (const terminal of [
  'COMPLETED',
  'FAILED',
  'CANCELLED',
] as const) {
  test(
    `polling stops after terminal simulation state ${terminal}`,
    { skip: !modulePresent },
    async () => {
      const { createAllocationSimulationPolling } =
        await loadModule()

      const timers = new FakeTimers()
      let calls = 0

      const controller = createAllocationSimulationPolling({
        load: async () => {
          calls += 1
          return simulation(calls, terminal)
        },
        timers,
      })

      await controller.start()

      assert.equal(calls, 1)
      assert.equal(timers.pendingCount(), 0)

      await timers.advanceBy(10_000)
      assert.equal(calls, 1)
    },
  )
}

test(
  'hidden state pauses and visible state refreshes immediately',
  { skip: !modulePresent },
  async () => {
    const { createAllocationSimulationPolling } =
      await loadModule()

    const timers = new FakeTimers()
    let calls = 0

    const controller = createAllocationSimulationPolling({
      load: async () => {
        calls += 1
        return simulation(calls, 'RUNNING')
      },
      timers,
    })

    await controller.start()
    assert.equal(calls, 1)

    controller.setVisible(false)
    await timers.advanceBy(6000)

    assert.equal(calls, 1)
    assert.equal(timers.pendingCount(), 0)

    controller.setVisible(true)
    await flushAsync()

    assert.equal(calls, 2)
    assert.equal(timers.pendingCount(), 1)
  },
)

test(
  'visibility refresh does not overlap an in-flight load',
  { skip: !modulePresent },
  async () => {
    const { createAllocationSimulationPolling } =
      await loadModule()

    const timers = new FakeTimers()
    const first = deferred<SimulationLike>()
    let calls = 0

    const controller = createAllocationSimulationPolling({
      load: async () => {
        calls += 1
        if (calls === 1) {
          return first.promise
        }
        return simulation(calls, 'RUNNING')
      },
      timers,
    })

    const starting = controller.start()
    await flushAsync()

    controller.setVisible(false)
    controller.setVisible(true)
    await flushAsync()

    assert.equal(calls, 1)

    first.resolve(simulation(1, 'RUNNING'))
    await starting
    assert.equal(timers.pendingCount(), 1)
  },
)

test(
  'stop clears scheduled work',
  { skip: !modulePresent },
  async () => {
    const { createAllocationSimulationPolling } =
      await loadModule()

    const timers = new FakeTimers()
    let calls = 0

    const controller = createAllocationSimulationPolling({
      load: async () => {
        calls += 1
        return simulation(calls, 'RUNNING')
      },
      timers,
    })

    await controller.start()
    assert.equal(timers.pendingCount(), 1)

    controller.stop()
    assert.equal(timers.pendingCount(), 0)

    await timers.advanceBy(10_000)
    assert.equal(calls, 1)
  },
)

test(
  'transient load error is reported and remains eligible for a later poll',
  { skip: !modulePresent },
  async () => {
    const { createAllocationSimulationPolling } =
      await loadModule()

    const timers = new FakeTimers()
    const errors: unknown[] = []
    let calls = 0

    const controller = createAllocationSimulationPolling({
      load: async () => {
        calls += 1
        if (calls === 1) {
          throw new Error('temporary read failure')
        }
        return simulation(calls, 'RUNNING')
      },
      onError: (error: unknown) => {
        errors.push(error)
      },
      timers,
    })

    await controller.start()

    assert.equal(calls, 1)
    assert.equal(errors.length, 1)
    assert.equal(timers.pendingCount(), 1)

    await timers.advanceBy(2000)

    assert.equal(calls, 2)
    assert.equal(timers.pendingCount(), 1)
  },
)
