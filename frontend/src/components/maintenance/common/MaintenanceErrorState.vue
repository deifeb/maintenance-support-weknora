<template>
  <section
    class="maintenance-error-state"
    role="alert"
  >
    <div class="maintenance-error-state__icon" aria-hidden="true">
      !
    </div>
    <div class="maintenance-error-state__content">
      <h3 class="maintenance-error-state__title">
        {{ resolvedTitle }}
      </h3>
      <p class="maintenance-error-state__message">
        {{ error.message }}
      </p>
      <div class="maintenance-error-state__metadata">
        <span v-if="error.code">
          {{ codeLabel }}: {{ error.code }}
        </span>
        <span v-if="error.request_id">
          {{ requestIdLabel }}: {{ error.request_id }}
        </span>
      </div>
      <t-button
        v-if="error.retryable"
        class="maintenance-error-state__retry"
        theme="primary"
        variant="outline"
        @click="$emit('retry')"
      >
        {{ resolvedRetryLabel }}
      </t-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import { normalizeMaintenanceLocale } from './status'

const props = withDefaults(
  defineProps<{
    error: MaintenanceClientError
    title?: string
    retryLabel?: string
    locale?: string
  }>(),
  {
    title: '',
    retryLabel: '',
    locale: 'zh-CN',
  },
)

defineEmits<{
  (event: 'retry'): void
}>()

const isChinese = computed(
  () => normalizeMaintenanceLocale(props.locale) === 'zh-CN',
)

const resolvedTitle = computed(
  () => props.title || (isChinese.value ? '加载失败' : 'Unable to load data'),
)

const resolvedRetryLabel = computed(
  () => props.retryLabel || (isChinese.value ? '重试' : 'Retry'),
)

const codeLabel = computed(
  () => (isChinese.value ? '错误代码' : 'Error code'),
)

const requestIdLabel = computed(
  () => (isChinese.value ? '请求 ID' : 'Request ID'),
)
</script>

<style scoped>
.maintenance-error-state {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  border: 1px solid var(--td-error-color-3);
  border-radius: 10px;
  background: var(--td-error-color-1);
}

.maintenance-error-state__icon {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  border-radius: 50%;
  background: var(--td-error-color);
  color: #fff;
  font-weight: 700;
}

.maintenance-error-state__content {
  min-width: 0;
}

.maintenance-error-state__title {
  margin: 0;
  color: var(--td-text-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.maintenance-error-state__message {
  margin: 6px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.maintenance-error-state__metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 8px;
  color: var(--td-text-color-placeholder);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.maintenance-error-state__retry {
  margin-top: 14px;
}
</style>
