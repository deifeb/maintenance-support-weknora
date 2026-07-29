<template>
  <section
    class="spare-part-reliability"
    aria-label="备件可靠性"
  >
    <div
      v-if="page.items.length === 0"
      class="spare-part-reliability__empty"
    >
      当前备件没有可靠性模型记录。
    </div>

    <article
      v-for="record in page.items"
      v-else
      :key="record.id"
      class="spare-part-reliability__record"
    >
      <header>
        <div>
          <span>{{ record.profile_code }}</span>
          <h3>{{ record.model_type }}</h3>
        </div>
        <strong>{{ record.is_active ? '启用' : '停用' }}</strong>
      </header>

      <dl>
        <div>
          <dt>数据来源类型</dt>
          <dd>{{ display(record.data_source_type) }}</dd>
        </div>
        <div>
          <dt>数据来源参考</dt>
          <dd>{{ display(record.data_source_reference) }}</dd>
        </div>
        <div>
          <dt>样本量</dt>
          <dd>{{ display(record.sample_size) }}</dd>
        </div>
        <div>
          <dt>置信水平</dt>
          <dd>{{ display(record.confidence_level) }}</dd>
        </div>
        <div>
          <dt>有效期开始</dt>
          <dd>{{ display(record.valid_from) }}</dd>
        </div>
        <div>
          <dt>有效期结束</dt>
          <dd>{{ display(record.valid_to) }}</dd>
        </div>
      </dl>

      <section
        v-if="parameters(record).length > 0"
        class="spare-part-reliability__parameters"
      >
        <h4>模型参数</h4>
        <dl>
          <div
            v-for="parameter in parameters(record)"
            :key="parameter.key"
          >
            <dt>{{ parameter.label }}</dt>
            <dd>{{ display(parameter.value) }}</dd>
          </div>
        </dl>
      </section>
    </article>
  </section>
</template>

<script setup lang="ts">
import type {
  ReliabilityDetailRecord,
} from '@/api/maintenance/master-data-details'
import type { PageData } from '@/api/maintenance/types'
import {
  reliabilityParameterEntries,
  type ReliabilityParameterEntry,
} from './SparePartOverview'

defineProps<{
  page: PageData<ReliabilityDetailRecord>
}>()

function parameters(
  record: ReliabilityDetailRecord,
): ReliabilityParameterEntry[] {
  return reliabilityParameterEntries(record)
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '未提供'
  }

  return String(value)
}
</script>

<style scoped>
.spare-part-reliability {
  display: grid;
  gap: 16px;
}

.spare-part-reliability__record {
  display: grid;
  gap: 18px;
  padding: 20px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.spare-part-reliability__record header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.spare-part-reliability__record header span {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.spare-part-reliability__record h3,
.spare-part-reliability__record h4 {
  margin: 4px 0 0;
}

.spare-part-reliability__record > dl,
.spare-part-reliability__parameters dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}

.spare-part-reliability__record dl > div {
  min-width: 0;
}

.spare-part-reliability dt {
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.spare-part-reliability dd {
  margin: 6px 0 0;
  overflow-wrap: anywhere;
}

.spare-part-reliability__parameters {
  padding-top: 16px;
  border-top: 1px solid var(--td-component-stroke);
}

.spare-part-reliability__empty {
  padding: 24px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 8px;
  color: var(--td-text-color-secondary);
}

@media (max-width: 720px) {
  .spare-part-reliability__record > dl,
  .spare-part-reliability__parameters dl {
    grid-template-columns: 1fr;
  }
}
</style>
