import type { MaintenancePermissions } from '@/stores/maintenance/permissions'

export type MasterDataResourceKey =
  | 'equipmentModels'
  | 'configurations'
  | 'parts'
  | 'spareParts'
  | 'reliabilityProfiles'
  | 'warehouses'
  | 'inventorySummaries'
  | 'suppliers'
  | 'supplierOffers'
  | 'failureModes'
  | 'maintenanceActivities'
  | 'substitutions'
  | 'kitRules'
  | 'lots'
  | 'serialItems'

export type MasterDataRecord = Record<string, unknown>
export type MasterDataAvailability = 'available' | 'planned'
export type MasterDataSortOrder = 'asc' | 'desc'
export type MasterDataFormatter =
  | 'text'
  | 'number'
  | 'boolean'
  | 'date'
  | 'datetime'
  | 'currency'
  | 'status'
  | 'json'
export type MasterDataControl = 'text' | 'number' | 'select' | 'date' | 'switch'
export type MasterDataActionKind = 'view' | 'edit' | 'deactivate'
export type MasterDataWriteCapability = 'editMasterData' | 'adjustInventory'

export interface MasterDataOption {
  label: string
  value: string | number | boolean
}

export interface MasterDataColumn<T extends MasterDataRecord = MasterDataRecord> {
  key: keyof T & string
  title: string
  titleKey: string
  width?: number
  sortable?: boolean
  formatter?: MasterDataFormatter
}

export interface MasterDataFormField<T extends MasterDataRecord = MasterDataRecord> {
  key: keyof T & string
  apiKey?: string
  label: string
  labelKey: string
  control: MasterDataControl
  required?: boolean
  options?: MasterDataOption[]
  placeholder?: string
  min?: number
  max?: number
  step?: number
  defaultValue?: unknown
  createOnly?: boolean
  multiline?: boolean
}

export interface MasterDataRowAction {
  key: string
  kind: MasterDataActionKind
  label: string
}

export interface MasterDataOperations {
  list: boolean
  create: boolean
  update: boolean
  deactivate: boolean
}

export interface MasterDataTransferDefinition {
  exportKey: string
  importable: boolean
}

export type MasterDataTransferAction = 'template' | 'export' | 'import'

export interface MasterDataDetailRoute {
  name:
    | 'maintenanceConfigurationDetail'
    | 'maintenanceSparePartDetail'
  param: 'configurationId' | 'sparePartId'
}

export interface MasterDataResourceDefinition<
  T extends MasterDataRecord = MasterDataRecord,
> {
  key: MasterDataResourceKey
  group: 'assets' | 'supply' | 'rules'
  title: string
  titleKey: string
  description: string
  endpoint: string
  rowKey: keyof T & string
  detailRoute?: MasterDataDetailRoute
  availability: MasterDataAvailability
  operations: MasterDataOperations
  transfer?: MasterDataTransferDefinition
  writeCapability: MasterDataWriteCapability
  columns: Array<MasterDataColumn<T>>
  form: Array<MasterDataFormField<T>>
  actions: (
    permissions: MaintenancePermissions,
    record?: MasterDataRecord,
  ) => MasterDataRowAction[]
}

type MasterDataRowActionFilter = (
  action: MasterDataRowAction,
  record: MasterDataRecord,
) => boolean

const ACTIVE_OPERATIONS: Readonly<MasterDataOperations> = {
  list: true,
  create: true,
  update: true,
  deactivate: true,
}

const PLANNED_OPERATIONS: Readonly<MasterDataOperations> = {
  list: false,
  create: false,
  update: false,
  deactivate: false,
}

function standardActions(
  operations: MasterDataOperations,
  availability: MasterDataAvailability,
  writeCapability: MasterDataWriteCapability,
  rowActionFilter?: MasterDataRowActionFilter,
): (
  permissions: MaintenancePermissions,
  record?: MasterDataRecord,
) => MasterDataRowAction[] {
  return (permissions, record) => {
    const actions: MasterDataRowAction[] = [
      { key: 'view', kind: 'view', label: '查看' },
    ]

    if (availability !== 'available' || !permissions[writeCapability]) {
      return actions
    }

    if (operations.update) {
      actions.push({ key: 'edit', kind: 'edit', label: '编辑' })
    }

    if (operations.deactivate) {
      actions.push({ key: 'deactivate', kind: 'deactivate', label: '停用' })
    }

    if (!record || !rowActionFilter) {
      return actions
    }

    return actions.filter(
      (action) => rowActionFilter(action, record),
    )
  }
}

