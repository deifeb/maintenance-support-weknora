<template>
  <t-tag
    :theme="lifecycleTheme(status)"
    variant="light"
    size="small"
  >
    {{ label || lifecycleLabel(status, locale) }}
  </t-tag>
</template>

<script setup lang="ts">
import {
  lifecycleLabel,
  lifecycleTheme,
} from './status'

withDefaults(
  defineProps<{
    status: string
    label?: string
    locale?: string
  }>(),
  {
    label: '',
    locale: 'zh-CN',
  },
)
</script>
