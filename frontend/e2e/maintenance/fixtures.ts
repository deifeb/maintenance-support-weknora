import { dirname, join } from 'node:path'

export const actorAliases = [
  'tenant-a-viewer',
  'tenant-a-contributor',
  'tenant-a-admin',
  'tenant-b-admin',
] as const

export type ActorAlias = (typeof actorAliases)[number]

export function storageStatePath(alias: ActorAlias): string {
  const manifestPath = process.env.E2E_ACTOR_MANIFEST_PATH
  const stateDir = manifestPath
    ? join(dirname(manifestPath), 'auth-states')
    : join('test-results', 'auth-states')
  return join(stateDir, `${alias}.json`)
}

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
