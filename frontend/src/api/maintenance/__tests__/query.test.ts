import assert from 'node:assert/strict'
import test from 'node:test'

import { buildQuery } from '../client.ts'

test('buildQuery omits nullish and empty values while preserving false and zero', () => {
  assert.equal(
    buildQuery({
      page: 2,
      keyword: null,
      missing: undefined,
      empty: '',
      include_inactive: false,
      offset: 0,
      sort_by: 'code',
    }),
    'page=2&include_inactive=false&offset=0&sort_by=code',
  )
})

test('buildQuery encodes scalar values with URLSearchParams', () => {
  assert.equal(
    buildQuery({
      keyword: 'pump seal/轴承',
      active: true,
    }),
    new URLSearchParams({
      keyword: 'pump seal/轴承',
      active: 'true',
    }).toString(),
  )
})
