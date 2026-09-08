<template>
  <section v-if="open" class="inventory-preview" role="dialog" aria-modal="true">
    <div class="inventory-preview__panel">
      <header class="inventory-preview__header">
        <div>
          <p>{{ t('maintenance.inventory.operations.preview.eyebrow') }}</p>
          <h2>{{ t('maintenance.inventory.operations.preview.title') }}</h2>
        </div>
        <button type="button" :disabled="busy" @click="emit('close')">
          {{ t('maintenance.inventory.operations.preview.close') }}
        </button>
      </header>

      <section class="inventory-preview__command">
        <h3>{{ t('maintenance.inventory.operations.preview.commandSummary') }}</h3>
        <pre data-testid="command-summary">{{ commandSummary }}</pre>
      </section>

      <section v-if="preview" class="inventory-preview__metadata">
        <h3>{{ t('maintenance.inventory.operations.preview.serverMetadata') }}</h3>
        <dl>
          <div><dt>transaction_id</dt><dd>{{ transactionId }}</dd></div>
          <div><dt>operation_type</dt><dd>{{ operationType }}</dd></div>
          <div><dt>transaction_version</dt><dd>{{ transactionVersion }}</dd></div>
          <div><dt>confirmation_expires_at</dt><dd>{{ confirmationExpiresAt }}</dd></div>
        </dl>
      </section>

      <p v-if="error" class="inventory-preview__error" role="alert">{{ error }}</p>

      <footer class="inventory-preview__actions">
        <button type="button" :disabled="busy" @click="emit('close')">
          {{ t('maintenance.inventory.operations.preview.close') }}
        </button>
        <button
          type="button"
          :disabled="busy || !preview || !canExecute"
          @click="emit('execute')"
        >
          {{ busy
            ? t('maintenance.inventory.operations.preview.executing')
            : t('maintenance.inventory.operations.preview.execute') }}
        </button>
      </footer>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { InventoryOperationPreviewRead } from '@/api/maintenance/inventory'

const props = withDefaults(defineProps<{
  open: boolean
  commandSummary: string
  preview: InventoryOperationPreviewRead | null
  busy?: boolean
  canExecute?: boolean
  error?: string
}>(), {
  busy: false,
  canExecute: false,
  error: '',
})

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'execute'): void
}>()

const { t } = useI18n()
const transactionId = computed(() => props.preview?.transaction_id ?? '—')
const operationType = computed(() => props.preview?.operation_type ?? '—')
const transactionVersion = computed(() => props.preview?.transaction_version ?? '—')
const confirmationExpiresAt = computed(() => props.preview?.confirmation_expires_at ?? '—')
</script>

<style scoped>
.inventory-preview { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 24px; background: rgb(0 0 0 / 45%); }
.inventory-preview__panel { width: min(680px, 100%); max-height: 90vh; overflow: auto; padding: 22px; border-radius: 10px; background: var(--td-bg-color-container); box-shadow: var(--td-shadow-3); }
.inventory-preview__header, .inventory-preview__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.inventory-preview__header p { margin: 0; color: var(--td-text-color-secondary); font-size: 11px; letter-spacing: .08em; }
.inventory-preview__header h2 { margin: 4px 0 0; }
.inventory-preview__command, .inventory-preview__metadata { margin-top: 18px; }
.inventory-preview__command pre { overflow: auto; padding: 12px; border-radius: 6px; background: var(--td-bg-color-page); white-space: pre-wrap; }
.inventory-preview__metadata dl { display: grid; gap: 8px; }
.inventory-preview__metadata dl div { display: grid; grid-template-columns: minmax(160px, .7fr) 1fr; gap: 10px; }
.inventory-preview__metadata dt { color: var(--td-text-color-secondary); }
.inventory-preview__metadata dd { margin: 0; word-break: break-word; }
.inventory-preview__error { margin-top: 16px; color: var(--td-error-color); }
.inventory-preview__actions { margin-top: 20px; justify-content: flex-end; }
</style>
