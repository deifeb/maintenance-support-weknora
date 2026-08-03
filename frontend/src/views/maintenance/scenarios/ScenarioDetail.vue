<template>
  <main class="scenario-detail">
    <button
      type="button"
      class="scenario-detail__back"
      @click="backToList"
    >
      ← {{ t('maintenance.scenario.detail.back') }}
    </button>

    <section
      v-if="invalidRoute"
      class="scenario-detail__invalid"
      role="alert"
    >
      <h1>{{ t('maintenance.scenario.detail.invalid') }}</h1>
    </section>

    <template v-else>
      <MaintenanceErrorState
        v-if="error"
        :error="error"
        @retry="load"
      />

      <section
        v-if="loading && !scenario"
        class="scenario-detail__loading"
      >
        {{ t('maintenance.scenario.loading') }}
      </section>

      <template v-if="scenario">
        <header class="scenario-detail__hero">
          <div>
            <span>{{ scenario.code }}</span>
            <h1>{{ scenario.name }}</h1>
            <p>{{ scenario.description || '—' }}</p>
          </div>
          <dl>
            <div>
              <dt>{{ t('maintenance.scenario.list.category') }}</dt>
              <dd>{{ scenario.category || '—' }}</dd>
            </div>
            <div>
              <dt>{{ t('maintenance.scenario.detail.lifecycle') }}</dt>
              <dd>
                {{
                  scenario.is_active
                    ? t('maintenance.scenario.detail.active')
                    : t('maintenance.scenario.detail.inactive')
                }}
              </dd>
            </div>
            <div>
              <dt>{{ t('maintenance.scenario.list.updatedAt') }}</dt>
              <dd>{{ formatDate(scenario.updated_at) }}</dd>
            </div>
          </dl>
        </header>

        <div class="scenario-detail__layout">
          <aside class="scenario-detail__versions">
            <header>
              <h2>{{ t('maintenance.scenario.detail.versions') }}</h2>
              <span>{{ versions.length }}</span>
            </header>
            <button
              v-for="item in versions"
              :key="item.id"
              type="button"
              :class="{
                'scenario-detail__version--active': (
                  fullVersion?.version.id === item.id
                ),
              }"
              @click="openVersion(item.id)"
            >
              <span>
                <strong>{{ item.version_code }}</strong>
                <small>{{ item.version_name }}</small>
              </span>
              <MaintenanceStatusTag :status="item.status" />
            </button>
          </aside>

          <section
            v-if="fullVersion"
            class="scenario-detail__version"
          >
            <header class="scenario-detail__version-header">
              <div>
                <span>
                  VERSION {{ fullVersion.version.version_code }}
                </span>
                <h2>{{ fullVersion.version.version_name }}</h2>
              </div>
              <div class="scenario-detail__version-actions">
                <button
                  v-if="canEditVersion"
                  type="button"
                  @click="editing = !editing"
                >
                  {{
                    editing
                      ? t('maintenance.scenario.detail.cancelEdit')
                      : t('maintenance.scenario.detail.edit')
                  }}
                </button>
                <button
                  v-if="canPublishVersion"
                  type="button"
                  class="scenario-detail__publish"
                  :disabled="saving"
                  @click="confirmLifecycle('publish')"
                >
                  {{ t('maintenance.scenario.detail.publish') }}
                </button>
                <button
                  v-if="canRetireVersion"
                  type="button"
                  class="scenario-detail__retire"
                  :disabled="saving"
                  @click="confirmLifecycle('retire')"
                >
                  {{ t('maintenance.scenario.detail.retire') }}
                </button>
              </div>
            </header>

            <div class="scenario-detail__facts">
              <article>
                <span>{{ t('maintenance.scenario.list.status') }}</span>
                <MaintenanceStatusTag
                  :status="fullVersion.version.status"
                />
              </article>
              <article>
                <span>{{ t('maintenance.scenario.fields.serviceLevel') }}</span>
                <strong>
                  {{ fullVersion.version.default_service_level }}
                </strong>
              </article>
              <article>
                <span>{{ t('maintenance.scenario.fields.executionMode') }}</span>
                <strong>{{ fullVersion.version.execution_mode }}</strong>
              </article>
              <article>
                <span>{{ t('maintenance.scenario.fields.missingPolicy') }}</span>
                <strong>
                  {{ fullVersion.version.missing_parameter_policy }}
                </strong>
              </article>
            </div>

            <form
              v-if="editing"
              class="scenario-detail__editor"
              @submit.prevent="saveVersion"
            >
              <label>
                <span>{{ t('maintenance.scenario.detail.versionName') }}</span>
                <input v-model="editForm.version_name" required>
              </label>
              <label>
                <span>{{ t('maintenance.scenario.fields.serviceLevel') }}</span>
                <input
                  v-model="editForm.default_service_level"
                  type="number"
                  min="0.01"
                  max="0.99"
                  step="0.01"
                  required
                >
              </label>
              <label>
                <span>{{ t('maintenance.scenario.fields.executionMode') }}</span>
                <select v-model="editForm.execution_mode">
                  <option value="AUTO">AUTO</option>
                  <option value="ANALYTICAL">ANALYTICAL</option>
                  <option value="MONTE_CARLO">MONTE_CARLO</option>
                  <option value="COMPARE">COMPARE</option>
                </select>
              </label>
              <label>
                <span>{{ t('maintenance.scenario.fields.missingPolicy') }}</span>
                <select v-model="editForm.missing_parameter_policy">
                  <option value="STRICT">STRICT</option>
                  <option value="WARN_AND_SKIP">WARN_AND_SKIP</option>
                  <option value="FALLBACK">FALLBACK</option>
                </select>
              </label>
              <label class="scenario-detail__editor-wide">
                <span>{{ t('maintenance.scenario.detail.description') }}</span>
                <textarea v-model="editForm.description" />
              </label>
              <button
                type="submit"
                :disabled="saving"
              >
                {{ t('maintenance.scenario.detail.save') }}
              </button>
            </form>

            <div class="scenario-detail__collections">
              <ScenarioRecordCollection
                :title="t('maintenance.scenario.detail.stages')"
                :records="fullVersion.stages"
                code-key="stage_code"
                name-key="stage_name"
              />
              <ScenarioRecordCollection
                :title="t('maintenance.scenario.detail.fleets')"
                :records="fullVersion.fleet_groups"
                code-key="group_code"
                name-key="group_name"
              />
              <ScenarioRecordCollection
                :title="t('maintenance.scenario.detail.overrides')"
                :records="fullVersion.overrides"
                code-key="spare_part_id"
                name-key="override_reason"
              />
            </div>
          </section>

          <section
            v-else
            class="scenario-detail__select-version"
          >
            <span>VERSION REGISTER</span>
            <h2>{{ t('maintenance.scenario.detail.selectVersion') }}</h2>
            <p>{{ t('maintenance.scenario.detail.selectVersionHint') }}</p>
          </section>
        </div>
      </template>
    </template>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  reactive,
  ref,
  watch,
} from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import {
  DialogPlugin,
  MessagePlugin,
} from 'tdesign-vue-next'
import {
  scenarioApi,
  type DemandExecutionMode,
  type MissingParameterPolicy,
  type ScenarioFullVersion,
  type ScenarioTemplate,
  type ScenarioVersionRecord,
} from '@/api/maintenance/scenarios'
import { normalizeMaintenanceError } from '@/api/maintenance/client'
import type { MaintenanceClientError } from '@/api/maintenance/types'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import ScenarioRecordCollection from '@/components/maintenance/scenario/ScenarioRecordCollection.vue'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const permissionStore = useMaintenancePermissionsStore()
const scenario = ref<ScenarioTemplate | null>(null)
const versions = ref<ScenarioVersionRecord[]>([])
const fullVersion = ref<ScenarioFullVersion | null>(
  null,
)
const loading = ref(false)
const saving = ref(false)
const editing = ref(false)
const error = ref<MaintenanceClientError | null>(null)
let loadGeneration = 0

