export const MAINTENANCE_CARD_REGISTRY = {
  SCENARIO_DRAFT: {
    objectType: 'AI_SESSION_SNAPSHOT',
  },
  CALCULATION: {
    objectType: 'CALCULATION_GROUP',
  },
  MODEL_COMPARISON: {
    objectType: 'CALCULATION_GROUP',
  },
  INVENTORY_GAP: {
    objectType: 'ALLOCATION_PLAN',
  },
  REVIEW_FINDING: {
    objectType: 'DEMAND_REVIEW_FINDING',
  },
  REPORT: {
    objectType: 'AI_REPORT_JOB',
  },
} as const

export type MaintenanceCardType = keyof typeof MAINTENANCE_CARD_REGISTRY

export interface MaintenanceCardTarget {
  object_type: string
  object_id: number | string
  observed_version: number | string | null
  navigation_path: string
}

export interface MaintenanceCard {
  schema_version: '1.0'
  type: MaintenanceCardType
  title: string
  summary: string
  status: string
  target: MaintenanceCardTarget
  observed_at: string
  payload: Record<string, unknown>
}

const MAINTENANCE_PATH_PREFIX = '/platform/maintenance/'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isNonBlankString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0

const isCardObjectID = (value: unknown): value is number | string =>
  (typeof value === 'number' && Number.isInteger(value) && value > 0)
  || isNonBlankString(value)

const isObservedVersion = (
  value: unknown,
): value is number | string | null =>
  value === null
  || (typeof value === 'number' && Number.isInteger(value) && value >= 0)
  || isNonBlankString(value)

export const isSafeMaintenanceNavigationPath = (
  path: unknown,
): path is string => {
  if (typeof path !== 'string' || path.length === 0) return false
  if (path !== path.trim()) return false
  if (!path.startsWith(MAINTENANCE_PATH_PREFIX)) return false
  if (path.includes('\\') || path.includes('#')) return false

  let decoded: string
  try {
    decoded = decodeURIComponent(path)
  } catch {
    return false
  }

  if (!decoded.startsWith(MAINTENANCE_PATH_PREFIX)) return false
  if (decoded.includes('\\')) return false

  const segments = decoded.split('/')
  if (segments.some((segment) => segment === '.' || segment === '..')) {
    return false
  }

  return true
}

const isMaintenanceCardType = (
  value: unknown,
): value is MaintenanceCardType =>
  typeof value === 'string'
  && Object.hasOwn(MAINTENANCE_CARD_REGISTRY, value)

const isValidMaintenanceCard = (value: unknown): value is MaintenanceCard => {
  if (!isRecord(value)) return false
  if (value.schema_version !== '1.0') return false
  if (!isMaintenanceCardType(value.type)) return false
  if (!isNonBlankString(value.title)) return false
  if (typeof value.summary !== 'string') return false
  if (typeof value.status !== 'string') return false
  if (typeof value.observed_at !== 'string') return false
  if (!isRecord(value.payload)) return false
  if (!isRecord(value.target)) return false

  const registryEntry = MAINTENANCE_CARD_REGISTRY[value.type]
  if (value.target.object_type !== registryEntry.objectType) return false
  if (!isCardObjectID(value.target.object_id)) return false
  if (!isObservedVersion(value.target.observed_version)) return false
  if (!isSafeMaintenanceNavigationPath(value.target.navigation_path)) {
    return false
  }

  return true
}

export const normalizeMaintenanceCards = (
  value: unknown,
): MaintenanceCard[] => {
  if (!Array.isArray(value)) return []

  return value.filter(isValidMaintenanceCard)
}
export const applyMaintenanceCardSnapshot = (
  message: Record<string, unknown>,
  snapshot: unknown,
): MaintenanceCard[] => {
  const current = normalizeMaintenanceCards(message.maintenance_cards)

  if (!Array.isArray(snapshot)) {
    message.maintenance_cards = current
    return current
  }

  const next = normalizeMaintenanceCards(snapshot)
  message.maintenance_cards = next
  return next
}
