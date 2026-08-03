import {
  computed,
  ref,
  type ComputedRef,
  type Ref,
} from 'vue'

import { normalizeMaintenanceError } from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  PageData,
} from '../../api/maintenance/types'

export type ServerTableSortOrder = 'asc' | 'desc'

export interface ServerTableQuery {
  page: number
  page_size: number
  keyword?: string
  include_inactive: boolean
  sort_by: string
  sort_order: ServerTableSortOrder
}

export interface ServerTableOptions<T> {
  fetchPage: (query: ServerTableQuery) => Promise<PageData<T>>
  initialPage?: number
  initialPageSize?: number
  initialSortBy?: string
  initialSortOrder?: ServerTableSortOrder
  initialIncludeInactive?: boolean
  normalizeError?: (value: unknown) => MaintenanceClientError
}

export interface ServerTableState<T> {
  rows: Ref<T[]>
  page: Ref<number>
  pageSize: Ref<number>
  total: Ref<number>
  pages: Ref<number>
  keyword: Ref<string>
  includeInactive: Ref<boolean>
  sortBy: Ref<string>
  sortOrder: Ref<ServerTableSortOrder>
  loading: Ref<boolean>
  error: Ref<MaintenanceClientError | null>
  query: ComputedRef<ServerTableQuery>
  refresh: () => Promise<void>
  setKeyword: (value: string) => Promise<void>
  setPage: (value: number) => Promise<void>
  setPageSize: (value: number) => Promise<void>
  setSort: (column: string) => Promise<void>
  setIncludeInactive: (value: boolean) => Promise<void>
  reset: (overrides?: Partial<ServerTableQuery>) => void
}

function positiveInteger(value: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback
  }
  return Math.max(1, Math.trunc(value))
}

export function createServerTableState<T>(
  options: ServerTableOptions<T>,
): ServerTableState<T> {
  const defaults: ServerTableQuery = {
    page: positiveInteger(options.initialPage ?? 1, 1),
    page_size: positiveInteger(options.initialPageSize ?? 20, 20),
    keyword: '',
    include_inactive: options.initialIncludeInactive ?? false,
    sort_by: options.initialSortBy ?? 'id',
    sort_order: options.initialSortOrder ?? 'asc',
  }

  const rows = ref<T[]>([]) as Ref<T[]>
  const page = ref(defaults.page)
  const pageSize = ref(defaults.page_size)
  const total = ref(0)
  const pages = ref(0)
  const keyword = ref(defaults.keyword ?? '')
  const includeInactive = ref(defaults.include_inactive)
  const sortBy = ref(defaults.sort_by)
  const sortOrder = ref<ServerTableSortOrder>(defaults.sort_order)
  const loading = ref(false)
  const error = ref<MaintenanceClientError | null>(null)
  const normalizeError = options.normalizeError ?? normalizeMaintenanceError

  let requestVersion = 0

  const query = computed<ServerTableQuery>(() => {
    const value: ServerTableQuery = {
      page: page.value,
      page_size: pageSize.value,
      include_inactive: includeInactive.value,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }

    const trimmedKeyword = keyword.value.trim()
    if (trimmedKeyword) {
      value.keyword = trimmedKeyword
    }

    return value
  })

  async function refresh(): Promise<void> {
    const currentVersion = requestVersion + 1
    requestVersion = currentVersion
    loading.value = true

    try {
      const result = await options.fetchPage({ ...query.value })
      if (currentVersion !== requestVersion) {
        return
      }

      rows.value = result.items
      page.value = result.page
      pageSize.value = result.page_size
      total.value = result.total
      pages.value = result.pages
      error.value = null
    } catch (value) {
      if (currentVersion !== requestVersion) {
        return
      }
      error.value = normalizeError(value)
    } finally {
      if (currentVersion === requestVersion) {
        loading.value = false
      }
    }
  }

  async function setKeyword(value: string): Promise<void> {
    keyword.value = value.trim()
    page.value = 1
    await refresh()
  }

  async function setPage(value: number): Promise<void> {
    page.value = positiveInteger(value, 1)
    await refresh()
  }

  async function setPageSize(value: number): Promise<void> {
    pageSize.value = positiveInteger(value, defaults.page_size)
    page.value = 1
    await refresh()
  }

  async function setSort(column: string): Promise<void> {
    if (sortBy.value === column) {
      sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortBy.value = column
      sortOrder.value = 'asc'
    }
    page.value = 1
    await refresh()
  }

  async function setIncludeInactive(value: boolean): Promise<void> {
    includeInactive.value = value
    page.value = 1
    await refresh()
  }

  function reset(overrides: Partial<ServerTableQuery> = {}): void {
    requestVersion += 1
    rows.value = []
    page.value = positiveInteger(overrides.page ?? defaults.page, defaults.page)
    pageSize.value = positiveInteger(
      overrides.page_size ?? defaults.page_size,
      defaults.page_size,
    )
    total.value = 0
    pages.value = 0
    keyword.value = overrides.keyword ?? defaults.keyword ?? ''
    includeInactive.value = overrides.include_inactive ?? defaults.include_inactive
    sortBy.value = overrides.sort_by ?? defaults.sort_by
    sortOrder.value = overrides.sort_order ?? defaults.sort_order
    loading.value = false
    error.value = null
  }

  return {
    rows,
    page,
    pageSize,
    total,
    pages,
    keyword,
    includeInactive,
    sortBy,
    sortOrder,
    loading,
    error,
    query,
    refresh,
    setKeyword,
    setPage,
    setPageSize,
    setSort,
    setIncludeInactive,
    reset,
  }
}

export const useServerTable = createServerTableState
