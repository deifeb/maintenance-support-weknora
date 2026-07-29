export type SparePartTabKey =
  | 'overview'
  | 'applicability'
  | 'inventory'
  | 'lotsSerials'
  | 'substitutions'
  | 'kitRules'
  | 'reliability'
  | 'supply'
  | 'evidence'
  | 'audit'

export interface SparePartTabDefinition {
  key: SparePartTabKey
  label: string
  availability: 'available' | 'unavailable'
}

export const SPARE_PART_TABS: readonly SparePartTabDefinition[] = [
  { key: 'overview', label: '概览', availability: 'available' },
  { key: 'applicability', label: '适用性', availability: 'unavailable' },
  { key: 'inventory', label: '库存', availability: 'available' },
  { key: 'lotsSerials', label: '批次/序列号', availability: 'unavailable' },
  { key: 'substitutions', label: '替代关系', availability: 'unavailable' },
  { key: 'kitRules', label: '套件规则', availability: 'unavailable' },
  { key: 'reliability', label: '可靠性', availability: 'available' },
  { key: 'supply', label: '供应', availability: 'available' },
  { key: 'evidence', label: '证据', availability: 'unavailable' },
  { key: 'audit', label: '审计', availability: 'unavailable' },
] as const

export type NumericValue = number | string | null

export interface InventorySummary {
  onHand: number
  available: number
  reserved: number
  damaged: number
  quarantined: number
  inTransit: number
}

export interface InventoryQuantityRecord {
  on_hand_quantity?: NumericValue
  available_quantity?: NumericValue
  reserved_quantity?: NumericValue
  damaged_quantity?: NumericValue
  quarantined_quantity?: NumericValue
  in_transit_quantity?: NumericValue
}

export interface ReliabilityParameterSource {
  failure_rate?: unknown
  mtbf_hours?: unknown
}

export interface ReliabilityParameterEntry {
  key: 'failure_rate' | 'mtbf_hours'
  label: string
  value: unknown
}

export function numeric(
  value: NumericValue | undefined,
): number {
  if (value === null || value === undefined) {
    return 0
  }

  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function summarizeInventory(
  rows: readonly InventoryQuantityRecord[],
): InventorySummary {
  return rows.reduce<InventorySummary>(
    (summary, row) => ({
      onHand: summary.onHand + numeric(row.on_hand_quantity),
      available:
        summary.available + numeric(row.available_quantity),
      reserved:
        summary.reserved + numeric(row.reserved_quantity),
      damaged:
        summary.damaged + numeric(row.damaged_quantity),
      quarantined:
        summary.quarantined + numeric(row.quarantined_quantity),
      inTransit:
        summary.inTransit + numeric(row.in_transit_quantity),
    }),
    {
      onHand: 0,
      available: 0,
      reserved: 0,
      damaged: 0,
      quarantined: 0,
      inTransit: 0,
    },
  )
}

function populated(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

export function reliabilityParameterEntries(
  row: ReliabilityParameterSource,
): ReliabilityParameterEntry[] {
  const candidates: ReliabilityParameterEntry[] = [
    {
      key: 'failure_rate',
      label: '故障率',
      value: row.failure_rate,
    },
    {
      key: 'mtbf_hours',
      label: '平均故障间隔（小时）',
      value: row.mtbf_hours,
    },
  ]

  return candidates.filter((entry) => populated(entry.value))
}
