<template>
  <section
    class="spare-part-overview"
    aria-label="备件概览"
  >
    <dl class="spare-part-overview__grid">
      <div>
        <dt>备件编码</dt>
        <dd>{{ record.code }}</dd>
      </div>
      <div>
        <dt>备件名称</dt>
        <dd>{{ record.name }}</dd>
      </div>
      <div>
        <dt>规格型号</dt>
        <dd>{{ display(record.specification) }}</dd>
      </div>
      <div>
        <dt>分类</dt>
        <dd>{{ display(record.category) }}</dd>
      </div>
      <div>
        <dt>计量单位</dt>
        <dd>{{ record.unit }}</dd>
      </div>
      <div>
        <dt>制造商</dt>
        <dd>{{ display(record.manufacturer) }}</dd>
      </div>
      <div>
        <dt>物料编码</dt>
        <dd>{{ display(record.material_code) }}</dd>
      </div>
      <div>
        <dt>国家标准</dt>
        <dd>{{ display(record.national_standard) }}</dd>
      </div>
      <div>
        <dt>保质期（月）</dt>
        <dd>{{ display(record.shelf_life_months) }}</dd>
      </div>
      <div>
        <dt>序列化管理</dt>
        <dd>{{ yesNo(record.is_serialized) }}</dd>
      </div>
      <div>
        <dt>可维修</dt>
        <dd>{{ yesNo(record.is_repairable) }}</dd>
      </div>
      <div>
        <dt>关键备件</dt>
        <dd>{{ yesNo(record.is_critical) }}</dd>
      </div>
      <div>
        <dt>默认服务水平</dt>
        <dd>{{ display(record.default_service_level) }}</dd>
      </div>
      <div>
        <dt>启用状态</dt>
        <dd>{{ record.is_active ? '启用' : '停用' }}</dd>
      </div>
      <div>
        <dt>更新时间</dt>
        <dd>{{ display(record.updated_at) }}</dd>
      </div>
      <div class="spare-part-overview__wide">
        <dt>说明</dt>
        <dd>{{ display(record.description) }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import type {
  SparePartDetailRecord,
} from '@/api/maintenance/master-data-details'

defineProps<{
  record: SparePartDetailRecord
}>()

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '未提供'
  }

  return String(value)
}

function yesNo(value: boolean): string {
  return value ? '是' : '否'
}
</script>

<style scoped>
.spare-part-overview__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.spare-part-overview__grid > div {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.spare-part-overview__grid dt {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.spare-part-overview__grid dd {
  margin: 7px 0 0;
  overflow-wrap: anywhere;
  color: var(--td-text-color-primary);
}

.spare-part-overview__wide {
  grid-column: 1 / -1;
}

@media (max-width: 900px) {
  .spare-part-overview__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .spare-part-overview__grid {
    grid-template-columns: 1fr;
  }
}
</style>
