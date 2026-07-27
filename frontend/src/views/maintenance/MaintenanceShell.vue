<template>
  <main class="maintenance-shell">
    <RouterView />
  </main>
</template>

<style scoped>
.maintenance-shell {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: auto;
  background: var(--td-bg-color-page);
}
</style>
