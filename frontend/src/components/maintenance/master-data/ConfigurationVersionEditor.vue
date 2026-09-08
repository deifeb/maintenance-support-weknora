<template>
  <div
    v-if="open"
    class="configuration-editor"
    role="presentation"
    @click.self="$emit('close')"
  >
    <aside
      class="configuration-editor__panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="configuration-version-editor-title"
    >
      <header class="configuration-editor__header">
        <div>
          <span>配置版本</span>
          <h2 id="configuration-version-editor-title">
            {{ mode === 'clone' ? '克隆为草稿' : '编辑版本' }}
          </h2>
        </div>
        <button
          type="button"
          aria-label="关闭"
          @click="$emit('close')"
        >
          ×
        </button>
      </header>

      <p
        v-if="error"
        class="configuration-editor__error"
        role="alert"
      >
        {{ error.message }}
      </p>

      <form
        class="configuration-editor__form"
        @submit.prevent="submit"
      >
        <label v-if="mode === 'clone'">
          <span>版本编码</span>
          <input
            v-model.trim="form.versionCode"
            required
            type="text"
          >
        </label>

        <label>
          <span>版本名称</span>
          <input
            v-model.trim="form.versionName"
            required
            type="text"
          >
        </label>

        <label>
          <span>生效日期</span>
          <input
            v-model="form.effectiveDate"
            type="date"
          >
        </label>

        <label v-if="mode === 'edit'">
          <span>失效日期</span>
          <input
            v-model="form.expiryDate"
            type="date"
          >
        </label>

        <label v-if="mode === 'edit'">
          <span>来源依据</span>
          <input
            v-model.trim="form.sourceReference"
            type="text"
          >
        </label>

        <label
          v-if="mode === 'edit'"
          class="configuration-editor__wide"
        >
          <span>说明</span>
          <textarea
            v-model.trim="form.description"
            rows="4"
          />
        </label>

        <label class="configuration-editor__switch">
          <input
            v-model="form.isDefault"
            type="checkbox"
          >
          <span>默认版本</span>
        </label>

        <label
          v-if="mode === 'edit'"
          class="configuration-editor__switch"
        >
          <input
            v-model="form.isActive"
            type="checkbox"
          >
          <span>启用</span>
        </label>

        <footer class="configuration-editor__footer">
          <button
            type="button"
            @click="$emit('close')"
          >
            取消
          </button>
          <button
            type="submit"
            class="configuration-editor__primary"
            :disabled="saving"
          >
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </footer>
      </form>
    </aside>
  </div>
</template>

<script setup lang="ts">
import {
  reactive,
  watch,
} from 'vue'

import type { MaintenanceClientError } from '@/api/maintenance/types'
import type {
  ConfigurationClonePayload,
  ConfigurationVersion,
  ConfigurationVersionUpdatePayload,
} from '@/api/maintenance/master-data-details'
import {
  configurationCloneCode,
} from '@/components/maintenance/master-data/ConfigurationTree'

const props = defineProps<{
  open: boolean
  mode: 'edit' | 'clone'
  version: ConfigurationVersion
  saving: boolean
  error: MaintenanceClientError | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (
    event: 'save',
    payload: ConfigurationVersionUpdatePayload | ConfigurationClonePayload,
  ): void
}>()

const form = reactive({
  versionCode: '',
  versionName: '',
  effectiveDate: '',
  expiryDate: '',
  sourceReference: '',
  description: '',
  isDefault: false,
  isActive: true,
})

function reset(): void {
  form.versionCode = props.mode === 'clone'
    ? configurationCloneCode(props.version.version_code)
    : props.version.version_code
  form.versionName = props.mode === 'clone'
    ? `${props.version.version_name}（副本）`
    : props.version.version_name
  form.effectiveDate = props.version.effective_date ?? ''
  form.expiryDate = props.version.expiry_date ?? ''
  form.sourceReference = props.version.source_reference ?? ''
  form.description = props.version.description ?? ''
  form.isDefault = props.mode === 'clone'
    ? false
    : props.version.is_default
  form.isActive = props.version.is_active
}

watch(
  () => [
    props.open,
    props.mode,
    props.version,
  ],
  reset,
  { immediate: true, deep: true },
)

function optionalText(value: string): string | null {
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

function submit(): void {
  if (props.saving) {
    return
  }

  if (props.mode === 'clone') {
    emit('save', {
      version_code: form.versionCode.trim(),
      version_name: form.versionName.trim(),
      effective_date: optionalText(form.effectiveDate),
      is_default: form.isDefault,
    })
    return
  }

  emit('save', {
    version_name: form.versionName.trim(),
    effective_date: optionalText(form.effectiveDate),
    expiry_date: optionalText(form.expiryDate),
    is_default: form.isDefault,
    is_active: form.isActive,
    source_reference: optionalText(form.sourceReference),
    description: optionalText(form.description),
  })
}
</script>

<style scoped>
.configuration-editor {
  position: fixed;
  z-index: 1700;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgb(0 0 0 / 38%);
}

.configuration-editor__panel {
  width: min(620px, 100%);
  height: 100%;
  overflow: auto;
  background: var(--td-bg-color-container);
}

.configuration-editor__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 24px 28px;
  border-bottom: 1px solid var(--td-component-stroke);
}

.configuration-editor__header span {
  color: var(--td-brand-color);
  font-size: 12px;
  font-weight: 600;
}

.configuration-editor__header h2 {
  margin: 6px 0 0;
}

.configuration-editor__header button {
  border: 0;
  background: transparent;
  color: var(--td-text-color-secondary);
  font-size: 26px;
  cursor: pointer;
}

.configuration-editor__error {
  margin: 20px 28px 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--td-error-color-1);
  color: var(--td-error-color);
}

.configuration-editor__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  padding: 24px 28px 96px;
}

.configuration-editor__form label {
  display: grid;
  gap: 8px;
}

.configuration-editor__form input:not([type='checkbox']),
.configuration-editor__form textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 11px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.configuration-editor__wide {
  grid-column: 1 / -1;
}

.configuration-editor__switch {
  grid-auto-flow: column;
  justify-content: start;
  align-items: center;
}

.configuration-editor__footer {
  position: fixed;
  right: 0;
  bottom: 0;
  display: flex;
  width: min(620px, 100%);
  box-sizing: border-box;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 28px;
  border-top: 1px solid var(--td-component-stroke);
  background: var(--td-bg-color-container);
}

.configuration-editor__footer button {
  padding: 9px 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.configuration-editor__footer .configuration-editor__primary {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

@media (max-width: 640px) {
  .configuration-editor__form {
    grid-template-columns: 1fr;
  }
}
</style>
