import type {
  ConfigurationTreeNode,
  ConfigurationTreeNodeRecord,
  ConfigurationVersion,
} from '../../../api/maintenance/master-data-details'
import type { MaintenancePermissions } from '../../../stores/maintenance/permission-matrix'

export type ConfigurationDetailMode =
  | 'editable'
  | 'clone-only'
  | 'readonly'

export interface ConfigurationDetailContext {
  routeConfigurationId: number | null
  loadedConfigurationId: number | null
}

export function configurationCloneCode(
  versionCode: string,
): string {
  return `${versionCode}-COPY`
}

function compareConfigurationNodes(
  left: Pick<ConfigurationTreeNodeRecord, 'sort_order' | 'item_code' | 'id'>,
  right: Pick<ConfigurationTreeNodeRecord, 'sort_order' | 'item_code' | 'id'>,
): number {
  if (left.sort_order !== right.sort_order) {
    return left.sort_order - right.sort_order
  }

  if (left.item_code < right.item_code) {
    return -1
  }
  if (left.item_code > right.item_code) {
    return 1
  }

  return left.id - right.id
}

export function sortConfigurationTree(
  items: readonly ConfigurationTreeNode[],
): ConfigurationTreeNode[] {
  return items
    .map((item) => ({
      ...item,
      children: sortConfigurationTree(item.children),
    }))
    .sort(compareConfigurationNodes)
}

export function buildConfigurationTree(
  items: readonly ConfigurationTreeNodeRecord[],
): ConfigurationTreeNode[] {
  const nodes = new Map<number, ConfigurationTreeNode>()

  items.forEach((item) => {
    nodes.set(item.id, {
      ...item,
      children: [],
    })
  })

  const roots: ConfigurationTreeNode[] = []

  nodes.forEach((node) => {
    const parent = node.parent_item_id === null
      ? undefined
      : nodes.get(node.parent_item_id)

    if (!parent || parent.id === node.id) {
      roots.push(node)
      return
    }

    parent.children.push(node)
  })

  return sortConfigurationTree(roots)
}

export function configurationDetailMode(
  version: Pick<ConfigurationVersion, 'status'>,
  permissions: Pick<MaintenancePermissions, 'editMasterData'>,
  context?: ConfigurationDetailContext,
): ConfigurationDetailMode {
  if (
    context
    && (
      context.routeConfigurationId === null
      || context.loadedConfigurationId !== context.routeConfigurationId
    )
  ) {
    return 'readonly'
  }

  if (!permissions.editMasterData) {
    return 'readonly'
  }

  if (version.status === 'DRAFT') {
    return 'editable'
  }

  if (version.status === 'PUBLISHED') {
    return 'clone-only'
  }

  return 'readonly'
}