const editForm = reactive<{
  version_name: string
  default_service_level: string
  execution_mode: DemandExecutionMode
  missing_parameter_policy: MissingParameterPolicy
  description: string
}>({
  version_name: '',
  default_service_level: '0.9',
  execution_mode: 'AUTO',
  missing_parameter_policy: 'WARN_AND_SKIP',
  description: '',
})

function positiveInteger(value: unknown): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  const parsed = Number(raw)
  return (
    Number.isInteger(parsed) && parsed > 0
      ? parsed
      : null
  )
}

const scenarioId = computed(
  () => positiveInteger(route.params.scenarioId),
)
const versionId = computed(
  () => (
    route.params.versionId === undefined
      ? null
      : positiveInteger(route.params.versionId)
  ),
)
const invalidRoute = computed(() => (
  scenarioId.value === null
  || (
    route.params.versionId !== undefined
    && versionId.value === null
  )
))
const canEditVersion = computed(() => (
  fullVersion.value?.version.status === 'DRAFT'
  && permissionStore.permissions.editMasterData
  && !permissionStore.permissions.publishRules
))
const canPublishVersion = computed(() => (
  fullVersion.value?.version.status === 'DRAFT'
  && permissionStore.permissions.confirmHighRisk
  && permissionStore.permissions.publishRules
))
const canRetireVersion = computed(() => (
  fullVersion.value?.version.status === 'PUBLISHED'
  && permissionStore.permissions.confirmHighRisk
  && permissionStore.permissions.publishRules
))

