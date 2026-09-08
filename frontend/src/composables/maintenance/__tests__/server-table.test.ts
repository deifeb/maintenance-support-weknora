import assert from 'node:assert/strict'
import test from 'node:test'

import type { PageData } from '../../../api/maintenance/types.ts'
import {
  createServerTableState,
  type ServerTableQuery,
} from '../useServerTable.ts'

interface Row {
  id: number
  name: string
}

function pageData(
  items: Row[],
  query: ServerTableQuery,
  total = items.length,
): PageData<Row> {
  return {
    items,
    page: query.page,
    page_size: query.page_size,
    total,
    pages: total === 0 ? 0 : Math.ceil(total / query.page_size),
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

test('refresh sends backend paging query and stores page data', async () => {
  const queries: ServerTableQuery[] = []
  const state = createServerTableState<Row>({
    initialPageSize: 50,
    initialSortBy: 'name',
    fetchPage: async (query) => {
      queries.push(query)
      return pageData([{ id: 1, name: 'Pump' }], query, 75)
    },
  })

  await state.refresh()

  assert.deepEqual(queries, [{
    page: 1,
    page_size: 50,
    include_inactive: false,
    sort_by: 'name',
    sort_order: 'asc',
  }])
  assert.deepEqual(state.rows.value, [{ id: 1, name: 'Pump' }])
  assert.equal(state.total.value, 75)
  assert.equal(state.pages.value, 2)
  assert.equal(state.loading.value, false)
})

test('keyword filtering resets page and refreshes once', async () => {
  const queries: ServerTableQuery[] = []
  const state = createServerTableState<Row>({
    initialPage: 4,
    fetchPage: async (query) => {
      queries.push(query)
      return pageData([], query)
    },
  })

  await state.setKeyword('  bearing  ')

  assert.equal(queries.length, 1)
  assert.equal(queries[0]?.page, 1)
  assert.equal(queries[0]?.keyword, 'bearing')
})

test('sorting resets page and toggles the current column', async () => {
  const queries: ServerTableQuery[] = []
  const state = createServerTableState<Row>({
    initialPage: 3,
    initialSortBy: 'id',
    fetchPage: async (query) => {
      queries.push(query)
      return pageData([], query)
    },
  })

  await state.setSort('name')
  await state.setSort('name')

  assert.deepEqual(
    queries.map((query) => ({
      page: query.page,
      sort_by: query.sort_by,
      sort_order: query.sort_order,
    })),
    [
      { page: 1, sort_by: 'name', sort_order: 'asc' },
      { page: 1, sort_by: 'name', sort_order: 'desc' },
    ],
  )
})

test('page size and inactive filtering reset to the first page', async () => {
  const queries: ServerTableQuery[] = []
  const state = createServerTableState<Row>({
    initialPage: 6,
    fetchPage: async (query) => {
      queries.push(query)
      return pageData([], query)
    },
  })

  await state.setPageSize(100)
  await state.setIncludeInactive(true)

  assert.deepEqual(
    queries.map((query) => ({
      page: query.page,
      page_size: query.page_size,
      include_inactive: query.include_inactive,
    })),
    [
      { page: 1, page_size: 100, include_inactive: false },
      { page: 1, page_size: 100, include_inactive: true },
    ],
  )
})

test('a stale response cannot overwrite the latest request', async () => {
  const first = deferred<PageData<Row>>()
  const second = deferred<PageData<Row>>()
  let callCount = 0
  const state = createServerTableState<Row>({
    fetchPage: async () => {
      callCount += 1
      return callCount === 1 ? first.promise : second.promise
    },
  })

  const firstRefresh = state.refresh()
  const secondRefresh = state.refresh()

  second.resolve({
    items: [{ id: 2, name: 'Latest' }],
    page: 1,
    page_size: 20,
    total: 1,
    pages: 1,
  })
  await secondRefresh

  first.resolve({
    items: [{ id: 1, name: 'Stale' }],
    page: 1,
    page_size: 20,
    total: 1,
    pages: 1,
  })
  await firstRefresh

  assert.deepEqual(state.rows.value, [{ id: 2, name: 'Latest' }])
  assert.equal(state.loading.value, false)
})

test('refresh failure preserves the last good page and normalizes error', async () => {
  let callCount = 0
  const state = createServerTableState<Row>({
    fetchPage: async (query) => {
      callCount += 1
      if (callCount === 1) {
        return pageData([{ id: 1, name: 'Good' }], query)
      }
      throw {
        status: 503,
        error: {
          code: 'MASTER_DATA_UNAVAILABLE',
          message: 'Service unavailable',
          request_id: 'req-503',
        },
      }
    },
  })

  await state.refresh()
  await state.refresh()

  assert.deepEqual(state.rows.value, [{ id: 1, name: 'Good' }])
  assert.deepEqual(state.error.value, {
    status: 503,
    code: 'MASTER_DATA_UNAVAILABLE',
    message: 'Service unavailable',
    request_id: 'req-503',
    retryable: true,
  })
})
