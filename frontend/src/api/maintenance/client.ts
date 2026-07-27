import type {
  MaintenanceClientError,
  MaintenanceResponse,
  MaintenanceResult,
} from './types'

const PREFIX = '/api/maintenance'
const DEFAULT_ERROR_CODE = 'MAINTENANCE_CLIENT_ERROR'
const DEFAULT_ERROR_MESSAGE = 'Maintenance request failed'

type QueryValue = string | number | boolean | null | undefined
type UnknownRecord = Record<string, unknown>

export interface MaintenanceRequestAdapter {
  get<T>(url: string, config?: unknown): Promise<T>
  post<T>(url: string, body?: unknown, config?: unknown): Promise<T>
  put<T>(url: string, body?: unknown, config?: unknown): Promise<T>
  patch<T>(url: string, body?: unknown, config?: unknown): Promise<T>
  del<T>(url: string, body?: unknown): Promise<T>
}

export type MaintenanceRequestLoader =
  () => Promise<MaintenanceRequestAdapter>

export interface MaintenanceClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(path: string, body: unknown, config?: unknown): Promise<MaintenanceResult<T>>
  put<T>(path: string, body: unknown): Promise<MaintenanceResult<T>>
  patch<T>(path: string, body: unknown): Promise<MaintenanceResult<T>>
  delete<T>(path: string, body?: unknown): Promise<MaintenanceResult<T>>
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null
}

function readString(
  record: UnknownRecord,
  key: string,
): string | undefined {
  const value = record[key]
  return typeof value === 'string' && value.length > 0
    ? value
    : undefined
}

function retryableForStatus(status: number | undefined): boolean {
  return (
    status === undefined
    || status === 408
    || status === 429
    || status >= 500
  )
}

export function buildQuery(
  values: Record<string, QueryValue>,
): string {
  const params = new URLSearchParams()

  Object.entries(values).forEach(([key, value]) => {
    if (
      value !== null
      && value !== undefined
      && value !== ''
    ) {
      params.set(key, String(value))
    }
  })

  return params.toString()
}

export function unwrapMaintenanceResponse<T>(
  response: MaintenanceResponse<T>,
): MaintenanceResult<T> {
  if (
    !isRecord(response)
    || response.success !== true
    || !('data' in response)
    || typeof response.message !== 'string'
    || !isRecord(response.meta)
    || !readString(response.meta, 'request_id')
    || !readString(response.meta, 'tenant_id')
  ) {
    throw new Error('Invalid maintenance response')
  }

  return {
    data: response.data,
    meta: response.meta,
  }
}

export function normalizeMaintenanceError(
  error: unknown,
): MaintenanceClientError {
  const source = isRecord(error) ? error : {}
  const nested = isRecord(source.error)
    ? source.error
    : {}
  const meta = isRecord(source.meta)
    ? source.meta
    : {}

  const status = typeof source.status === 'number'
    ? source.status
    : undefined
  const details = nested.details ?? source.details
  const requestId = (
    readString(nested, 'request_id')
    ?? readString(source, 'request_id')
    ?? readString(meta, 'request_id')
  )

  const result: MaintenanceClientError = {
    code: (
      readString(nested, 'code')
      ?? readString(source, 'code')
      ?? DEFAULT_ERROR_CODE
    ),
    message: (
      readString(nested, 'message')
      ?? readString(source, 'message')
      ?? DEFAULT_ERROR_MESSAGE
    ),
    retryable: typeof source.retryable === 'boolean'
      ? source.retryable
      : retryableForStatus(status),
  }

  if (status !== undefined) {
    result.status = status
  }
  if (details !== undefined) {
    result.details = details
  }
  if (requestId !== undefined) {
    result.request_id = requestId
  }

  return result
}

async function loadDefaultRequestAdapter(
): Promise<MaintenanceRequestAdapter> {
  const { del, get, patch, post, put } =
    await import('@/utils/request')

  return {
    get<T>(url: string, config?: unknown): Promise<T> {
      return get<T>(url, config)
    },
    post<T>(url: string, body?: unknown, config?: unknown): Promise<T> {
      return post<T>(url, body as object, config)
    },
    put<T>(url: string, body?: unknown, config?: unknown): Promise<T> {
      return put<T>(url, body as object, config)
    },
    patch<T>(url: string, body?: unknown, config?: unknown): Promise<T> {
      return patch<T>(url, body as object, config)
    },
    del<T>(url: string, body?: unknown): Promise<T> {
      return del<T>(url, body)
    },
  }
}

export function createMaintenanceClient(
  loadRequestAdapter: MaintenanceRequestLoader = loadDefaultRequestAdapter,
): MaintenanceClient {
  async function execute<T>(
    operation: (adapter: MaintenanceRequestAdapter) => Promise<MaintenanceResponse<T>>,
  ): Promise<MaintenanceResult<T>> {
    try {
      const adapter = await loadRequestAdapter()
      return unwrapMaintenanceResponse(await operation(adapter))
    } catch (error) {
      throw normalizeMaintenanceError(error)
    }
  }

  return {
    get<T>(path: string) {
      return execute((adapter) =>
        adapter.get<MaintenanceResponse<T>>(`${PREFIX}${path}`),
      )
    },
    post<T>(path: string, body: unknown, config?: unknown) {
      return execute((adapter) =>
        adapter.post<MaintenanceResponse<T>>(`${PREFIX}${path}`, body, config),
      )
    },
    put<T>(path: string, body: unknown) {
      return execute((adapter) =>
        adapter.put<MaintenanceResponse<T>>(`${PREFIX}${path}`, body),
      )
    },
    patch<T>(path: string, body: unknown) {
      return execute((adapter) =>
        adapter.patch<MaintenanceResponse<T>>(`${PREFIX}${path}`, body),
      )
    },
    delete<T>(path: string, body?: unknown) {
      return execute((adapter) =>
        adapter.del<MaintenanceResponse<T>>(`${PREFIX}${path}`, body),
      )
    },
  }
}

const defaultMaintenanceClient = createMaintenanceClient()

export function maintenanceGet<T>(path: string): Promise<MaintenanceResult<T>> {
  return defaultMaintenanceClient.get<T>(path)
}

export function maintenancePost<T>(
  path: string,
  body: unknown,
  config?: unknown,
): Promise<MaintenanceResult<T>> {
  return defaultMaintenanceClient.post<T>(path, body, config)
}

export function maintenancePut<T>(
  path: string,
  body: unknown,
): Promise<MaintenanceResult<T>> {
  return defaultMaintenanceClient.put<T>(path, body)
}

export function maintenancePatch<T>(
  path: string,
  body: unknown,
): Promise<MaintenanceResult<T>> {
  return defaultMaintenanceClient.patch<T>(path, body)
}

export function maintenanceDelete<T>(
  path: string,
  body?: unknown,
): Promise<MaintenanceResult<T>> {
  return defaultMaintenanceClient.delete<T>(path, body)
}