function syncEditForm(
  version: ScenarioVersionRecord,
): void {
  editForm.version_name = version.version_name
  editForm.default_service_level = (
    version.default_service_level
  )
  editForm.execution_mode = version.execution_mode
  editForm.missing_parameter_policy = (
    version.missing_parameter_policy
  )
  editForm.description = version.description ?? ''
}

async function load(): Promise<void> {
  const targetScenario = scenarioId.value
  const targetVersion = versionId.value
  const generation = ++loadGeneration
  if (targetScenario === null || invalidRoute.value) {
    scenario.value = null
    versions.value = []
    fullVersion.value = null
    return
  }
  loading.value = true
  error.value = null
  editing.value = false
  try {
    const [scenarioResult, versionsResult] = (
      await Promise.all([
        scenarioApi.getScenario(targetScenario),
        scenarioApi.listVersions(targetScenario),
      ])
    )
    const fullResult = targetVersion === null
      ? null
      : await scenarioApi.getFullVersion(
          targetVersion,
        )
    if (generation !== loadGeneration) return
    if (
      fullResult
      && fullResult.data.version
        .scenario_template_id !== targetScenario
    ) {
      throw new Error(
        'Scenario version does not belong to route scenario',
      )
    }
    scenario.value = scenarioResult.data
    versions.value = [...versionsResult.data].sort(
      (left, right) => right.id - left.id,
    )
    fullVersion.value = fullResult?.data ?? null
    if (fullVersion.value) {
      syncEditForm(fullVersion.value.version)
    }
  } catch (value) {
    if (generation === loadGeneration) {
      error.value = normalizeMaintenanceError(value)
    }
  } finally {
    if (generation === loadGeneration) {
      loading.value = false
    }
  }
}

async function saveVersion(): Promise<void> {
  const current = fullVersion.value?.version
  if (
    !current
    || !canEditVersion.value
    || saving.value
  ) {
    return
  }
  saving.value = true
  error.value = null
  try {
    await scenarioApi.updateVersion(
      current.id,
      {
        version_name: editForm.version_name,
        default_service_level: (
          editForm.default_service_level
        ),
        execution_mode: editForm.execution_mode,
        missing_parameter_policy: (
          editForm.missing_parameter_policy
        ),
        description: editForm.description || null,
      },
    )
    editing.value = false
    MessagePlugin.success(
      t('maintenance.scenario.detail.saved'),
    )
    await load()
  } catch (value) {
    error.value = normalizeMaintenanceError(value)
  } finally {
    saving.value = false
  }
}

function confirmLifecycle(
  action: 'publish' | 'retire',
): void {
  if (
    !permissionStore.permissions.confirmHighRisk
    || !permissionStore.permissions.publishRules
    || !fullVersion.value
  ) {
    return
  }
  const dialog = DialogPlugin.confirm({
    header: t(
      `maintenance.scenario.detail.${action}ConfirmTitle`,
    ),
    body: t(
      `maintenance.scenario.detail.${action}ConfirmBody`,
    ),
    confirmBtn: {
      content: t(
        `maintenance.scenario.detail.${action}`,
      ),
      theme: action === 'retire'
        ? 'danger'
        : 'primary',
    },
    cancelBtn: t('common.cancel'),
    theme: 'warning',
    onConfirm: async () => {
      try {
        saving.value = true
        const id = fullVersion.value?.version.id
        if (!id) return
        if (action === 'publish') {
          await scenarioApi.publishVersion(id)
        } else {
          await scenarioApi.retireVersion(id)
        }
        MessagePlugin.success(
          t(
            `maintenance.scenario.detail.${action}Success`,
          ),
        )
        await load()
      } catch (value) {
        error.value = normalizeMaintenanceError(
          value,
        )
      } finally {
        saving.value = false
        dialog.destroy()
      }
    },
    onClose: () => dialog.destroy(),
  })
}

function backToList(): void {
  void router.push({
    name: 'maintenanceScenarios',
  })
}

function openVersion(targetVersionId: number): void {
  if (scenarioId.value === null) return
  void router.push({
    name: 'maintenanceScenarioVersionDetail',
    params: {
      scenarioId: scenarioId.value,
      versionId: targetVersionId,
    },
  })
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(
        locale.value,
        {
          dateStyle: 'medium',
          timeStyle: 'short',
        },
      ).format(date)
}

watch(
  () => [
    route.params.scenarioId,
    route.params.versionId,
  ],
  () => {
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  loadGeneration += 1
})
</script>

<style scoped>
.scenario-detail {
  max-width: 1440px;
  margin: 0 auto;
  padding: 28px 32px 64px;
}

.scenario-detail__back {
  margin-bottom: 16px;
  padding: 7px 0;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.scenario-detail__hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 24px;
  padding: 24px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 10px;
  background:
    linear-gradient(120deg, color-mix(in srgb, var(--td-brand-color) 8%, transparent), transparent 48%),
    var(--td-bg-color-container);
}

