<template>
  <nav
    class="scenario-steps"
    :aria-label="t('maintenance.scenario.stepsLabel')"
  >
    <button
      v-for="step in WIZARD_STEPS"
      :key="step.key"
      type="button"
      class="scenario-steps__item"
      :class="{
        'scenario-steps__item--active': step.number === currentStep,
        'scenario-steps__item--complete': completion[step.key],
        'scenario-steps__item--locked': !canOpen(step.key),
      }"
      :disabled="!canOpen(step.key)"
      :aria-current="step.number === currentStep ? 'step' : undefined"
      @click="emit('navigate', step.number)"
    >
      <span class="scenario-steps__index">
        <template v-if="completion[step.key]">✓</template>
        <template v-else>{{ step.number }}</template>
      </span>
      <span class="scenario-steps__copy">
        <strong>
          {{ t(`maintenance.scenario.steps.${step.key}`) }}
        </strong>
        <small>
          {{
            completion[step.key]
              ? t('maintenance.scenario.complete')
              : t('maintenance.scenario.incomplete')
          }}
        </small>
      </span>
    </button>

    <div class="scenario-steps__meter">
      <span
        :style="{ width: `${completionPercent}%` }"
      />
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  WIZARD_STEPS,
  canNavigateToStep,
  type WizardStepKey,
} from './scenario-validation'

const props = defineProps<{
  currentStep: number
  completion: Record<WizardStepKey, boolean>
}>()

const emit = defineEmits<{
  navigate: [step: number]
}>()

const { t } = useI18n()

function canOpen(key: WizardStepKey): boolean {
  return canNavigateToStep(
    key,
    props.completion,
  )
}

const completionPercent = computed(() => {
  const completed = WIZARD_STEPS.filter(
    (step) => props.completion[step.key],
  ).length
  return Math.round(
    (completed / WIZARD_STEPS.length) * 100,
  )
})
</script>

<style scoped>
.scenario-steps {
  position: sticky;
  top: 20px;
  display: grid;
  gap: 4px;
}

.scenario-steps__item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--td-text-color-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.scenario-steps__item:hover:not(:disabled) {
  background: var(--td-bg-color-secondarycontainer);
}

.scenario-steps__item--active {
  border-color: var(--td-brand-color);
  background: color-mix(in srgb, var(--td-brand-color) 8%, transparent);
  color: var(--td-text-color-primary);
}

.scenario-steps__item--locked {
  cursor: not-allowed;
  opacity: 0.46;
}

.scenario-steps__index {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--td-component-stroke);
  border-radius: 50%;
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-steps__item--active .scenario-steps__index {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.scenario-steps__item--complete .scenario-steps__index {
  border-color: var(--td-success-color);
  color: var(--td-success-color);
}

.scenario-steps__copy {
  display: grid;
  gap: 2px;
}

.scenario-steps__copy strong {
  font-size: 13px;
  font-weight: 650;
}

.scenario-steps__copy small {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.scenario-steps__meter {
  height: 3px;
  margin: 12px 10px 0;
  overflow: hidden;
  border-radius: 999px;
  background: var(--td-bg-color-secondarycontainer);
}

.scenario-steps__meter span {
  display: block;
  height: 100%;
  background: var(--td-success-color);
  transition: width 220ms ease;
}

@media (max-width: 960px) {
  .scenario-steps {
    position: static;
    grid-template-columns: repeat(6, minmax(120px, 1fr));
    overflow-x: auto;
    padding-bottom: 8px;
  }

  .scenario-steps__meter {
    display: none;
  }
}
</style>
