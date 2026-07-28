<template>
  <t-tag
    :theme="riskTheme(risk)"
    variant="light"
    size="small"
  >
    {{ riskLabel(risk, locale) }}
  </t-tag>
</template>

<script setup lang="ts">
import {
  riskLabel,
  riskTheme,
} from './status'

withDefaults(
  defineProps<{
    risk: string
    locale?: string
  }>(),
  {
    locale: 'zh-CN',
  },
)
</script>
