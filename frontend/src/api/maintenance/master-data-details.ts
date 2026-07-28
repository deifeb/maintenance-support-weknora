import {
  maintenanceGet,
  maintenancePost,
  maintenancePut,
} from './client'
import type { MaintenanceResult } from './types'

export type DecimalValue = number | string
export type ConfigurationStatus = 'DRAFT' | 'PUBLISHED' | 'RETIRED'
export type CriticalityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface ConfigurationVersion {
  id: number
  equipment_model_id: number
  version_code: string
  version_name: string
  status: ConfigurationStatus
  effective_date: string | null
  expiry_date: string | null
  is_default: boolean
  is_active: boolean
  source_reference: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export interface ConfigurationTreeNodeRecord {
  id: number
  item_code: string
  parent_item_id: number | null
  part_id: number
  spare_part_id: number | null
  install_quantity: DecimalValue
  position_code: string | null
  position_name: string | null
  criticality_level: CriticalityLevel
  replacement_ratio: DecimalValue
  maintenance_level: string | null
  is_mandatory: boolean
  sort_order: number
  notes: string | null
}

export interface ConfigurationTreeNode
  extends ConfigurationTreeNodeRecord {
  children: ConfigurationTreeNode[]
}

export interface ConfigurationTreeData {
  version: ConfigurationVersion
  items: ConfigurationTreeNode[]
}

export interface ConfigurationClonePayload {
  version_code: string
  version_name: string
  effective_date: string | null
  is_default: boolean
}

export interface ConfigurationVersionUpdatePayload {
  version_name?: string
  effective_date?: string | null
  expiry_date?: string | null
  is_default?: boolean
  is_active?: boolean
  source_reference?: string | null
  description?: string | null
}

export interface ConfigurationItemCreatePayload {
  configuration_version_id: number
  item_code: string
  parent_item_id: number | null
  part_id: number
  spare_part_id: number | null
  install_quantity: DecimalValue
  position_code: string | null
  position_name: string | null
  criticality_level: CriticalityLevel
  replacement_ratio: DecimalValue
  maintenance_level: string | null
  is_mandatory: boolean
  sort_order: number
  notes: string | null
}

export type ConfigurationItemUpdatePayload =
  Partial<
    Omit<
      ConfigurationItemCreatePayload,
      'configuration_version_id' | 'item_code'
    >
  >

export interface SparePartDetailRecord {
  id: number
  code: string
  name: string
  specification: string | null
  category: string | null
  unit: string
  manufacturer: string | null
  material_code: string | null
  national_standard: string | null
  shelf_life_months: number | null
  is_serialized: boolean
  is_repairable: boolean
  is_critical: boolean
  default_service_level: DecimalValue | null
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface InventoryDetailRecord {
  id: number
  warehouse_id: number
  spare_part_id: number
  on_hand_quantity: DecimalValue
  reserved_quantity: DecimalValue
  damaged_quantity: DecimalValue
  quarantined_quantity: DecimalValue
  in_transit_quantity: DecimalValue
  safety_stock: DecimalValue
  reorder_point: DecimalValue
  maximum_stock: DecimalValue | null
  available_quantity: DecimalValue
  last_counted_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface ReliabilityDetailRecord {
  id: number
  profile_code: string
  spare_part_id: number
  configuration_version_id: number | null
  model_type: string
  failure_rate: DecimalValue | null
  mtbf_hours: DecimalValue | null
  data_source_type: string
  data_source_reference: string | null
  sample_size: number | null
  confidence_level: DecimalValue | null
  valid_from: string | null
  valid_to: string | null
  notes: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SupplierOfferDetailRecord {
  id: number
  offer_code: string
  supplier_id: number
  spare_part_id: number
  unit_price: DecimalValue
  currency: string
  tax_rate: DecimalValue | null
  price_includes_tax: boolean
  lead_time_days: number
  minimum_order_quantity: DecimalValue
  order_multiple: DecimalValue
  maximum_supply_quantity: DecimalValue | null
  warranty_months: number | null
  quality_level: string | null
  is_preferred: boolean
  valid_from: string | null
  valid_to: string | null
  notes: string | null
  is_active: boolean
}

export interface DetailApiClient {
  get<T>(path: string): Promise<MaintenanceResult<T>>
  post<T>(
    path: string,
    body: unknown,
  ): Promise<MaintenanceResult<T>>
  put<T>(
    path: string,
    body: unknown,
  ): Promise<MaintenanceResult<T>>
}

const defaultMasterDataDetailsClient: DetailApiClient = {
  get: maintenanceGet,
  post: maintenancePost,
  put: maintenancePut,
}

export function createMasterDataDetailsApi(
  client: DetailApiClient = defaultMasterDataDetailsClient,
) {
  return {
    getConfigurationTree(
      configurationId: number,
    ): Promise<MaintenanceResult<ConfigurationTreeData>> {
      return client.get<ConfigurationTreeData>(
        `/v1/master-data/configuration-versions/${configurationId}/tree`,
      )
    },

    updateConfigurationVersion(
      configurationId: number,
      body: ConfigurationVersionUpdatePayload,
    ): Promise<MaintenanceResult<ConfigurationVersion>> {
      return client.put<ConfigurationVersion>(
        `/v1/master-data/configuration-versions/${configurationId}`,
        body,
      )
    },

    cloneConfigurationVersion(
      configurationId: number,
      body: ConfigurationClonePayload,
    ): Promise<MaintenanceResult<ConfigurationVersion>> {
      return client.post<ConfigurationVersion>(
        `/v1/master-data/configuration-versions/${configurationId}/clone`,
        body,
      )
    },

    createConfigurationItem(
      body: ConfigurationItemCreatePayload,
    ): Promise<MaintenanceResult<ConfigurationTreeNodeRecord>> {
      return client.post<ConfigurationTreeNodeRecord>(
        '/v1/master-data/configuration-items',
        body,
      )
    },

    updateConfigurationItem(
      configurationItemId: number,
      body: ConfigurationItemUpdatePayload,
    ): Promise<MaintenanceResult<ConfigurationTreeNodeRecord>> {
      return client.put<ConfigurationTreeNodeRecord>(
        `/v1/master-data/configuration-items/${configurationItemId}`,
        body,
      )
    },
  }
}

export const masterDataDetailsApi = createMasterDataDetailsApi()