.scenario-detail__hero > div > span,
.scenario-detail__version-header span,
.scenario-detail__select-version > span {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.12em;
}

.scenario-detail__hero h1 {
  margin: 7px 0 0;
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  font-size: 34px;
}

.scenario-detail__hero p {
  margin: 8px 0 0;
  color: var(--td-text-color-secondary);
}

.scenario-detail__hero dl {
  display: grid;
  grid-template-columns: repeat(3, auto);
  gap: 22px;
  margin: 0;
}

.scenario-detail__hero dl div {
  display: grid;
  gap: 4px;
}

.scenario-detail__hero dt,
.scenario-detail__facts span,
.scenario-detail__editor label span {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.scenario-detail__hero dd {
  margin: 0;
  font-size: 12px;
}

.scenario-detail__layout {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  align-items: start;
  gap: 18px;
  margin-top: 18px;
}

.scenario-detail__versions,
.scenario-detail__version,
.scenario-detail__select-version,
.scenario-detail__loading,
.scenario-detail__invalid {
  border: 1px solid var(--td-component-stroke);
  border-radius: 9px;
  background: var(--td-bg-color-container);
}

.scenario-detail__versions {
  display: grid;
  gap: 5px;
  padding: 12px;
}

.scenario-detail__versions header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 6px 10px;
}

.scenario-detail__versions h2 {
  margin: 0;
  font-size: 14px;
}

.scenario-detail__versions header span {
  color: var(--td-text-color-placeholder);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-detail__versions > button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.scenario-detail__versions > button:hover,
.scenario-detail__version--active {
  border-color: var(--td-brand-color) !important;
  background: color-mix(in srgb, var(--td-brand-color) 7%, transparent) !important;
}

.scenario-detail__versions button > span {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.scenario-detail__versions strong,
.scenario-detail__versions small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scenario-detail__versions strong {
  font-size: 12px;
}

.scenario-detail__versions small {
  color: var(--td-text-color-secondary);
  font-size: 10px;
}

.scenario-detail__version {
  padding: 24px;
}

.scenario-detail__version-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.scenario-detail__version-header h2 {
  margin: 6px 0 0;
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  font-size: 25px;
}

.scenario-detail__version-actions {
  display: flex;
  gap: 7px;
}

.scenario-detail__version-actions button,
.scenario-detail__editor button {
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.scenario-detail__version-actions .scenario-detail__publish {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.scenario-detail__version-actions .scenario-detail__retire {
  border-color: var(--td-error-color);
  color: var(--td-error-color);
}

.scenario-detail__facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin-top: 20px;
  overflow: hidden;
  border: 1px solid var(--td-component-stroke);
  border-radius: 7px;
  background: var(--td-component-stroke);
}

.scenario-detail__facts article {
  display: grid;
  min-height: 78px;
  align-content: space-between;
  gap: 8px;
  padding: 13px;
  background: var(--td-bg-color-container);
}

.scenario-detail__facts strong {
  font-size: 13px;
}

.scenario-detail__editor {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
  padding: 16px;
  border-left: 3px solid var(--td-brand-color);
  background: var(--td-bg-color-secondarycontainer);
}

.scenario-detail__editor label {
  display: grid;
  gap: 5px;
}

.scenario-detail__editor input,
.scenario-detail__editor select,
.scenario-detail__editor textarea {
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--td-component-border);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.scenario-detail__editor textarea {
  min-height: 74px;
  resize: vertical;
}

.scenario-detail__editor-wide {
  grid-column: 1 / -1;
}

.scenario-detail__editor button {
  justify-self: start;
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.scenario-detail__collections {
  display: grid;
  gap: 12px;
  margin-top: 18px;
}

.scenario-detail__select-version,
.scenario-detail__loading,
.scenario-detail__invalid {
  display: grid;
  min-height: 280px;
  align-content: center;
  justify-items: center;
  padding: 24px;
  text-align: center;
}

.scenario-detail__select-version h2,
.scenario-detail__select-version p {
  margin: 0;
}

.scenario-detail__select-version h2 {
  margin-top: 8px;
}

.scenario-detail__select-version p {
  max-width: 440px;
  margin-top: 7px;
  color: var(--td-text-color-secondary);
}

@media (max-width: 980px) {
  .scenario-detail__hero,
  .scenario-detail__layout {
    grid-template-columns: 1fr;
  }

  .scenario-detail__hero dl {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .scenario-detail {
    padding: 20px 16px 48px;
  }

  .scenario-detail__hero dl,
  .scenario-detail__facts,
  .scenario-detail__editor {
    grid-template-columns: 1fr;
  }

  .scenario-detail__version-header {
    flex-direction: column;
  }

  .scenario-detail__editor-wide {
    grid-column: auto;
  }
}
</style>