function defineResource(
  definition: Omit<
    MasterDataResourceDefinition,
    'actions' | 'writeCapability'
  > & {
    writeCapability?: MasterDataWriteCapability
    rowActionFilter?: MasterDataRowActionFilter
  },
): MasterDataResourceDefinition {
  const {
    writeCapability: requestedWriteCapability,
    rowActionFilter,
    ...resource
  } = definition
  const writeCapability = requestedWriteCapability ?? 'editMasterData'

  return {
    ...resource,
    writeCapability,
    actions: standardActions(
      resource.operations,
      resource.availability,
      writeCapability,
      rowActionFilter,
    ),
  }
}

const activeOperations = (
  overrides: Partial<MasterDataOperations> = {},
): MasterDataOperations => ({
  ...ACTIVE_OPERATIONS,
  ...overrides,
})

const plannedResource = (
  definition: Omit<
    MasterDataResourceDefinition,
    'availability' | 'operations' | 'transfer' | 'actions' | 'writeCapability'
  >,
): MasterDataResourceDefinition => defineResource({
  ...definition,
  availability: 'planned',
  operations: { ...PLANNED_OPERATIONS },
})

export function visibleMasterDataTransferActions(
  resource: MasterDataResourceDefinition,
  permissions: MaintenancePermissions,
): MasterDataTransferAction[] {
  if (resource.availability !== 'available' || !resource.transfer) {
    return []
  }

  const actions: MasterDataTransferAction[] = ['template', 'export']
  if (resource.transfer.importable && permissions.editMasterData) {
    actions.push('import')
  }
  return actions
}

const criticalityOptions: MasterDataOption[] = [
  { label: '普通', value: false },
  { label: '关键', value: true },
]

export const MASTER_DATA_RESOURCES: Readonly<
  Record<MasterDataResourceKey, MasterDataResourceDefinition>
