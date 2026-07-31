<template>
  <main class="scenario-wizard">
    <header class="scenario-wizard__masthead">
      <div>
        <span class="scenario-wizard__eyebrow">
          {{ t('maintenance.scenario.eyebrow') }}
          <template v-if="sessionId">
            · SESSION {{ sessionId }}
          </template>
        </span>
        <h1>
          {{
            draft?.scenario_name
            || t('maintenance.scenario.title')
          }}
        </h1>
        <p>{{ t('maintenance.scenario.description') }}</p>
      </div>

      <div class="scenario-wizard__save-state">
        <span
          class="scenario-wizard__save-dot"
          :class="`scenario-wizard__save-dot--${autosave.status}`"
        />
        <span>
          {{
            t(
              `maintenance.scenario.autosave.${autosave.status}`,
            )
          }}
        </span>
        <small v-if="autosave.lastSavedAt">
          {{ formatSavedAt(autosave.lastSavedAt) }}
        </small>
        <strong v-if="version">v{{ version }}</strong>
      </div>
    </header>

    <MaintenanceErrorState
      v-if="error && autosave.status !== 'conflict'"
      class="scenario-wizard__error"
      :error="error"
      @retry="retrySave"
    />

    <section
      v-if="autosave.status === 'conflict'"
      class="scenario-wizard__conflict"
      role="alert"
    >
      <div>
        <span>VERSION CONFLICT</span>
        <h2>{{ t('maintenance.scenario.conflict.title') }}</h2>
        <p>{{ t('maintenance.scenario.conflict.description') }}</p>
      </div>
      <div class="scenario-wizard__conflict-compare">
        <article>
          <small>{{ t('maintenance.scenario.conflict.local') }}</small>
          <strong>{{ draft?.scenario_name }}</strong>
          <span>v{{ version }}</span>
        </article>
        <article>
          <small>{{ t('maintenance.scenario.conflict.server') }}</small>
          <strong>{{ serverDraft?.scenario_name }}</strong>
          <span>v{{ conflictServerVersion ?? '?' }}</span>
        </article>
      </div>
      <div class="scenario-wizard__conflict-actions">
        <button
          type="button"
          @click="reloadServerDraft"
        >
          {{ t('maintenance.scenario.actions.reloadServer') }}
        </button>
        <button
          type="button"
          @click="discardLocalChanges"
        >
          {{ t('maintenance.scenario.actions.discardLocal') }}
        </button>
      </div>
    </section>

    <section
      v-if="loading && !draft"
      class="scenario-wizard__loading"
      aria-live="polite"
    >
      <span />
      {{ t('maintenance.scenario.loading') }}
    </section>

    <div
      v-else-if="draft"
      class="scenario-wizard__workspace"
    >
      <aside class="scenario-wizard__rail">
        <ScenarioStepNavigation
          :current-step="draft.current_step"
          :completion="evaluation.completion"
          @navigate="goToStep"
        />
      </aside>

      <section class="scenario-wizard__editor">
        <ScenarioBasicsStep
          v-if="draft.current_step === 1"
          :draft="draft"
          :disabled="editorDisabled"
          @rename="rename"
          @patch="updateField"
          @open-evidence="openEvidence"
        />
        <ScenarioConfigurationStep
          v-else-if="draft.current_step === 2"
          :draft="draft"
          :disabled="editorDisabled"
          @patch="updateField"
          @open-evidence="openEvidence"
        />
        <ScenarioMissionStep
          v-else-if="draft.current_step === 3"
          :draft="draft"
          :disabled="editorDisabled"
          @patch="updateField"
          @open-evidence="openEvidence"
        />
        <ScenarioReliabilityRepairStep
          v-else-if="draft.current_step === 4"
          :draft="draft"
          :disabled="editorDisabled"
          @patch="updateField"
          @open-evidence="openEvidence"
        />
        <ScenarioCalculationStep
          v-else-if="draft.current_step === 5"
          :draft="draft"
          :disabled="editorDisabled"
          @patch="updateField"
          @open-evidence="openEvidence"
        />
        <ScenarioConfirmationStep
          v-else
          :draft="draft"
          :evaluation="evaluation"
          :version="version ?? 1"
          :disabled="editorDisabled"
          :saving="materializing"
          @confirm-field="confirmField"
          @materialize="handleMaterialize"
        />

        <footer class="scenario-wizard__footer">
          <button
            type="button"
            :disabled="draft.current_step <= 1"
            @click="goToStep(draft.current_step - 1)"
          >
            {{ t('maintenance.scenario.actions.previous') }}
          </button>
          <span>
            {{ draft.current_step }} / 6
          </span>
          <button
            v-if="draft.current_step < 6"
            type="button"
            class="scenario-wizard__next"
            :disabled="!canAdvance"
            @click="goToStep(draft.current_step + 1)"
          >
            {{ t('maintenance.scenario.actions.next') }}
          </button>
        </footer>
      </section>

      <aside
        v-if="evidence.length > 0"
        class="scenario-wizard__evidence"
      >
        <header>
          <span>EVIDENCE</span>
          <button
            type="button"
            aria-label="Close"
            @click="evidence = []"
          >×</button>
        </header>
        <ol>
          <li
            v-for="reference in evidence"
            :key="reference"
          >
            {{ reference }}
          </li>
        </ol>
      </aside>
    </div>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  onBeforeRouteLeave,
  useRoute,
  useRouter,
} from 'vue-router'
import type {
  ScenarioFieldState,
} from '@/api/maintenance/scenarios'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import ScenarioBasicsStep from '@/components/maintenance/scenario/ScenarioBasicsStep.vue'
import ScenarioCalculationStep from '@/components/maintenance/scenario/ScenarioCalculationStep.vue'
import ScenarioConfigurationStep from '@/components/maintenance/scenario/ScenarioConfigurationStep.vue'
import ScenarioConfirmationStep from '@/components/maintenance/scenario/ScenarioConfirmationStep.vue'
import ScenarioMissionStep from '@/components/maintenance/scenario/ScenarioMissionStep.vue'
import ScenarioReliabilityRepairStep from '@/components/maintenance/scenario/ScenarioReliabilityRepairStep.vue'
import ScenarioStepNavigation from '@/components/maintenance/scenario/ScenarioStepNavigation.vue'
import {
  WIZARD_STEPS,
  canNavigateToStep,
  evaluateWizard,
} from '@/components/maintenance/scenario/scenario-validation'
import {
  confirmedField,
  draftField,
} from '@/components/maintenance/scenario/scenario-field-utils'
import { useScenarioDraftStore } from '@/stores/maintenance/scenarioDraft'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const store = useScenarioDraftStore()
const permissionStore = useMaintenancePermissionsStore()
const {
  sessionId,
  version,
  draft,
  serverDraft,
  loading,
  error,
  autosave,
  conflictServerVersion,
} = storeToRefs(store)
const {
  load,
  createManual,
  updateField,
  rename,
  setCurrentStep,
  reloadServerDraft,
  retrySave,
  flushSave,
  discardLocalChanges,
  materialize,
  deactivate,
} = store

