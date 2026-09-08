<template>
  <section
    class="spare-part-unavailable"
    :aria-label="`${domain}接口状态`"
  >
    <div class="spare-part-unavailable__icon">!</div>
    <div>
      <h3>当前接口未开放</h3>
      <p>
        当前 Maintenance API 路由表未提供该备件的{{ domain }}数据契约。
      </p>
      <p>{{ reason }}</p>
      <p class="spare-part-unavailable__guard">
        本页签不构造替代数据，也不会发起猜测请求。
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  domain: string
  reason: string
}>()
</script>

<style scoped>
.spare-part-unavailable {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 24px;
  border: 1px dashed var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-secondarycontainer);
}

.spare-part-unavailable__icon {
  display: grid;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: var(--td-warning-color-1);
  color: var(--td-warning-color);
  font-weight: 700;
}

.spare-part-unavailable h3 {
  margin: 0 0 10px;
}

.spare-part-unavailable p {
  margin: 6px 0 0;
  color: var(--td-text-color-secondary);
  line-height: 1.7;
}

.spare-part-unavailable__guard {
  font-weight: 600;
}
</style>
