<template>
  <div
    class="maintenance-metric-card"
    :class="{
      'maintenance-metric-card--clickable': clickable,
    }"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :aria-disabled="clickable ? false : undefined"
    @click="triggerClick"
    @keydown.enter.prevent="triggerClick"
    @keydown.space.prevent="triggerClick"
  >
    <div class="maintenance-metric-card__header">
      <span class="maintenance-metric-card__label">
        {{ label }}
      </span>
      <slot name="extra" />
    </div>

    <div
      v-if="loading"
      class="maintenance-metric-card__skeleton"
      aria-label="loading"
    >
      <span />
      <span />
    </div>

    <template v-else>
      <div class="maintenance-metric-card__value-row">
        <strong class="maintenance-metric-card__value">
          {{ value }}
        </strong>
        <span
          v-if="suffix"
          class="maintenance-metric-card__suffix"
        >
          {{ suffix }}
        </span>
      </div>

      <div
        v-if="trend !== undefined || trendLabel"
        class="maintenance-metric-card__trend"
        :class="trendClass"
      >
        <span v-if="trend !== undefined">
          {{ trendText }}
        </span>
        <span v-if="trendLabel">
          {{ trendLabel }}
        </span>
      </div>

      <div
        v-if="$slots.footer"
        class="maintenance-metric-card__footer"
      >
        <slot name="footer" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    suffix?: string
    trend?: number
    trendLabel?: string
    loading?: boolean
    clickable?: boolean
  }>(),
  {
    suffix: '',
    trend: undefined,
    trendLabel: '',
    loading: false,
    clickable: false,
  },
)

const emit = defineEmits<{
  (event: 'click'): void
}>()

const trendClass = computed(() => {
  if (props.trend === undefined || props.trend === 0) {
    return 'maintenance-metric-card__trend--neutral'
  }
  return props.trend > 0
    ? 'maintenance-metric-card__trend--positive'
    : 'maintenance-metric-card__trend--negative'
})

const trendText = computed(() => {
  if (props.trend === undefined) {
    return ''
  }
  const prefix = props.trend > 0 ? '+' : ''
  return `${prefix}${props.trend}%`
})

function triggerClick(): void {
  if (props.clickable) {
    emit('click')
  }
}
</script>

<style scoped>
.maintenance-metric-card {
  min-width: 0;
  padding: 20px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
  box-shadow: var(--td-shadow-1);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.maintenance-metric-card--clickable {
  cursor: pointer;
}

.maintenance-metric-card--clickable:hover,
.maintenance-metric-card--clickable:focus-visible {
  border-color: var(--td-brand-color);
  box-shadow: var(--td-shadow-2);
  outline: none;
}

.maintenance-metric-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.maintenance-metric-card__label {
  color: var(--td-text-color-secondary);
  font-size: 14px;
  line-height: 22px;
}

.maintenance-metric-card__value-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 12px;
}

.maintenance-metric-card__value {
  color: var(--td-text-color-primary);
  font-size: 30px;
  font-weight: 600;
  line-height: 1.2;
}

.maintenance-metric-card__suffix {
  color: var(--td-text-color-secondary);
  font-size: 14px;
}

.maintenance-metric-card__trend {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  font-size: 12px;
  line-height: 20px;
}

.maintenance-metric-card__trend--positive {
  color: var(--td-success-color);
}

.maintenance-metric-card__trend--negative {
  color: var(--td-error-color);
}

.maintenance-metric-card__trend--neutral {
  color: var(--td-text-color-placeholder);
}

.maintenance-metric-card__footer {
  margin-top: 14px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.maintenance-metric-card__skeleton {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.maintenance-metric-card__skeleton span {
  display: block;
  height: 16px;
  border-radius: 6px;
  background: linear-gradient(
    90deg,
    var(--td-bg-color-secondarycontainer) 25%,
    var(--td-bg-color-container-hover) 37%,
    var(--td-bg-color-secondarycontainer) 63%
  );
  background-size: 400% 100%;
  animation: maintenance-skeleton 1.4s ease infinite;
}

.maintenance-metric-card__skeleton span:first-child {
  width: 62%;
  height: 34px;
}

.maintenance-metric-card__skeleton span:last-child {
  width: 42%;
}

@keyframes maintenance-skeleton {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}
</style>
