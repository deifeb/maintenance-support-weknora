<template>
  <div
    v-if="open"
    class="configuration-item-editor"
    role="presentation"
    @click.self="$emit('close')"
  >
    <aside
      class="configuration-item-editor__panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="configuration-item-editor-title"
    >
      <header class="configuration-item-editor__header">
        <div>
          <span>配置项目</span>
          <h2 id="configuration-item-editor-title">
            {{ mode === 'create' ? '新增项目' : '编辑项目' }}
          </h2>
          <p v-if="parent">
            父项目：{{ parent.item_code }}
          </p>
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
        class="configuration-item-editor__error"
        role="alert"
      >
        {{ error.message }}
      </p>

      <form
        class="configuration-item-editor__form"
        @submit.prevent="submit"
      >
        <label>
          <span>项目编码</span>
          <input
            v-model.trim="form.itemCode"
            required
            type="text"
            :disabled="mode === 'edit'"
          >
        </label>

        <label>
          <span>零件 ID</span>
          <input
            v-model.number="form.partId"
            required
            min="1"
            type="number"
          >
        </label>

        <label>
          <span>备件 ID</span>
          <input
            v-model="form.sparePartId"
            min="1"
            type="number"
          >
        </label>

        <label>
          <span>装机数量</span>
          <input
            v-model.number="form.installQuantity"
            required
            min="0"
            step="any"
            type="number"
          >
        </label>

        <label>
          <span>位置编码</span>
          <input
            v-model.trim="form.positionCode"
            type="text"
          >
        </label>

        <label>
          <span>位置名称</span>
          <input
            v-model.trim="form.positionName"
            type="text"
          >
        </label>

        <label>
          <span>关键度</span>
          <select v-model="form.criticalityLevel">
            <option value="LOW">LOW</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HIGH">HIGH</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
        </label>

        <label>
          <span>替换比例</span>
          <input
            v-model.number="form.replacementRatio"
            required
            min="0"
            step="any"
            type="number"
          >
        </label>

        <label>
          <span>维修级别</span>
          <input
            v-model.trim="form.maintenanceLevel"
            type="text"
          >
        </label>

        <label>
          <span>排序号</span>
          <input
            v-model.number="form.sortOrder"
            required
            type="number"
          >
        </label>

        <label class="configuration-item-editor__switch">
          <input
            v-model="form.isMandatory"
            type="checkbox"
          >
          <span>必装项目</span>
        </label>

        <label class="configuration-item-editor__wide">
          <span>依据与备注</span>
          <textarea
            v-model.trim="form.notes"
            rows="4"
          />
        </label>

        <footer class="configuration-item-editor__footer">
          <button
            type="button"
            @click="$emit('close')"
          >
            取消
          </button>
          <button
            type="submit"
            class="configuration-item-editor__primary"
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
  ConfigurationItemCreatePayload,
  ConfigurationItemUpdatePayload,
  ConfigurationTreeNode,
  CriticalityLevel,
} from '@/api/maintenance/master-data-details'

const props = defineProps<{
  open: boolean
  mode: 'create' | 'edit'
  configurationId: number
  parent: ConfigurationTreeNode | null
  item: ConfigurationTreeNode | null
  saving: boolean
  error: MaintenanceClientError | null
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (
    event: 'save',
    payload: ConfigurationItemCreatePayload | ConfigurationItemUpdatePayload,
  ): void
}>()

const form = reactive({
  itemCode: '',
  partId: 0,
  sparePartId: '',
  installQuantity: 1,
  positionCode: '',
  positionName: '',
  criticalityLevel: 'MEDIUM' as CriticalityLevel,
  replacementRatio: 1,
  maintenanceLevel: '',
  isMandatory: true,
  sortOrder: 0,
  notes: '',
})

