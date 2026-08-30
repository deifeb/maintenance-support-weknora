import type { MaintenanceCardType } from '@/utils/maintenanceCards'

export type MaintenanceCardComponentLoader = () => Promise<unknown>

export const MAINTENANCE_CARD_COMPONENT_LOADERS = {
  SCENARIO_DRAFT: () => import('./ScenarioDraftCard.vue'),
  CALCULATION: () => import('./CalculationCard.vue'),
  MODEL_COMPARISON: () => import('./ModelComparisonCard.vue'),
  INVENTORY_GAP: () => import('./InventoryGapCard.vue'),
  REVIEW_FINDING: () => import('./ReviewFindingCard.vue'),
  REPORT: () => import('./ReportCard.vue'),
} satisfies Record<MaintenanceCardType, MaintenanceCardComponentLoader>

export const getMaintenanceCardComponentLoader = (
  type: unknown,
): MaintenanceCardComponentLoader | undefined => {
  if (typeof type !== 'string') return undefined

  return Object.hasOwn(MAINTENANCE_CARD_COMPONENT_LOADERS, type)
    ? MAINTENANCE_CARD_COMPONENT_LOADERS[
        type as MaintenanceCardType
      ]
    : undefined
}
