export const actorAliases = [
  'tenant-a-viewer',
  'tenant-a-contributor',
  'tenant-a-admin',
  'tenant-b-admin',
] as const

export type ActorAlias = (typeof actorAliases)[number]

export const fixtureAliases = Object.freeze({
  tenantAEquipmentModel: 'tenant-a-equipment-model',
  tenantAPart: 'tenant-a-part',
  tenantASparePart: 'tenant-a-spare-part',
  tenantAWarehouse: 'tenant-a-warehouse',
  tenantAScenario: 'tenant-a-scenario',
  tenantBEquipmentModel: 'tenant-b-equipment-model',
  tenantBPart: 'tenant-b-part',
  tenantBSparePart: 'tenant-b-spare-part',
  tenantBWarehouse: 'tenant-b-warehouse',
  tenantBScenario: 'tenant-b-scenario',
} as const)

export type FixtureAlias = (typeof fixtureAliases)[keyof typeof fixtureAliases]
