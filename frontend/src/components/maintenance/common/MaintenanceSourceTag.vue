<template>
  <t-tooltip
    v-if="evidenceReference"
    :content="evidenceTooltip"
    placement="top"
  >
    <t-tag
      :theme="sourceTheme(source)"
      variant="light"
      size="small"
    >
      {{ sourceLabel(source, locale) }}
    </t-tag>
  </t-tooltip>
  <t-tag
    v-else
    :theme="sourceTheme(source)"
    variant="light"
    size="small"
  >
    {{ sourceLabel(source, locale) }}
  </t-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  normalizeMaintenanceLocale,
  sourceLabel,
  sourceTheme,
} from './status'

const props = withDefaults(
  defineProps<{
    source: string
    evidenceReference?: string
    locale?: string
  }>(),
  {
    evidenceReference: '',
    locale: 'zh-CN',
  },
)

const evidenceTooltip = computed(() => {
  const prefix = normalizeMaintenanceLocale(props.locale) === 'zh-CN'
    ? '证据引用'
    : 'Evidence reference'
  return `${prefix}: ${props.evidenceReference}`
})
</script>
