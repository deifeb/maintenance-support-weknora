<template>
  <div
    v-if="open"
    class="master-data-drawer"
    role="presentation"
    @click.self="$emit('close')"
  >
    <aside
      class="master-data-drawer__panel"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="drawerTitleId"
    >
      <header class="master-data-drawer__header">
        <div>
          <span class="master-data-drawer__eyebrow">
            {{ resource.title }}
          </span>
          <h2 :id="drawerTitleId">
            {{ drawerTitle }}
          </h2>
        </div>
        <button
          type="button"
          class="master-data-drawer__close"
          aria-label="关闭"
          @click="$emit('close')"
        >
          ×
        </button>
      </header>

      <MaintenanceErrorState
        v-if="error"
        :error="error"
        class="master-data-drawer__error"
      />

      <form
        class="master-data-drawer__form"
        @submit.prevent="submit"
      >
        <label
          v-for="field in resource.form"
          :key="field.key"
          class="master-data-drawer__field"
        >
          <span class="master-data-drawer__label">
            {{ field.label }}
            <span v-if="field.required" aria-hidden="true">*</span>
          </span>

          <textarea
            v-if="field.control === 'text' && field.multiline"
            :value="stringValue(field.key)"
            :required="field.required"
            :disabled="isFieldDisabled(field)"
            :placeholder="field.placeholder"
            rows="4"
            @input="updateText(field.key, $event)"
          />

          <input
            v-else-if="field.control === 'text' || field.control === 'date'"
            :type="field.control === 'date' ? 'date' : 'text'"
            :value="stringValue(field.key)"
            :required="field.required"
            :disabled="isFieldDisabled(field)"
            :placeholder="field.placeholder"
            @input="updateText(field.key, $event)"
          >

          <input
            v-else-if="field.control === 'number'"
            type="number"
            :value="numberValue(field.key)"
            :required="field.required"
            :disabled="isFieldDisabled(field)"
            :min="field.min"
            :max="field.max"
            :step="field.step ?? 'any'"
            @input="updateNumber(field.key, $event)"
          >

          <select
            v-else-if="field.control === 'select'"
            :value="selectValue(field.key)"
            :required="field.required"
            :disabled="isFieldDisabled(field)"
            @change="updateSelect(field, $event)"
          >
            <option value="">
              请选择
            </option>
            <option
              v-for="option in field.options ?? []"
              :key="String(option.value)"
              :value="String(option.value)"
            >
              {{ option.label }}
            </option>
          </select>

          <span
            v-else-if="field.control === 'switch'"
            class="master-data-drawer__switch"
          >
            <input
              type="checkbox"
              :checked="Boolean(formValues[field.key])"
              :disabled="isFieldDisabled(field)"
              @change="updateSwitch(field.key, $event)"
            >
            <span>{{ Boolean(formValues[field.key]) ? '是' : '否' }}</span>
          </span>
        </label>

        <footer class="master-data-drawer__footer">
          <button
            type="button"
            class="master-data-drawer__button master-data-drawer__button--secondary"
            @click="$emit('close')"
          >
            {{ readonlyMode ? '关闭' : '取消' }}
          </button>
          <button
            v-if="!readonlyMode"
            type="submit"
            class="master-data-drawer__button master-data-drawer__button--primary"
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
  computed,
  ref,
  watch,
} from 'vue'

import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import type {
  MasterDataFormField,
  MasterDataRecord,
  MasterDataResourceDefinition,
} from './MasterDataRegistry'

const props = withDefaults(
  defineProps<{
    open: boolean
    resource: MasterDataResourceDefinition
    record?: MasterDataRecord | null
    mode?: 'create' | 'edit' | 'view'
    saving?: boolean
    error?: MaintenanceClientError | null
  }>(),
  {
    record: null,
    mode: 'create',
    saving: false,
    error: null,
  },
)

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'save', values: MasterDataRecord): void
}>()

const formValues = ref<MasterDataRecord>({})
const drawerTitleId = 'maintenance-master-data-editor-title'

const readonlyMode = computed(
  () => props.mode === 'view' || props.resource.availability !== 'available',
)

const drawerTitle = computed(() => {
  if (props.mode === 'view') {
    return '查看记录'
  }
  if (props.mode === 'edit') {
    return '编辑记录'
  }
  return '新建记录'
})

