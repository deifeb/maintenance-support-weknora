<template>
  <SparePartUnavailablePanel
    domain="批次/序列号"
    reason="当前 master-data router 未注册 lots 或 serial-items 端点。"
  />
</template>

<script setup lang="ts">
import SparePartUnavailablePanel from './SparePartUnavailablePanel.vue'
</script>
