import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createAutosaveController,
  type AutosaveTimerAdapter,
} from '../useDebouncedAutosave.ts'

interface ScheduledTask {
  dueAt: number
  callback: () => void | Promise<void>
}

class FakeTimers implements AutosaveTimerAdapter {
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

  async advanceBy(milliseconds: number): Promise<void> {
    const target = this.now + milliseconds
    while (true) {
      const next = [...this.tasks.entries()]
        .filter(([, task]) => task.dueAt <= target)
        .sort((left, right) => (
          left[1].dueAt - right[1].dueAt
        ))[0]
      if (!next) break
      const [id, task] = next
      this.tasks.delete(id)
      this.now = task.dueAt
      await task.callback()
    }
    this.now = target
  }
}

test('rapid edits save only the latest generation', async () => {
  const saved: string[] = []
  const timers = new FakeTimers()
  const controller = createAutosaveController<string>({
    delayMs: 800,
    timers,
    save: async (value) => {
      saved.push(value)
      return { version: saved.length + 1 }
    },
  })

  controller.schedule('a')
  controller.schedule('b')
  controller.schedule('c')
  await timers.advanceBy(800)

  assert.deepEqual(saved, ['c'])
  assert.equal(controller.state().dirty, false)
  assert.equal(controller.state().status, 'saved')
})

test('conflict remains dirty and never overwrites local data', async () => {
  const sampleDraft = { scenario_name: 'Local edit' }
  const controller = createAutosaveController({
    delayMs: 1,
    save: async () => {
      throw {
        code: 'SCENARIO_DRAFT_VERSION_CONFLICT',
        details: { actual_version: 4 },
      }
    },
  })

  controller.schedule(sampleDraft)
  await controller.flush()

  assert.equal(controller.state().status, 'conflict')
  assert.equal(controller.state().dirty, true)
  assert.deepEqual(
    controller.state().pendingValue,
    sampleDraft,
  )
})

test('edits during a save are serialized into one latest follow-up', async () => {
  const started: string[] = []
  const resolvers: Array<() => void> = []
  const controller = createAutosaveController<string>({
    delayMs: 1,
    save: async (value) => {
      started.push(value)
      await new Promise<void>((resolve) => {
        resolvers.push(resolve)
      })
      return { version: started.length }
    },
  })

  controller.schedule('first')
  const flushing = controller.flush()
  await Promise.resolve()
  controller.schedule('middle')
  controller.schedule('latest')
  assert.deepEqual(started, ['first'])

  resolvers.shift()?.()
  await Promise.resolve()
  await Promise.resolve()
  assert.deepEqual(started, ['first', 'latest'])
  resolvers.shift()?.()
  await flushing

  assert.equal(controller.state().dirty, false)
  assert.equal(controller.state().status, 'saved')
})

test('dispose invalidates pending timers and in-flight results', async () => {
  const timers = new FakeTimers()
  let resolveSave: (() => void) | undefined
  const controller = createAutosaveController<string>({
    delayMs: 10,
    timers,
    save: async () => {
      await new Promise<void>((resolve) => {
        resolveSave = resolve
      })
      return { version: 2 }
    },
  })

  controller.schedule('pending')
  controller.dispose()
  await timers.advanceBy(10)
  assert.equal(controller.state().status, 'idle')

  const second = createAutosaveController<string>({
    delayMs: 1,
    save: async () => {
      await new Promise<void>((resolve) => {
        resolveSave = resolve
      })
      return { version: 2 }
    },
  })
  second.schedule('saving')
  const flushing = second.flush()
  await Promise.resolve()
  second.dispose()
  resolveSave?.()
  await flushing

  assert.equal(second.state().status, 'idle')
  assert.equal(second.state().dirty, false)
})