function resetForm(): void {
  const nextValues: MasterDataRecord = {}

  props.resource.form.forEach((field) => {
    const sourceKey = field.apiKey ?? field.key
    const recordValue = props.record?.[sourceKey]
    nextValues[field.key] = recordValue ?? field.defaultValue ?? ''
  })

  formValues.value = nextValues
}

watch(
  () => [
    props.open,
    props.resource.key,
    props.record,
    props.mode,
  ],
  resetForm,
  { immediate: true, deep: true },
)

function isFieldDisabled(field: MasterDataFormField): boolean {
  return readonlyMode.value || (props.mode === 'edit' && Boolean(field.createOnly))
}

function stringValue(key: string): string {
  const value = formValues.value[key]
  return value === null || value === undefined ? '' : String(value)
}

function numberValue(key: string): string | number {
  const value = formValues.value[key]
  return typeof value === 'number' || typeof value === 'string' ? value : ''
}

function selectValue(key: string): string {
  const value = formValues.value[key]
  return value === null || value === undefined ? '' : String(value)
}

function updateText(key: string, event: Event): void {
  formValues.value[key] = (event.target as HTMLInputElement).value
}

function updateNumber(key: string, event: Event): void {
  const raw = (event.target as HTMLInputElement).value
  formValues.value[key] = raw === '' ? undefined : Number(raw)
}

function updateSwitch(key: string, event: Event): void {
  formValues.value[key] = (event.target as HTMLInputElement).checked
}

function updateSelect(
  field: MasterDataFormField,
  event: Event,
): void {
  const raw = (event.target as HTMLSelectElement).value
  const option = field.options?.find(
    (candidate) => String(candidate.value) === raw,
  )
  formValues.value[field.key] = option?.value ?? raw
}

function submit(): void {
  if (!readonlyMode.value && !props.saving) {
    emit('save', { ...formValues.value })
  }
}
</script>

<style scoped>
.master-data-drawer {
  position: fixed;
  z-index: 1600;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgb(0 0 0 / 38%);
}

.master-data-drawer__panel {
  width: min(620px, 100%);
  height: 100%;
  overflow: auto;
  background: var(--td-bg-color-container);
  box-shadow: var(--td-shadow-3);
}

.master-data-drawer__header {
  position: sticky;
  z-index: 2;
  top: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  border-bottom: 1px solid var(--td-component-stroke);
  background: var(--td-bg-color-container);
}

.master-data-drawer__eyebrow {
  color: var(--td-brand-color);
  font-size: 12px;
  font-weight: 600;
}

.master-data-drawer__header h2 {
  margin: 6px 0 0;
  font-size: 22px;
}

.master-data-drawer__close {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-size: 24px;
  cursor: pointer;
}

.master-data-drawer__error {
  margin: 20px 28px 0;
}

.master-data-drawer__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  padding: 24px 28px 96px;
}

.master-data-drawer__field {
  display: grid;
  gap: 8px;
}

.master-data-drawer__field:has(textarea) {
  grid-column: 1 / -1;
}

.master-data-drawer__label {
  color: var(--td-text-color-primary);
  font-size: 13px;
  font-weight: 500;
}

.master-data-drawer__label span {
  color: var(--td-error-color);
}

.master-data-drawer input:not([type='checkbox']),
.master-data-drawer select,
.master-data-drawer textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 11px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.master-data-drawer input:focus,
.master-data-drawer select:focus,
.master-data-drawer textarea:focus {
  border-color: var(--td-brand-color);
  outline: none;
}

.master-data-drawer input:disabled,
.master-data-drawer select:disabled,
.master-data-drawer textarea:disabled {
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-placeholder);
}

.master-data-drawer__switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
}

.master-data-drawer__footer {
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

.master-data-drawer__button {
  min-width: 84px;
  padding: 9px 16px;
  border-radius: 6px;
  font: inherit;
  cursor: pointer;
}

.master-data-drawer__button--secondary {
  border: 1px solid var(--td-component-stroke);
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
}

.master-data-drawer__button--primary {
  border: 1px solid var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

.master-data-drawer__button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

@media (max-width: 640px) {
  .master-data-drawer__form {
    grid-template-columns: 1fr;
  }
}
</style>
