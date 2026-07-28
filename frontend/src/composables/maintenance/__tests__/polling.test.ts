import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createPollingController,
  type PollingTimerAdapter,
} from '../usePageVisibilityPolling.ts'

interface ScheduledTask {
  dueAt: number
  callback: () => void | Promise<void>
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

test('polling runs immediately and then every interval', async () => {
  const calls: number[] = []
  const timers = new FakeTimers()
  const controller = createPollingController({
    intervalMs: 30_000,
    run: async () => {
      calls.push(timers.now)
    },
    timers,
  })

  await controller.start()
  assert.deepEqual(calls, [0])

  await timers.advanceBy(30_000)
  assert.deepEqual(calls, [0, 30_000])
})

test('hidden state pauses and visible state refreshes immediately', async () => {
  const calls: number[] = []
  const timers = new FakeTimers()
  const controller = createPollingController({
    intervalMs: 30_000,
    run: async () => {
      calls.push(timers.now)
    },
    timers,
  })

  await controller.start()
  controller.setVisible(false)
  await timers.advanceBy(60_000)
  assert.deepEqual(calls, [0])
  assert.equal(timers.pendingCount(), 0)

  controller.setVisible(true)
  assert.deepEqual(calls, [0, 60_000])
})

test('inactive route pauses and reactivation refreshes immediately', async () => {
  const calls: number[] = []
  const timers = new FakeTimers()
  const controller = createPollingController({
    intervalMs: 30_000,
    run: async () => {
      calls.push(timers.now)
    },
    timers,
  })

  await controller.start()
  controller.setActive(false)
  await timers.advanceBy(30_000)
  assert.deepEqual(calls, [0])

  controller.setActive(true)
  assert.deepEqual(calls, [0, 30_000])
})

test('stop cancels scheduled work', async () => {
  const calls: number[] = []
  const timers = new FakeTimers()
  const controller = createPollingController({
    intervalMs: 30_000,
    run: async () => {
      calls.push(timers.now)
    },
    timers,
  })

  await controller.start()
  assert.equal(timers.pendingCount(), 1)

  controller.stop()
  assert.equal(timers.pendingCount(), 0)
  await timers.advanceBy(60_000)
  assert.deepEqual(calls, [0])
})