> = {
  equipmentModels: defineResource({
    key: 'equipmentModels',
    group: 'assets',
    title: '设备型号',
    titleKey: 'maintenance.masterData.equipmentModels',
    description: '维护设备型号、制造商、系列和设计寿命。',
    endpoint: '/v1/master-data/equipment-models',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'equipment-models', importable: true },
    columns: [
      { key: 'code', title: '编码', titleKey: 'code', sortable: true },
      { key: 'name', title: '名称', titleKey: 'name', sortable: true },
      { key: 'category', title: '类别', titleKey: 'category', sortable: true },
      { key: 'manufacturer', title: '制造商', titleKey: 'manufacturer' },
      { key: 'model_series', title: '系列', titleKey: 'modelSeries' },
      { key: 'service_life_years', title: '设计寿命（年）', titleKey: 'serviceLifeYears', formatter: 'number' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true, createOnly: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'category', label: '类别', labelKey: 'category', control: 'text' },
      { key: 'manufacturer', label: '制造商', labelKey: 'manufacturer', control: 'text' },
      { key: 'model_series', label: '系列', labelKey: 'modelSeries', control: 'text' },
      { key: 'service_life_years', label: '设计寿命（年）', labelKey: 'serviceLifeYears', control: 'number', min: 0, step: 0.1 },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  configurations: defineResource({
    key: 'configurations',
    group: 'assets',
    title: '配置版本',
    titleKey: 'maintenance.masterData.configurations',
    description: '维护设备配置版本及其生效状态。配置树将在后续专用页面中提供。',
    endpoint: '/v1/master-data/configuration-versions',
    rowKey: 'id',
    detailRoute: {
      name: 'maintenanceConfigurationDetail',
      param: 'configurationId',
    },
    availability: 'available',
    operations: activeOperations({ deactivate: false }),
    transfer: { exportKey: 'configuration-versions', importable: true },
    rowActionFilter: (action, record) => (
      action.kind !== 'edit'
      || record.status === 'DRAFT'
    ),
    columns: [
      { key: 'version_code', title: '版本编码', titleKey: 'versionCode', sortable: true },
      { key: 'version_name', title: '版本名称', titleKey: 'versionName', sortable: true },
      { key: 'equipment_model_id', title: '设备型号 ID', titleKey: 'equipmentModelId', formatter: 'number' },
      { key: 'status', title: '状态', titleKey: 'status', formatter: 'status' },
      { key: 'effective_date', title: '生效日期', titleKey: 'effectiveDate', formatter: 'date' },
      { key: 'is_default', title: '默认版本', titleKey: 'isDefault', formatter: 'boolean' },
    ],
    form: [
      { key: 'equipment_model_id', label: '设备型号 ID', labelKey: 'equipmentModelId', control: 'number', required: true, min: 1, createOnly: true },
      { key: 'version_code', label: '版本编码', labelKey: 'versionCode', control: 'text', required: true, createOnly: true },
      { key: 'version_name', label: '版本名称', labelKey: 'versionName', control: 'text', required: true },
      { key: 'effective_date', label: '生效日期', labelKey: 'effectiveDate', control: 'date' },
      { key: 'expiry_date', label: '失效日期', labelKey: 'expiryDate', control: 'date' },
      { key: 'is_default', label: '默认版本', labelKey: 'isDefault', control: 'switch', defaultValue: false },
      { key: 'source_reference', label: '来源参考', labelKey: 'sourceReference', control: 'text' },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  parts: defineResource({
    key: 'parts',
    group: 'assets',
    title: '零部件',
    titleKey: 'maintenance.masterData.parts',
    description: '维护设备零部件目录及技术规格。',
    endpoint: '/v1/master-data/parts',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'parts', importable: true },
    columns: [
      { key: 'code', title: '编码', titleKey: 'code', sortable: true },
      { key: 'name', title: '名称', titleKey: 'name', sortable: true },
      { key: 'part_type', title: '类型', titleKey: 'partType' },
      { key: 'specification', title: '规格', titleKey: 'specification' },
      { key: 'manufacturer', title: '制造商', titleKey: 'manufacturer' },
      { key: 'unit', title: '单位', titleKey: 'unit' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true, createOnly: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'part_type', label: '类型', labelKey: 'partType', control: 'text' },
      { key: 'specification', label: '规格', labelKey: 'specification', control: 'text' },
      { key: 'manufacturer', label: '制造商', labelKey: 'manufacturer', control: 'text' },
      { key: 'unit', label: '单位', labelKey: 'unit', control: 'text', required: true, defaultValue: '件' },
      { key: 'drawing_number', label: '图号', labelKey: 'drawingNumber', control: 'text' },
      { key: 'maintenance_level', label: '维修级别', labelKey: 'maintenanceLevel', control: 'text' },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  spareParts: defineResource({
    key: 'spareParts',
    group: 'assets',
    title: '备件',
    titleKey: 'maintenance.masterData.spareParts',
    description: '维护备件目录、关键属性和默认服务水平。',
    endpoint: '/v1/master-data/spare-parts',
    rowKey: 'id',
    detailRoute: {
      name: 'maintenanceSparePartDetail',
      param: 'sparePartId',
    },
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'spare-parts', importable: true },
    columns: [
      { key: 'code', title: '编码', titleKey: 'code', sortable: true },
      { key: 'name', title: '名称', titleKey: 'name', sortable: true },
      { key: 'category', title: '类别', titleKey: 'category', sortable: true },
      { key: 'specification', title: '规格', titleKey: 'specification' },
      { key: 'unit', title: '单位', titleKey: 'unit' },
      { key: 'is_critical', title: '关键件', titleKey: 'criticality', formatter: 'boolean' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true, createOnly: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'specification', label: '规格', labelKey: 'specification', control: 'text' },
      { key: 'category', label: '类别', labelKey: 'category', control: 'text' },
      { key: 'unit', label: '单位', labelKey: 'unit', control: 'text', required: true, defaultValue: '件' },
      { key: 'manufacturer', label: '制造商', labelKey: 'manufacturer', control: 'text' },
      { key: 'material_code', label: '物料编码', labelKey: 'materialCode', control: 'text' },
      { key: 'national_standard', label: '国家标准', labelKey: 'nationalStandard', control: 'text' },
      { key: 'shelf_life_months', label: '保质期（月）', labelKey: 'shelfLifeMonths', control: 'number', min: 0 },
      { key: 'is_serialized', label: '序列号管理', labelKey: 'isSerialized', control: 'switch', defaultValue: false },
      { key: 'is_repairable', label: '可修复', labelKey: 'isRepairable', control: 'switch', defaultValue: false },
      { key: 'criticality', apiKey: 'is_critical', label: '关键程度', labelKey: 'criticality', control: 'select', options: criticalityOptions, defaultValue: false },
      { key: 'default_service_level', label: '默认服务水平', labelKey: 'defaultServiceLevel', control: 'number', min: 0, max: 1, step: 0.01 },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  reliabilityProfiles: defineResource({
    key: 'reliabilityProfiles',
    group: 'rules',
    title: '可靠性档案',
    titleKey: 'maintenance.masterData.reliabilityProfiles',
    description: '维护备件可靠性模型、参数和数据来源。',
    endpoint: '/v1/master-data/reliability-profiles',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'reliability-profiles', importable: true },
    columns: [
      { key: 'profile_code', title: '档案编码', titleKey: 'profileCode', sortable: true },
      { key: 'spare_part_id', title: '备件 ID', titleKey: 'sparePartId', formatter: 'number' },
      { key: 'model_type', title: '模型类型', titleKey: 'modelType', formatter: 'status' },
      { key: 'failure_rate', title: '失效率', titleKey: 'failureRate', formatter: 'number' },
      { key: 'mtbf_hours', title: 'MTBF（小时）', titleKey: 'mtbfHours', formatter: 'number' },
      { key: 'data_source_type', title: '数据来源', titleKey: 'dataSourceType', formatter: 'status' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'profile_code', label: '档案编码', labelKey: 'profileCode', control: 'text', required: true, createOnly: true },
      { key: 'spare_part_id', label: '备件 ID', labelKey: 'sparePartId', control: 'number', required: true, min: 1, createOnly: true },
      { key: 'configuration_version_id', label: '配置版本 ID', labelKey: 'configurationVersionId', control: 'number', min: 1 },
      { key: 'model_type', label: '模型类型', labelKey: 'modelType', control: 'select', required: true, options: [
        { label: '指数分布', value: 'EXPONENTIAL' },
        { label: '威布尔分布', value: 'WEIBULL' },
        { label: '二项分布', value: 'BINOMIAL' },
        { label: '负二项分布', value: 'NEGATIVE_BINOMIAL' },
        { label: '经验分布', value: 'EMPIRICAL' },
      ] },
      { key: 'failure_rate', label: '失效率', labelKey: 'failureRate', control: 'number', min: 0, step: 0.000001 },
      { key: 'mtbf_hours', label: 'MTBF（小时）', labelKey: 'mtbfHours', control: 'number', min: 0, step: 0.01 },
      { key: 'weibull_shape', label: '威布尔形状参数', labelKey: 'weibullShape', control: 'number', min: 0, step: 0.01 },
      { key: 'weibull_scale', label: '威布尔尺度参数', labelKey: 'weibullScale', control: 'number', min: 0, step: 0.01 },
      { key: 'binomial_trials', label: '二项试验次数', labelKey: 'binomialTrials', control: 'number', min: 1 },
      { key: 'binomial_probability', label: '二项概率', labelKey: 'binomialProbability', control: 'number', min: 0, max: 1, step: 0.01 },
      { key: 'negative_binomial_r', label: '负二项 r', labelKey: 'negativeBinomialR', control: 'number', min: 0, step: 0.01 },
      { key: 'negative_binomial_p', label: '负二项 p', labelKey: 'negativeBinomialP', control: 'number', min: 0, max: 1, step: 0.01 },
      { key: 'empirical_mean', label: '经验均值', labelKey: 'empiricalMean', control: 'number', min: 0, step: 0.01 },
      { key: 'empirical_variance', label: '经验方差', labelKey: 'empiricalVariance', control: 'number', min: 0, step: 0.01 },
      { key: 'data_source_type', label: '数据来源', labelKey: 'dataSourceType', control: 'select', required: true, options: [
        { label: '人工确认', value: 'USER_CONFIRMED' },
        { label: '用户提供', value: 'USER_PROVIDED' },
        { label: '主数据', value: 'MASTER_DATA' },
        { label: '知识检索', value: 'KNOWLEDGE_RETRIEVED' },
        { label: '系统默认', value: 'SYSTEM_DEFAULT' },
        { label: '模型推断', value: 'LLM_INFERRED' },
      ] },
      { key: 'sample_size', label: '样本量', labelKey: 'sampleSize', control: 'number', min: 0 },
      { key: 'confidence_level', label: '置信水平', labelKey: 'confidenceLevel', control: 'number', min: 0, max: 1, step: 0.01 },
      { key: 'valid_from', label: '有效期开始', labelKey: 'validFrom', control: 'date' },
      { key: 'valid_to', label: '有效期结束', labelKey: 'validTo', control: 'date' },
      { key: 'notes', label: '备注', labelKey: 'notes', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  warehouses: defineResource({
    key: 'warehouses',
    group: 'supply',
    title: '仓库',
    titleKey: 'maintenance.masterData.warehouses',
    description: '维护仓库位置、责任人和运营状态。',
    endpoint: '/v1/master-data/warehouses',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'warehouses', importable: true },
    columns: [
      { key: 'code', title: '编码', titleKey: 'code', sortable: true },
      { key: 'name', title: '名称', titleKey: 'name', sortable: true },
      { key: 'warehouse_type', title: '类型', titleKey: 'warehouseType' },
      { key: 'location', title: '位置', titleKey: 'location' },
      { key: 'responsible_person', title: '负责人', titleKey: 'responsiblePerson' },
      { key: 'status', title: '运营状态', titleKey: 'status', formatter: 'status' },
      { key: 'is_active', title: '启用', titleKey: 'isActive', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true, createOnly: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'warehouse_type', label: '类型', labelKey: 'warehouseType', control: 'text' },
      { key: 'location', label: '位置', labelKey: 'location', control: 'text' },
      { key: 'organization', label: '所属组织', labelKey: 'organization', control: 'text' },
      { key: 'responsible_person', label: '负责人', labelKey: 'responsiblePerson', control: 'text' },
      { key: 'contact', label: '联系方式', labelKey: 'contact', control: 'text' },
      { key: 'status', label: '运营状态', labelKey: 'status', control: 'select', options: [
        { label: '正常', value: 'NORMAL' },
        { label: '冻结', value: 'FROZEN' },
        { label: '停用', value: 'CLOSED' },
      ], defaultValue: 'NORMAL' },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  inventorySummaries: defineResource({
    key: 'inventorySummaries',
    group: 'supply',
    title: '库存汇总',
    titleKey: 'maintenance.masterData.inventorySummaries',
    description: '按仓库和备件维护账面库存、安全库存与补货点。',
    endpoint: '/v1/master-data/inventories',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations({ deactivate: false }),
    transfer: { exportKey: 'inventories', importable: true },
    writeCapability: 'adjustInventory',
    columns: [
      { key: 'warehouse_id', title: '仓库 ID', titleKey: 'warehouseId', sortable: true, formatter: 'number' },
      { key: 'spare_part_id', title: '备件 ID', titleKey: 'sparePartId', sortable: true, formatter: 'number' },
      { key: 'on_hand_quantity', title: '现有量', titleKey: 'onHandQuantity', formatter: 'number' },
      { key: 'available_quantity', title: '可用量', titleKey: 'availableQuantity', formatter: 'number' },
      { key: 'reserved_quantity', title: '预留量', titleKey: 'reservedQuantity', formatter: 'number' },
      { key: 'safety_stock', title: '安全库存', titleKey: 'safetyStock', formatter: 'number' },
      { key: 'reorder_point', title: '补货点', titleKey: 'reorderPoint', formatter: 'number' },
    ],
    form: [
      { key: 'warehouse_id', label: '仓库 ID', labelKey: 'warehouseId', control: 'number', required: true, min: 1, createOnly: true },
      { key: 'spare_part_id', label: '备件 ID', labelKey: 'sparePartId', control: 'number', required: true, min: 1, createOnly: true },
      { key: 'on_hand_quantity', label: '现有量', labelKey: 'onHandQuantity', control: 'number', required: true, min: 0, step: 0.01 },
      { key: 'reserved_quantity', label: '预留量', labelKey: 'reservedQuantity', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'damaged_quantity', label: '损坏量', labelKey: 'damagedQuantity', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'quarantined_quantity', label: '隔离量', labelKey: 'quarantinedQuantity', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'in_transit_quantity', label: '在途量', labelKey: 'inTransitQuantity', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'safety_stock', label: '安全库存', labelKey: 'safetyStock', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'reorder_point', label: '补货点', labelKey: 'reorderPoint', control: 'number', min: 0, step: 0.01, defaultValue: 0 },
      { key: 'maximum_stock', label: '最大库存', labelKey: 'maximumStock', control: 'number', min: 0, step: 0.01 },
      { key: 'notes', label: '备注', labelKey: 'notes', control: 'text', multiline: true },
    ],
  }),
  suppliers: defineResource({
    key: 'suppliers',
    group: 'supply',
    title: '供应商',
    titleKey: 'maintenance.masterData.suppliers',
    description: '维护供应商资质、联系人和评级。',
    endpoint: '/v1/master-data/suppliers',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'suppliers', importable: true },
    columns: [
      { key: 'code', title: '编码', titleKey: 'code', sortable: true },
      { key: 'name', title: '名称', titleKey: 'name', sortable: true },
      { key: 'supplier_type', title: '类型', titleKey: 'supplierType' },
      { key: 'contact_person', title: '联系人', titleKey: 'contactPerson' },
      { key: 'rating', title: '评级', titleKey: 'rating', formatter: 'number' },
      { key: 'qualification_status', title: '资质状态', titleKey: 'qualificationStatus', formatter: 'status' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true, createOnly: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'supplier_type', label: '类型', labelKey: 'supplierType', control: 'text' },
      { key: 'contact_person', label: '联系人', labelKey: 'contactPerson', control: 'text' },
      { key: 'phone', label: '电话', labelKey: 'phone', control: 'text' },
      { key: 'email', label: '邮箱', labelKey: 'email', control: 'text' },
      { key: 'address', label: '地址', labelKey: 'address', control: 'text' },
      { key: 'credit_code', label: '信用代码', labelKey: 'creditCode', control: 'text' },
      { key: 'rating', label: '评级', labelKey: 'rating', control: 'number', min: 0, max: 100, step: 0.1 },
      { key: 'qualification_status', label: '资质状态', labelKey: 'qualificationStatus', control: 'text' },
      { key: 'description', label: '说明', labelKey: 'description', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  supplierOffers: defineResource({
    key: 'supplierOffers',
    group: 'supply',
    title: '供应商报价',
    titleKey: 'maintenance.masterData.supplierOffers',
    description: '维护备件报价、交期、最小订购量和有效期。',
    endpoint: '/v1/master-data/supplier-offers',
    rowKey: 'id',
    availability: 'available',
    operations: activeOperations(),
    transfer: { exportKey: 'supplier-offers', importable: true },
    columns: [
      { key: 'offer_code', title: '报价编码', titleKey: 'offerCode', sortable: true },
      { key: 'supplier_id', title: '供应商 ID', titleKey: 'supplierId', formatter: 'number' },
      { key: 'spare_part_id', title: '备件 ID', titleKey: 'sparePartId', formatter: 'number' },
      { key: 'unit_price', title: '单价', titleKey: 'unitPrice', formatter: 'currency' },
      { key: 'lead_time_days', title: '交期（天）', titleKey: 'leadTimeDays', formatter: 'number' },
      { key: 'minimum_order_quantity', title: '最小订购量', titleKey: 'minimumOrderQuantity', formatter: 'number' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'offer_code', label: '报价编码', labelKey: 'offerCode', control: 'text', required: true, createOnly: true },
      { key: 'supplier_id', label: '供应商 ID', labelKey: 'supplierId', control: 'number', required: true, min: 1 },
      { key: 'spare_part_id', label: '备件 ID', labelKey: 'sparePartId', control: 'number', required: true, min: 1 },
      { key: 'unit_price', label: '单价', labelKey: 'unitPrice', control: 'number', required: true, min: 0, step: 0.01 },
      { key: 'currency', label: '币种', labelKey: 'currency', control: 'text', required: true, defaultValue: 'CNY' },
      { key: 'tax_rate', label: '税率', labelKey: 'taxRate', control: 'number', min: 0, max: 1, step: 0.01 },
      { key: 'price_includes_tax', label: '含税', labelKey: 'priceIncludesTax', control: 'switch', defaultValue: true },
      { key: 'lead_time_days', label: '交期（天）', labelKey: 'leadTimeDays', control: 'number', required: true, min: 0 },
      { key: 'minimum_order_quantity', label: '最小订购量', labelKey: 'minimumOrderQuantity', control: 'number', min: 0, step: 0.01, defaultValue: 1 },
      { key: 'order_multiple', label: '订购倍数', labelKey: 'orderMultiple', control: 'number', min: 0, step: 0.01, defaultValue: 1 },
      { key: 'maximum_supply_quantity', label: '最大供应量', labelKey: 'maximumSupplyQuantity', control: 'number', min: 0, step: 0.01 },
      { key: 'warranty_months', label: '质保期（月）', labelKey: 'warrantyMonths', control: 'number', min: 0 },
      { key: 'quality_level', label: '质量等级', labelKey: 'qualityLevel', control: 'text' },
      { key: 'is_preferred', label: '首选供应商', labelKey: 'isPreferred', control: 'switch', defaultValue: false },
      { key: 'valid_from', label: '有效期开始', labelKey: 'validFrom', control: 'date' },
      { key: 'valid_to', label: '有效期结束', labelKey: 'validTo', control: 'date' },
      { key: 'notes', label: '备注', labelKey: 'notes', control: 'text', multiline: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  failureModes: plannedResource({
    key: 'failureModes',
    group: 'rules',
    title: '故障模式',
    titleKey: 'maintenance.masterData.failureModes',
    description: '后端主数据路由就绪后启用故障模式台账。',
    endpoint: '/v1/master-data/failure-modes',
    rowKey: 'id',
    columns: [
      { key: 'code', title: '编码', titleKey: 'code' },
      { key: 'name', title: '名称', titleKey: 'name' },
      { key: 'severity', title: '严重度', titleKey: 'severity', formatter: 'status' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'severity', label: '严重度', labelKey: 'severity', control: 'text' },
    ],
  }),
  maintenanceActivities: plannedResource({
    key: 'maintenanceActivities',
    group: 'rules',
    title: '维修活动',
    titleKey: 'maintenance.masterData.maintenanceActivities',
    description: '后端主数据路由就绪后启用维修活动定义。',
    endpoint: '/v1/master-data/maintenance-activities',
    rowKey: 'id',
    columns: [
      { key: 'code', title: '编码', titleKey: 'code' },
      { key: 'name', title: '名称', titleKey: 'name' },
      { key: 'maintenance_level', title: '维修级别', titleKey: 'maintenanceLevel' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'maintenance_level', label: '维修级别', labelKey: 'maintenanceLevel', control: 'text' },
    ],
  }),
  substitutions: plannedResource({
    key: 'substitutions',
    group: 'rules',
    title: '替代关系',
    titleKey: 'maintenance.masterData.substitutions',
    description: '后端主数据路由就绪后启用备件替代关系。',
    endpoint: '/v1/master-data/substitutions',
    rowKey: 'id',
    columns: [
      { key: 'primary_spare_part_id', title: '主备件 ID', titleKey: 'primarySparePartId' },
      { key: 'substitute_spare_part_id', title: '替代备件 ID', titleKey: 'substituteSparePartId' },
      { key: 'priority', title: '优先级', titleKey: 'priority', formatter: 'number' },
    ],
    form: [
      { key: 'primary_spare_part_id', label: '主备件 ID', labelKey: 'primarySparePartId', control: 'number', required: true },
      { key: 'substitute_spare_part_id', label: '替代备件 ID', labelKey: 'substituteSparePartId', control: 'number', required: true },
      { key: 'priority', label: '优先级', labelKey: 'priority', control: 'number', min: 0 },
    ],
  }),
  kitRules: plannedResource({
    key: 'kitRules',
    group: 'rules',
    title: '套件规则',
    titleKey: 'maintenance.masterData.kitRules',
    description: '后端主数据路由就绪后启用套件规则。',
    endpoint: '/v1/master-data/kit-rules',
    rowKey: 'id',
    columns: [
      { key: 'code', title: '编码', titleKey: 'code' },
      { key: 'name', title: '名称', titleKey: 'name' },
      { key: 'is_active', title: '状态', titleKey: 'status', formatter: 'boolean' },
    ],
    form: [
      { key: 'code', label: '编码', labelKey: 'code', control: 'text', required: true },
      { key: 'name', label: '名称', labelKey: 'name', control: 'text', required: true },
      { key: 'is_active', label: '启用', labelKey: 'isActive', control: 'switch', defaultValue: true },
    ],
  }),
  lots: plannedResource({
    key: 'lots',
    group: 'supply',
    title: '批次',
    titleKey: 'maintenance.masterData.lots',
    description: '后端主数据路由就绪后启用批次追溯。',
    endpoint: '/v1/master-data/lots',
    rowKey: 'id',
    columns: [
      { key: 'lot_number', title: '批次号', titleKey: 'lotNumber' },
      { key: 'spare_part_id', title: '备件 ID', titleKey: 'sparePartId' },
      { key: 'quantity', title: '数量', titleKey: 'quantity', formatter: 'number' },
      { key: 'expiry_date', title: '失效日期', titleKey: 'expiryDate', formatter: 'date' },
    ],
    form: [
      { key: 'lot_number', label: '批次号', labelKey: 'lotNumber', control: 'text', required: true },
      { key: 'spare_part_id', label: '备件 ID', labelKey: 'sparePartId', control: 'number', required: true },
      { key: 'quantity', label: '数量', labelKey: 'quantity', control: 'number', min: 0 },
      { key: 'expiry_date', label: '失效日期', labelKey: 'expiryDate', control: 'date' },
    ],
  }),
  serialItems: plannedResource({
    key: 'serialItems',
    group: 'supply',
    title: '序列件',
    titleKey: 'maintenance.masterData.serialItems',
    description: '后端主数据路由就绪后启用序列件追溯。',
    endpoint: '/v1/master-data/serial-items',
    rowKey: 'id',
    columns: [
      { key: 'serial_number', title: '序列号', titleKey: 'serialNumber' },
      { key: 'spare_part_id', title: '备件 ID', titleKey: 'sparePartId' },
      { key: 'warehouse_id', title: '仓库 ID', titleKey: 'warehouseId' },
      { key: 'status', title: '状态', titleKey: 'status', formatter: 'status' },
    ],
    form: [
      { key: 'serial_number', label: '序列号', labelKey: 'serialNumber', control: 'text', required: true },
      { key: 'spare_part_id', label: '备件 ID', labelKey: 'sparePartId', control: 'number', required: true },
      { key: 'warehouse_id', label: '仓库 ID', labelKey: 'warehouseId', control: 'number', required: true },
      { key: 'status', label: '状态', labelKey: 'status', control: 'text' },
    ],
  }),
}

export const MASTER_DATA_RESOURCE_KEYS = Object.freeze(
  Object.keys(MASTER_DATA_RESOURCES) as MasterDataResourceKey[],
)

export const MASTER_DATA_RESOURCE_LIST = Object.freeze(
  MASTER_DATA_RESOURCE_KEYS.map((key) => MASTER_DATA_RESOURCES[key]),
)

export const AVAILABLE_MASTER_DATA_RESOURCES = Object.freeze(
  MASTER_DATA_RESOURCE_LIST.filter(
    (resource) => resource.availability === 'available',
  ),
)

export function isMasterDataResourceKey(
  value: unknown,
): value is MasterDataResourceKey {
  return (
    typeof value === 'string'
    && Object.prototype.hasOwnProperty.call(
      MASTER_DATA_RESOURCES,
      value,
    )
  )
}

export function getMasterDataResource(
  key: string,
): MasterDataResourceDefinition | undefined {
  return MASTER_DATA_RESOURCES[key as MasterDataResourceKey]
}

export function serializeMasterDataForm(
  resource: MasterDataResourceDefinition,
  values: MasterDataRecord,
  mode: 'create' | 'edit',
): MasterDataRecord {
  const payload: MasterDataRecord = {}

  resource.form.forEach((field) => {
    if (mode === 'edit' && field.createOnly) {
      return
    }

    const value = values[field.key]
    if (value === undefined || value === '') {
      return
    }

    payload[field.apiKey ?? field.key] = value
  })

  return payload
}
