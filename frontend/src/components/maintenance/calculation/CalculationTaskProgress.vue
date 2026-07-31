<template>
  <article class="task-progress" :data-status="child.calculation_status">
    <header>
      <div>
        <span>{{ child.is_primary ? primaryLabel : candidateLabel }}</span>
        <h3>{{ child.candidate_key }}</h3>
      </div>
      <strong>{{ child.calculation_status }}</strong>
    </header>

    <dl>
      <div>
        <dt>{{ modelLabel }}</dt>
        <dd>{{ child.reliability_model }}</dd>
      </div>
      <div>
        <dt>{{ modeLabel }}</dt>
        <dd>{{ child.execution_mode }}</dd>
      </div>
      <div>
        <dt>{{ attemptLabel }}</dt>
        <dd>#{{ child.attempt_number }}</dd>
      </div>
      <div>
        <dt>{{ stageLabel }}</dt>
        <dd>{{ child.current_stage || child.calculation_status }}</dd>
      </div>
    </dl>

    <div class="task-progress__meter">
      <div
        class="task-progress__fill"
        :style="{ width: `${boundedProgress}%` }"
      />
    </div>
    <div class="task-progress__percent">
      <span>{{ progressLabel }}</span>
      <strong>{{ child.progress_percent }}%</strong>
    </div>

    <ul v-if="child.warnings?.length" class="task-progress__warnings">
      <li v-for="warning in child.warnings" :key="warning">
        {{ warning }}
      </li>
    </ul>
    <p v-if="child.terminal_error" class="task-progress__error">
      {{ child.terminal_error }}
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  CalculationGroupChild,
} from '@/api/maintenance/calculation-groups'

const props = withDefaults(
  defineProps<{
    child: CalculationGroupChild
    candidateLabel?: string
    primaryLabel?: string
    modelLabel?: string
    modeLabel?: string
    attemptLabel?: string
    stageLabel?: string
    progressLabel?: string
  }>(),
  {
    candidateLabel: 'Candidate',
    primaryLabel: 'Primary candidate',
    modelLabel: 'Reliability model',
    modeLabel: 'Execution mode',
    attemptLabel: 'Attempt',
    stageLabel: 'Current stage',
    progressLabel: 'Progress',
  },
)

const boundedProgress = computed(() => {
  const value = Number(props.child.progress_percent)
  return Number.isFinite(value)
    ? Math.min(100, Math.max(0, value))
    : 0
})
</script>

<style scoped>
.task-progress {
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-top: 3px solid var(--td-brand-color);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.task-progress[data-status="SUCCEEDED"],
.task-progress[data-status="PARTIAL_SUCCESS"] {
  border-top-color: var(--td-success-color);
}

.task-progress[data-status="FAILED"] {
  border-top-color: var(--td-error-color);
}

.task-progress > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.task-progress header span,
.task-progress dt,
.task-progress__percent span {
  color: var(--td-text-color-placeholder);
  font-size: 9px;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.task-progress h3 {
  margin: 4px 0 0;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 13px;
}

.task-progress header > strong {
  color: var(--td-brand-color);
  font-size: 10px;
}

.task-progress dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;
}

.task-progress dd {
  margin: 3px 0 0;
  color: var(--td-text-color-primary);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.task-progress__meter {
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--td-bg-color-secondarycontainer);
}

.task-progress__fill {
  height: 100%;
  border-radius: inherit;
  background: var(--td-brand-color);
  transition: width .25s ease;
}

.task-progress__percent {
  display: flex;
  justify-content: space-between;
  margin-top: 7px;
}

.task-progress__percent strong {
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.task-progress__warnings,
.task-progress__error {
  margin: 13px 0 0;
  padding: 9px 11px;
  border-radius: 4px;
  font-size: 11px;
}

.task-progress__warnings {
  padding-left: 28px;
  background: var(--td-warning-color-1);
  color: var(--td-warning-color);
}

.task-progress__error {
  background: var(--td-error-color-1);
  color: var(--td-error-color);
  overflow-wrap: anywhere;
}
</style>