function reset(): void {
  form.itemCode = props.item?.item_code ?? ''
  form.partId = props.item?.part_id ?? 0
  form.sparePartId = props.item?.spare_part_id === null
    || props.item?.spare_part_id === undefined
    ? ''
    : String(props.item.spare_part_id)
  form.installQuantity = Number(props.item?.install_quantity ?? 1)
  form.positionCode = props.item?.position_code ?? ''
  form.positionName = props.item?.position_name ?? ''
  form.criticalityLevel = props.item?.criticality_level ?? 'MEDIUM'
  form.replacementRatio = Number(props.item?.replacement_ratio ?? 1)
  form.maintenanceLevel = props.item?.maintenance_level ?? ''
  form.isMandatory = props.item?.is_mandatory ?? true
  form.sortOrder = props.item?.sort_order ?? 0
  form.notes = props.item?.notes ?? ''
}

watch(
  () => [
    props.open,
    props.mode,
    props.configurationId,
    props.parent,
    props.item,
  ],
  reset,
  { immediate: true, deep: true },
)

function optionalText(value: string): string | null {
  const normalized = value.trim()
  return normalized.length > 0 ? normalized : null
}

function optionalId(value: string): number | null {
  const normalized = value.trim()
  return normalized.length > 0 ? Number(normalized) : null
}

function sharedValues() {
  return {
    parent_item_id: props.parent?.id ?? props.item?.parent_item_id ?? null,
    part_id: Number(form.partId),
    spare_part_id: optionalId(form.sparePartId),
    install_quantity: Number(form.installQuantity),
    position_code: optionalText(form.positionCode),
    position_name: optionalText(form.positionName),
    criticality_level: form.criticalityLevel,
    replacement_ratio: Number(form.replacementRatio),
    maintenance_level: optionalText(form.maintenanceLevel),
    is_mandatory: form.isMandatory,
    sort_order: Number(form.sortOrder),
    notes: optionalText(form.notes),
  }
}

function submit(): void {
  if (props.saving) {
    return
  }

  const values = sharedValues()

  if (props.mode === 'create') {
    emit('save', {
      configuration_version_id: props.configurationId,
      item_code: form.itemCode.trim(),
      ...values,
    })
    return
  }

  emit('save', values)
}
</script>

<style scoped>
.configuration-item-editor {
  position: fixed;
  z-index: 1700;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgb(0 0 0 / 38%);
}

.configuration-item-editor__panel {
  width: min(720px, 100%);
  height: 100%;
  overflow: auto;
  background: var(--td-bg-color-container);
}

.configuration-item-editor__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 24px 28px;
  border-bottom: 1px solid var(--td-component-stroke);
}

.configuration-item-editor__header span {
  color: var(--td-brand-color);
  font-size: 12px;
  font-weight: 600;
}

.configuration-item-editor__header h2 {
  margin: 6px 0 0;
}

.configuration-item-editor__header p {
  margin: 6px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.configuration-item-editor__header button {
  border: 0;
  background: transparent;
  color: var(--td-text-color-secondary);
  font-size: 26px;
  cursor: pointer;
}

.configuration-item-editor__error {
  margin: 20px 28px 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--td-error-color-1);
  color: var(--td-error-color);
}

.configuration-item-editor__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  padding: 24px 28px 96px;
}

.configuration-item-editor__form label {
  display: grid;
  gap: 8px;
}

.configuration-item-editor__form input:not([type='checkbox']),
.configuration-item-editor__form select,
.configuration-item-editor__form textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px 11px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.configuration-item-editor__wide {
  grid-column: 1 / -1;
}

.configuration-item-editor__switch {
  grid-auto-flow: column;
  justify-content: start;
  align-items: center;
}

.configuration-item-editor__footer {
  position: fixed;
  right: 0;
  bottom: 0;
  display: flex;
  width: min(720px, 100%);
  box-sizing: border-box;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 28px;
  border-top: 1px solid var(--td-component-stroke);
  background: var(--td-bg-color-container);
}

.configuration-item-editor__footer button {
  padding: 9px 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.configuration-item-editor__footer .configuration-item-editor__primary {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: #fff;
}

@media (max-width: 640px) {
  .configuration-item-editor__form {
    grid-template-columns: 1fr;
  }
}
</style>
