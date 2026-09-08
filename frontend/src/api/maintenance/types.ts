export interface ApiMeta {
  request_id: string
  tenant_id: string
  version?: number
}

export interface MaintenanceResponse<T> {
  success: true
  data: T
  message: string
  meta: ApiMeta
}

export interface PageData<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface MaintenanceResult<T> {
  data: T
  meta: ApiMeta
}

export interface MaintenanceClientError {
  status?: number
  code: string
  message: string
  details?: unknown
  request_id?: string
  retryable: boolean
}