const evidence = ref<string[]>([])
const materializing = ref(false)
let initializationGeneration = 0

const evaluation = computed(() => (
  draft.value
    ? evaluateWizard(draft.value)
    : {
        completion: Object.fromEntries(
          WIZARD_STEPS.map(
            (step) => [step.key, false],
          ),
        ) as ReturnType<
          typeof evaluateWizard
        >['completion'],
        blockingFields: [],
        canMaterialize: false,
      }
))
const editorDisabled = computed(() => (
  materializing.value
  || !permissionStore.permissions.editMasterData
))
const canAdvance = computed(() => {
  if (!draft.value) return false
  const current = WIZARD_STEPS[
    draft.value.current_step - 1
  ]
  return Boolean(
    current
    && evaluation.value.completion[current.key],
  )
})

function positiveSessionId(
  value: unknown,
): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = Number(raw)
  return (
    Number.isInteger(parsed) && parsed > 0
      ? parsed
      : null
  )
}

async function initialize(
  queryValue: unknown,
): Promise<void> {
  const generation = ++initializationGeneration
  const targetSessionId = positiveSessionId(
    queryValue,
  )
  if (targetSessionId !== null) {
    await load(targetSessionId)
    return
  }
  const createdSessionId = await createManual(
    t('maintenance.scenario.newTitle'),
  )
  if (generation !== initializationGeneration) {
    return
  }
  await router.replace({
    query: {
      ...route.query,
      session_id: String(createdSessionId),
    },
  })
}

