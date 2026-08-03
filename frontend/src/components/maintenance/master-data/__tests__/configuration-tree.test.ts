import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { permissionsForRole } from '../../../../stores/maintenance/permission-matrix.ts'
import {
  buildConfigurationTree,
  configurationDetailMode,
  sortConfigurationTree,
} from '../ConfigurationTree.ts'

test('configuration tree preserves parent-child sort order without mutating input', () => {
  const input = [
    {
      id: 2,
      item_code: 'CHILD-B',
      parent_item_id: 1,
      sort_order: 2,
    },
    {
      id: 1,
      item_code: 'ROOT',
      parent_item_id: null,
      sort_order: 1,
    },
    {
      id: 3,
      item_code: 'CHILD-A',
      parent_item_id: 1,
      sort_order: 1,
    },
  ]

  const tree = buildConfigurationTree(input as never)

  assert.equal(tree[0]?.id, 1)
  assert.deepEqual(
    tree[0]?.children.map((node) => node.id),
    [3, 2],
  )
  assert.deepEqual(
    input.map((node) => node.id),
    [2, 1, 3],
  )
  assert.equal('children' in input[0], false)
})

test('configuration tree keeps orphan and self-parent items visible as roots', () => {
  const tree = buildConfigurationTree([
    {
      id: 7,
      item_code: 'ORPHAN',
      parent_item_id: 999,
      sort_order: 0,
    },
    {
      id: 8,
      item_code: 'SELF',
      parent_item_id: 8,
      sort_order: 1,
    },
  ] as never)

  assert.deepEqual(
    tree.map((node) => node.id),
    [7, 8],
  )
})

test('configuration tree uses item code and id as deterministic tie breakers', () => {
  const tree = buildConfigurationTree([
    {
      id: 12,
      item_code: 'B',
      parent_item_id: null,
      sort_order: 0,
    },
    {
      id: 11,
      item_code: 'A',
      parent_item_id: null,
      sort_order: 0,
    },
    {
      id: 10,
      item_code: 'A',
      parent_item_id: null,
      sort_order: 0,
    },
  ] as never)

  assert.deepEqual(
    tree.map((node) => node.id),
    [10, 11, 12],
  )
})

test('nested API trees are cloned and sorted recursively', () => {
  const input = [
    {
      id: 1,
      item_code: 'ROOT',
      parent_item_id: null,
      sort_order: 0,
      children: [
        {
          id: 3,
          item_code: 'B',
          parent_item_id: 1,
          sort_order: 2,
          children: [],
        },
        {
          id: 2,
          item_code: 'A',
          parent_item_id: 1,
          sort_order: 1,
          children: [],
        },
      ],
    },
  ]

  const sorted = sortConfigurationTree(input as never)

  assert.deepEqual(
    sorted[0]?.children.map((node) => node.id),
    [2, 3],
  )
  assert.deepEqual(
    input[0]?.children.map((node) => node.id),
    [3, 2],
  )
  assert.notEqual(sorted, input)
  assert.notEqual(sorted[0], input[0])
})

test('configuration modes enforce draft-only editing', () => {
  const contributor = permissionsForRole('contributor')
  const viewer = permissionsForRole('viewer')

  assert.equal(
    configurationDetailMode(
      { status: 'DRAFT' },
      contributor,
    ),
    'editable',
  )
  assert.equal(
    configurationDetailMode(
      { status: 'PUBLISHED' },
      contributor,
    ),
    'clone-only',
  )
  assert.equal(
    configurationDetailMode(
      { status: 'PUBLISHED' },
      viewer,
    ),
    'readonly',
  )
  assert.equal(
    configurationDetailMode(
      { status: 'RETIRED' },
      contributor,
    ),
    'readonly',
  )
})

test('configuration detail becomes readonly when loaded data belongs to another route', () => {
  const contributor = permissionsForRole('contributor')

  assert.equal(
    configurationDetailMode(
      { status: 'DRAFT' },
      contributor,
      {
        routeConfigurationId: 22,
        loadedConfigurationId: 11,
      },
    ),
    'readonly',
  )
  assert.equal(
    configurationDetailMode(
      { status: 'DRAFT' },
      contributor,
      {
        routeConfigurationId: 11,
        loadedConfigurationId: 11,
      },
    ),
    'editable',
  )
})

test('configuration detail closes editors and guards writes across route changes', () => {
  const source = readFileSync(
    new URL(
      '../../../../views/maintenance/master-data/ConfigurationDetail.vue',
      import.meta.url,
    ),
    'utf8',
  )

  assert.match(
    source,
    /const loadedConfigurationId = ref<number \| null>\(null\)/,
  )
  assert.match(source, /function resetEditorsForRouteChange\(\): void/)
  assert.match(
    source,
    /watch\([\s\S]*resetEditorsForRouteChange\(\)[\s\S]*void load\(\)/,
  )
  assert.match(
    source,
    /loadedConfigurationId\.value !== id/,
  )
  assert.match(
    source,
    /mode\.value !== expectedMode/,
  )
  assert.match(
    source,
    /loadedConfigurationId\.value !== configurationId\.value/,
  )
})

test('configuration tree node renders every required maintenance field separately', () => {
  const source = readFileSync(
    new URL('../ConfigurationTreeNode.vue', import.meta.url),
    'utf8',
  )

  for (const fragment of [
    'node.part_id',
    'node.spare_part_id',
    'node.install_quantity',
    'node.criticality_level',
    'node.maintenance_level',
    'node.is_mandatory',
    'node.notes',
  ]) {
    assert.ok(source.includes(fragment), `missing ${fragment}`)
  }

  assert.doesNotMatch(
    source,
    /node\.spare_part_id\s*\?\?\s*node\.part_id/,
  )
})

test('configuration clone code uses the approved COPY suffix', async () => {
  const module = await import('../ConfigurationTree.ts')
  assert.equal(
    module.configurationCloneCode('CFG-001'),
    'CFG-001-COPY',
  )

  const source = readFileSync(
    new URL('../ConfigurationVersionEditor.vue', import.meta.url),
    'utf8',
  )

  assert.match(
    source,
    /configurationCloneCode\(props\.version\.version_code\)/,
  )
  assert.doesNotMatch(source, /version_code\}-DRAFT/)
})
