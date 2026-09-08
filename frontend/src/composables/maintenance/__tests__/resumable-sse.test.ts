import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createResumableSSE,
  type ResumableSSEEnvironment,
  type ResumableSSEEvent,
} from '../useResumableSSE.ts'

interface Connection {
  groupId: number
  lastSequence: number
  signal: AbortSignal
  emit(event: ResumableSSEEvent): void
}

function fakeEnvironment(): {
  environment: ResumableSSEEnvironment
  connections: Connection[]
} {
  const connections: Connection[] = []
  return {
    connections,
    environment: {
      connect(options) {
        connections.push({
          groupId: options.groupId,
          lastSequence: options.lastSequence,
          signal: options.signal,
          emit: options.onEvent,
        })
        options.onOpen()
        return new Promise(() => undefined)
      },
      async poll() {
        return []
      },
      setTimeout(callback) {
        return globalThis.setTimeout(callback, 60_000)
      },
      clearTimeout(handle) {
        globalThis.clearTimeout(
          handle as ReturnType<typeof globalThis.setTimeout>,
        )
      },
    },
  }
}

test('visibility resume reconnects from last sequence', () => {
  const fake = fakeEnvironment()
  const received: number[] = []
  const source = createResumableSSE(fake.environment)
  source.start({
    groupId: 8,
    lastSequence: 12,
    onEvent(event) {
      received.push(event.sequence)
    },
  })
  fake.connections[0]?.emit({
    groupId: 8,
    sequence: 13,
    type: 'child.progress',
    payload: {},
  })

  source.setVisible(false)
  assert.equal(
    fake.connections[0]?.signal.aborted,
    true,
  )
  source.setVisible(true)

  assert.equal(fake.connections.length, 2)
  assert.equal(
    fake.connections.at(-1)?.lastSequence,
    13,
  )
  assert.deepEqual(received, [13])
})

test('stale generation callbacks cannot advance the cursor', () => {
  const fake = fakeEnvironment()
  const source = createResumableSSE(fake.environment)
  source.start({
    groupId: 8,
    lastSequence: 4,
    onEvent() {},
  })
  const stale = fake.connections[0]
  source.start({
    groupId: 9,
    lastSequence: 1,
    onEvent() {},
  })

  stale?.emit({
    groupId: 8,
    sequence: 99,
    type: 'child.completed',
    payload: {},
  })
  source.setVisible(false)
  source.setVisible(true)

  assert.equal(
    fake.connections.at(-1)?.groupId,
    9,
  )
  assert.equal(
    fake.connections.at(-1)?.lastSequence,
    1,
  )
})

test('repeated SSE failures activate polling fallback', async () => {
  const timers: Array<{
    callback: () => void
    delay: number
    cancelled: boolean
  }> = []
  let connectCalls = 0
  let pollCalls = 0
  const environment: ResumableSSEEnvironment = {
    async connect() {
      connectCalls += 1
      throw new Error('offline')
    },
    async poll() {
      pollCalls += 1
      return []
    },
    setTimeout(callback, delay) {
      const timer = {
        callback,
        delay,
        cancelled: false,
      }
      timers.push(timer)
      return timer
    },
    clearTimeout(handle) {
      ;(handle as typeof timers[number]).cancelled = true
    },
  }
  const source = createResumableSSE(environment)
  source.start({
    groupId: 5,
    onEvent() {},
  })

  for (let attempt = 0; attempt < 2; attempt += 1) {
    await Promise.resolve()
    await Promise.resolve()
    const reconnect = timers.find(
      (timer) => !timer.cancelled && timer.delay > 0,
    )
    assert.ok(reconnect)
    reconnect.cancelled = true
    reconnect.callback()
  }
  await Promise.resolve()
  await Promise.resolve()
  const fallback = timers.find(
    (timer) => !timer.cancelled && timer.delay === 0,
  )
  assert.ok(fallback)
  fallback.cancelled = true
  fallback.callback()
  await Promise.resolve()
  await Promise.resolve()

  assert.equal(connectCalls, 3)
  assert.equal(pollCalls, 1)
  source.stop()
})
