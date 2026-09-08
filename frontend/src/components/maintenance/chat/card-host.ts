import {
  normalizeMaintenanceCards,
  type MaintenanceCard,
} from '../../../utils/maintenanceCards'

import {
  getMaintenanceCardComponentLoader,
  type MaintenanceCardComponentLoader,
} from './card-registry'

export interface MaintenanceCardRenderItem {
  key: string
  card: MaintenanceCard
  loader: MaintenanceCardComponentLoader
}

const renderKey = (card: MaintenanceCard): string => [
  card.type,
  card.target.object_type,
  String(card.target.object_id),
  card.target.observed_version === null
    ? ''
    : String(card.target.observed_version),
].join(':')

export const buildMaintenanceCardRenderItems = (
  value: unknown,
): MaintenanceCardRenderItem[] => {
  const cards = normalizeMaintenanceCards(value)

  return cards.flatMap((card) => {
    const loader = getMaintenanceCardComponentLoader(card.type)
    if (!loader) return []

    return [{
      key: renderKey(card),
      card,
      loader,
    }]
  })
}
