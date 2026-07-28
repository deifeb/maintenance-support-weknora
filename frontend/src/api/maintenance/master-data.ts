import {
  buildQuery,
  maintenanceGet,
  maintenancePatch,
  maintenancePost,
  maintenancePut,
} from './client'
import type {
  MaintenanceResult,
  PageData,
} from './types'

export type MasterDataIdentifier = string | number

export interface MasterDataEndpoint {
  endpoint: string
}

export interface MasterDataListQuery {
  page: number
  page_size: number
  keyword?: string
  include_inactive: boolean
  sort_by: string
  sort_order: 'asc' | 'desc'
}

export interface MasterDataApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(path: string, body: unknown): Promise<MaintenanceResult<T>>
  put<T>(path: string, body: unknown): Promise<MaintenanceResult<T>>
  patch<T>(path: string, body: unknown): Promise<MaintenanceResult<T>>
}

const defaultMasterDataClient: MasterDataApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
  patch: maintenancePatch,
}

function itemPath(
  resource: MasterDataEndpoint,
  identifier: MasterDataIdentifier,
): string {
  return `${resource.endpoint}/${encodeURIComponent(String(identifier))}`
}

export function createMasterDataApi(
  client: MasterDataApiClient = defaultMasterDataClient,
) {
  return {
    list<T>(
      resource: MasterDataEndpoint,
      query: MasterDataListQuery,
    ): Promise<MaintenanceResult<PageData<T>>> {
      const queryString = buildQuery({ ...query })
      return client.get<PageData<T>>(`${resource.endpoint}?${queryString}`)
    },
    get<T>(
      resource: MasterDataEndpoint,
      identifier: MasterDataIdentifier,
    ): Promise<MaintenanceResult<T>> {
      return client.get<T>(itemPath(resource, identifier))
    },
    create<T>(
      resource: MasterDataEndpoint,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      return client.post<T>(resource.endpoint, body)
    },
    update<T>(
      resource: MasterDataEndpoint,
      identifier: MasterDataIdentifier,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      return client.put<T>(itemPath(resource, identifier), body)
    },
    setActive<T>(
      resource: MasterDataEndpoint,
      identifier: MasterDataIdentifier,
      isActive: boolean,
    ): Promise<MaintenanceResult<T>> {
      return client.patch<T>(
        `${itemPath(resource, identifier)}/active`,
        { is_active: isActive },
      )
    },
  }
}

export const masterDataApi = createMasterDataApi()
