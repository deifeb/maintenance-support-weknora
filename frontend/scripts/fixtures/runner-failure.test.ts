// Intentionally outside src: only the runner's propagation regression executes it.
import test from 'node:test'
import assert from 'node:assert/strict'
test('intentional runner failure', () => assert.fail('runner must propagate this failure'))
