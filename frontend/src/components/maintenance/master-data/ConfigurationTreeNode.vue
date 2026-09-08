<template>
  <li class="configuration-tree-node">
    <article
      class="configuration-tree-node__row"
      :style="{ marginInlineStart: `${level * 18}px` }"
    >
      <div class="configuration-tree-node__identity">
        <strong>{{ node.item_code }}</strong>
        <span>位置编码：{{ node.position_code || '—' }}</span>
        <span>位置名称：{{ node.position_name || '—' }}</span>
      </div>

      <dl class="configuration-tree-node__facts">
        <div>
          <dt>零件 ID</dt>
          <dd>{{ node.part_id }}</dd>
        </div>
        <div>
          <dt>备件 ID</dt>
          <dd>{{ node.spare_part_id ?? '—' }}</dd>
        </div>
        <div>
          <dt>装机数量</dt>
          <dd>{{ node.install_quantity }}</dd>
        </div>
        <div>
          <dt>关键度</dt>
          <dd>{{ node.criticality_level }}</dd>
        </div>
        <div>
          <dt>维修级别</dt>
          <dd>{{ node.maintenance_level || '—' }}</dd>
        </div>
        <div>
          <dt>必装</dt>
          <dd>{{ node.is_mandatory ? '是' : '否' }}</dd>
        </div>
        <div class="configuration-tree-node__fact-wide">
          <dt>依据/备注</dt>
          <dd>{{ node.notes || '—' }}</dd>
        </div>
      </dl>

      <div
        v-if="editable"
        class="configuration-tree-node__actions"
      >
        <button
          type="button"
          @click="$emit('create-child', node)"
        >
          新增子项
        </button>
        <button
          type="button"
          @click="$emit('edit-item', node)"
        >
          编辑
        </button>
      </div>
    </article>

    <ul
      v-if="node.children.length > 0"
      class="configuration-tree-node__children"
    >
      <ConfigurationTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :editable="editable"
        :level="level + 1"
        @create-child="$emit('create-child', $event)"
        @edit-item="$emit('edit-item', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import type { ConfigurationTreeNode } from '@/api/maintenance/master-data-details'

defineProps<{
  node: ConfigurationTreeNode
  editable: boolean
  level: number
}>()

defineEmits<{
  (event: 'create-child', node: ConfigurationTreeNode): void
  (event: 'edit-item', node: ConfigurationTreeNode): void
}>()
</script>

<style scoped>
.configuration-tree-node {
  display: grid;
  gap: 8px;
}

.configuration-tree-node__row {
  display: grid;
  grid-template-columns: minmax(150px, 0.8fr) minmax(320px, 2fr) auto;
  align-items: center;
  gap: 18px;
  padding: 14px 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.configuration-tree-node__identity {
  display: grid;
  gap: 4px;
}

.configuration-tree-node__identity span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.configuration-tree-node__facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.configuration-tree-node__facts div {
  min-width: 0;
}

.configuration-tree-node__fact-wide {
  grid-column: span 2;
}

.configuration-tree-node__facts dt {
  color: var(--td-text-color-placeholder);
  font-size: 11px;
}

.configuration-tree-node__facts dd {
  overflow: hidden;
  margin: 3px 0 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.configuration-tree-node__actions {
  display: flex;
  gap: 8px;
}

.configuration-tree-node__actions button {
  padding: 6px 10px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.configuration-tree-node__children {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 960px) {
  .configuration-tree-node__row {
    grid-template-columns: 1fr;
  }

  .configuration-tree-node__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
