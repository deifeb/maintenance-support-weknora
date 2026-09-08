<template>
  <section
    class="configuration-tree"
    aria-label="配置树"
  >
    <header class="configuration-tree__header">
      <div>
        <h2>配置项目树</h2>
        <p>按安装位置和排序号展示配置项目。</p>
      </div>
      <button
        v-if="editable"
        type="button"
        class="configuration-tree__button configuration-tree__button--primary"
        @click="$emit('create-root')"
      >
        新增根项目
      </button>
    </header>

    <div
      v-if="items.length === 0"
      class="configuration-tree__empty"
    >
      <p>当前配置版本尚无项目。</p>
      <button
        v-if="editable"
        type="button"
        class="configuration-tree__button"
        @click="$emit('create-root')"
      >
        创建第一个项目
      </button>
    </div>

    <ul
      v-else
      class="configuration-tree__list"
    >
      <ConfigurationTreeNode
        v-for="node in items"
        :key="node.id"
        :node="node"
        :editable="editable"
        :level="0"
        @create-child="$emit('create-child', $event)"
        @edit-item="$emit('edit-item', $event)"
      />
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { ConfigurationTreeNode as ConfigurationTreeNodeRecord } from '@/api/maintenance/master-data-details'
import ConfigurationTreeNode from './ConfigurationTreeNode.vue'

defineProps<{
  items: ConfigurationTreeNodeRecord[]
  editable: boolean
}>()

defineEmits<{
  (event: 'create-root'): void
  (event: 'create-child', node: ConfigurationTreeNodeRecord): void
  (event: 'edit-item', node: ConfigurationTreeNodeRecord): void
}>()
</script>

<style scoped>
.configuration-tree {
  display: grid;
  gap: 16px;
}

.configuration-tree__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.configuration-tree__header h2,
.configuration-tree__header p {
  margin: 0;
}

.configuration-tree__header p {
  margin-top: 6px;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.configuration-tree__list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.configuration-tree__empty {
  display: grid;
  justify-items: start;
  gap: 12px;
  padding: 28px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 8px;
  color: var(--td-text-color-secondary);
}

.configuration-tree__empty p {
  margin: 0;
}

.configuration-tree__button {
  padding: 8px 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.configuration-tree__button--primary {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

@media (max-width: 640px) {
  .configuration-tree__header {
    display: grid;
  }
}
</style>