function goToStep(stepNumber: number): void {
  if (!draft.value) return
  const target = WIZARD_STEPS[
    Math.max(1, Math.min(6, stepNumber)) - 1
  ]
  if (
    target
    && canNavigateToStep(
      target.key,
      evaluation.value.completion,
    )
  ) {
    setCurrentStep(target.number)
  }
}

function openEvidence(references: string[]): void {
  evidence.value = [...references]
}

function confirmField(key: string): void {
  if (!draft.value) return
  updateField(
    key,
    confirmedField(
      draftField(draft.value, key),
    ),
  )
}

async function handleMaterialize(): Promise<void> {
  if (
    materializing.value
    || !evaluation.value.canMaterialize
    || sessionId.value === null
    || version.value === null
  ) {
    return
  }
  materializing.value = true
  try {
    const result = await materialize(
      `scenario-${sessionId.value}-v${version.value}`,
    )
    await router.push({
      name: 'maintenanceScenarioVersionDetail',
      params: {
        scenarioId: result.scenario_id,
        versionId: result.scenario_version_id,
      },
    })
  } catch {
    // The store exposes the normalized materialization error.
  } finally {
    materializing.value = false
  }
}

function formatSavedAt(timestamp: number): string {
  return new Intl.DateTimeFormat(
    locale.value,
    {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    },
  ).format(timestamp)
}

watch(
  () => route.query.session_id,
  (value) => {
    void initialize(value)
  },
  { immediate: true },
)

onBeforeRouteLeave(async () => {
  await flushSave()
  if (!autosave.value.dirty) {
    return true
  }
  return window.confirm(
    t('maintenance.scenario.unsavedLeave'),
  )
})

onBeforeUnmount(() => {
  initializationGeneration += 1
  deactivate()
})
</script>

<style scoped>
.scenario-wizard {
  --scenario-ink: var(--td-text-color-primary);
  max-width: 1480px;
  min-height: 100%;
  margin: 0 auto;
  padding: 28px 32px 64px;
  color: var(--scenario-ink);
}

.scenario-wizard__masthead {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
  padding: 24px;
  overflow: hidden;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background:
    linear-gradient(115deg, color-mix(in srgb, var(--td-brand-color) 10%, transparent), transparent 48%),
    repeating-linear-gradient(90deg, transparent 0 39px, color-mix(in srgb, var(--td-text-color-primary) 4%, transparent) 40px),
    var(--td-bg-color-container);
}

.scenario-wizard__eyebrow {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.12em;
}

.scenario-wizard__masthead h1 {
  max-width: 760px;
  margin: 8px 0 0;
  overflow: hidden;
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  font-size: clamp(28px, 3vw, 44px);
  font-weight: 600;
  line-height: 1.08;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scenario-wizard__masthead p {
  max-width: 680px;
  margin: 10px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 13px;
}

.scenario-wizard__save-state {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 3px 8px;
  min-width: 170px;
  padding: 11px 13px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  background: color-mix(in srgb, var(--td-bg-color-container) 88%, transparent);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-wizard__save-state small {
  grid-column: 2;
  color: var(--td-text-color-placeholder);
}

.scenario-wizard__save-state strong {
  grid-column: 1 / -1;
  margin-top: 4px;
  color: var(--td-text-color-secondary);
}

.scenario-wizard__save-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--td-text-color-placeholder);
}

.scenario-wizard__save-dot--saved {
  background: var(--td-success-color);
}

.scenario-wizard__save-dot--dirty,
.scenario-wizard__save-dot--saving {
  background: var(--td-warning-color);
}

.scenario-wizard__save-dot--saving {
  animation: save-pulse 900ms ease-in-out infinite alternate;
}

.scenario-wizard__save-dot--error,
.scenario-wizard__save-dot--conflict {
  background: var(--td-error-color);
}

.scenario-wizard__workspace {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  align-items: start;
  gap: 20px;
}

.scenario-wizard__editor,
.scenario-wizard__rail,
.scenario-wizard__evidence {
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background: var(--td-bg-color-container);
}

.scenario-wizard__rail {
  padding: 12px;
}

.scenario-wizard__editor {
  min-width: 0;
  padding: 26px;
  box-shadow: var(--td-shadow-1);
}

.scenario-wizard__workspace:has(
  .scenario-wizard__evidence
) {
  grid-template-columns: 230px minmax(0, 1fr) 260px;
}

.scenario-wizard__evidence {
  position: sticky;
  top: 20px;
  padding: 16px;
}

.scenario-wizard__evidence header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
}

