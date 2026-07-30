import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createImportTaskPolling,
  type ImportTaskPollingTimerAdapter,
} from '../useImportTaskPolling.ts'
import type { ImportTaskView } from '@/api/maintenance/imports.ts'

class FakeTimers implements ImportTaskPollingTimerAdapter {
  private nextId = 1
  private readonly callbacks = new Map<number, () => void | Promise<void>>()

  setTimeout(callback: () => void | Promise<void>): number {
    const id = this.nextId++
    this.callbacks.set(id, callback)
    return id
  }

  clearTimeout(handle: unknown): void {
    this.callbacks.delete(Number(handle))
  }

  get pendingCount(): number {
    return this.callbacks.size
  }

  async runNext(): Promise<void> {
    const next = this.callbacks.entries().next().value as [number, () => void | Promise<void>] | undefined
    if (!next) return
    this.callbacks.delete(next[0])
    await next[1]()
  }
}

function task(status: string): ImportTaskView {
  return {
    task_id: 'task-1', status, original_filename: 'parts.xlsx', file_sha256: 'hash',
    template_version: 'v1', sheets: [], preview: {}, errors: [], warnings: [], can_execute: true,
    created_at: 'now', expires_at: 'later', started_at: null, finished_at: null,
    result: null, error_code: null, error_message: null,
  }
}

test('poller loads immediately, continues only nonterminal tasks, and clears terminal timers', async () => {
  const timers = new FakeTimers()
  const observed: string[] = []
  const responses = [task('RUNNING'), task('COMPLETED')]
  const poller = createImportTaskPolling({
    intervalMs: 1,
    load: async () => responses.shift()!,
    onTask: (next) => observed.push(next.status),
    onError: () => assert.fail('unexpected poll error'),
    timers,
  })

  await poller.start()
  assert.deepEqual(observed, ['RUNNING'])
  assert.equal(timers.pendingCount, 1)

  await timers.runNext()
  assert.deepEqual(observed, ['RUNNING', 'COMPLETED'])
  assert.equal(timers.pendingCount, 0)
})

test('terminal completion permanently halts visibility and activity resume loads', async () => {
  const timers = new FakeTimers()
  let loads = 0
  const poller = createImportTaskPolling({
    intervalMs: 1,
    load: async () => { loads += 1; return task('COMPLETED') },
    onTask: () => undefined,
    onError: () => assert.fail('unexpected poll error'),
    timers,
  })

  await poller.start()
  poller.setVisible(false)
  poller.setVisible(true)
  poller.setActive(false)
  poller.setActive(true)
  await Promise.resolve()

  assert.equal(loads, 1)
  assert.equal(timers.pendingCount, 0)
})

test('poll errors permanently halt visibility and activity resume loads', async () => {
  const timers = new FakeTimers()
  let loads = 0
  let errors = 0
  const poller = createImportTaskPolling({
    intervalMs: 1,
    load: async () => {
      loads += 1
      throw { code: 'NETWORK', message: 'offline', retryable: true }
    },
    onTask: () => assert.fail('unexpected task'),
    onError: () => { errors += 1 },
    timers,
  })

  await poller.start()
  poller.setActive(false)
  poller.setActive(true)
  poller.setVisible(false)
  poller.setVisible(true)
  await poller.start()

  assert.equal(loads, 1)
  assert.equal(errors, 1)
  assert.equal(timers.pendingCount, 0)
})

test('hidden or inactive polling pauses and reactivation refreshes immediately', async () => {
  const timers = new FakeTimers()
  let loads = 0
  const poller = createImportTaskPolling({
    intervalMs: 1,
    load: async () => { loads += 1; return task('RUNNING') },
    onTask: () => undefined,
    onError: () => assert.fail('unexpected poll error'),
    timers,
  })
  await poller.start()
  poller.setVisible(false)
  assert.equal(timers.pendingCount, 0)
  await timers.runNext()
  assert.equal(loads, 1)

  poller.setVisible(true)
  assert.equal(loads, 2)
  poller.setActive(false)
  assert.equal(timers.pendingCount, 0)
  poller.setActive(true)
  await Promise.resolve()
  assert.equal(loads, 3)
})

test('poller never overlaps loads and stop prevents later scheduling', async () => {
  const timers = new FakeTimers()
  let release: (() => void) | undefined
  let loads = 0
  const waiting = new Promise<void>((resolve) => { release = resolve })
  const poller = createImportTaskPolling({
    intervalMs: 1,
    load: async () => { loads += 1; await waiting; return task('RUNNING') },
    onTask: () => undefined,
    onError: () => assert.fail('unexpected poll error'),
    timers,
  })
  const first = poller.start()
  await Promise.resolve()
  assert.equal(loads, 1)

  poller.setVisible(false)
  poller.setVisible(true)
  assert.equal(loads, 1)
  poller.stop()
  release?.()
  await first
  assert.equal(timers.pendingCount, 0)
  await timers.runNext()
  assert.equal(loads, 1)
})