.scenario-wizard__evidence button {
  border: 0;
  background: transparent;
  color: var(--td-text-color-secondary);
  font-size: 22px;
  cursor: pointer;
}

.scenario-wizard__evidence ol {
  display: grid;
  gap: 8px;
  padding-left: 20px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.scenario-wizard__editor :deep(.scenario-step) {
  display: grid;
  gap: 18px;
}

.scenario-wizard__editor :deep(.scenario-step__header) {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--td-component-stroke);
}

.scenario-wizard__editor :deep(.scenario-step__header > span) {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.12em;
}

.scenario-wizard__editor :deep(.scenario-step__header h2) {
  margin: 6px 0 0;
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  font-size: 25px;
}

.scenario-wizard__editor :deep(.scenario-step__header p) {
  max-width: 720px;
  margin: 7px 0 0;
  color: var(--td-text-color-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.scenario-wizard__editor :deep(.scenario-step__grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.scenario-wizard__editor :deep(.scenario-step__wide) {
  grid-column: 1 / -1;
}

.scenario-wizard__editor :deep(.scenario-step__notice) {
  margin: 0;
  padding: 10px 12px;
  border-radius: 5px;
  background: var(--td-bg-color-secondarycontainer);
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.scenario-wizard__editor :deep(
  .scenario-step__notice--error
) {
  color: var(--td-error-color);
}

.scenario-wizard__footer {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid var(--td-component-stroke);
}

.scenario-wizard__footer button {
  justify-self: start;
  min-height: 40px;
  padding: 0 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.scenario-wizard__footer button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.scenario-wizard__footer span {
  color: var(--td-text-color-placeholder);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-wizard__footer .scenario-wizard__next {
  justify-self: end;
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.scenario-wizard__conflict {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 1fr auto;
  align-items: center;
  gap: 20px;
  margin-bottom: 18px;
  padding: 18px;
  border: 1px solid var(--td-error-color);
  border-left-width: 4px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--td-error-color) 5%, var(--td-bg-color-container));
}

.scenario-wizard__conflict h2,
.scenario-wizard__conflict p {
  margin: 0;
}

.scenario-wizard__conflict > div > span {
  color: var(--td-error-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.1em;
}

.scenario-wizard__conflict h2 {
  margin-top: 5px;
  font-size: 17px;
}

.scenario-wizard__conflict p {
  margin-top: 5px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.scenario-wizard__conflict-compare {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.scenario-wizard__conflict-compare article {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
}

.scenario-wizard__conflict-compare strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scenario-wizard__conflict-compare small,
.scenario-wizard__conflict-compare span {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
}

.scenario-wizard__conflict-actions {
  display: grid;
  gap: 8px;
}

.scenario-wizard__conflict-actions button {
  padding: 8px 11px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.scenario-wizard__loading {
  display: flex;
  min-height: 280px;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--td-text-color-secondary);
}

.scenario-wizard__loading > span {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--td-brand-color);
  animation: save-pulse 700ms ease-in-out infinite alternate;
}

@keyframes save-pulse {
  to {
    opacity: 0.3;
    transform: scale(0.7);
  }
}

@media (max-width: 1180px) {
  .scenario-wizard__workspace,
  .scenario-wizard__workspace:has(
    .scenario-wizard__evidence
  ) {
    grid-template-columns: 210px minmax(0, 1fr);
  }

  .scenario-wizard__evidence {
    position: static;
    grid-column: 2;
  }
}

@media (max-width: 960px) {
  .scenario-wizard {
    padding: 20px 18px 48px;
  }

  .scenario-wizard__workspace,
  .scenario-wizard__workspace:has(
    .scenario-wizard__evidence
  ) {
    grid-template-columns: 1fr;
  }

  .scenario-wizard__rail,
  .scenario-wizard__evidence {
    grid-column: auto;
  }

  .scenario-wizard__conflict {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .scenario-wizard__masthead {
    align-items: flex-start;
    flex-direction: column;
  }

  .scenario-wizard__save-state {
    width: 100%;
  }

  .scenario-wizard__editor {
    padding: 18px;
  }

  .scenario-wizard__editor :deep(.scenario-step__grid) {
    grid-template-columns: 1fr;
  }

  .scenario-wizard__editor :deep(.scenario-step__wide) {
    grid-column: auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .scenario-wizard__save-dot--saving,
  .scenario-wizard__loading > span {
    animation: none;
  }
}
</style>
