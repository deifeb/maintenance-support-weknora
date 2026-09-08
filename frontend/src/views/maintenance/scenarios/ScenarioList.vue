<template>
  <section class="scenario-list">
    <MaintenancePageHeader
      :title="t('maintenance.pages.scenarios')"
      :description="t('maintenance.scenario.list.description')"
    >
      <template #secondaryActions>
        <button
          type="button"
          class="scenario-list__secondary"
          :disabled="loading"
          @click="refresh"
        >
          {{ t('maintenance.scenario.list.refresh') }}
        </button>
      </template>
      <template #primaryActions>
        <button
          v-if="canCreate"
          type="button"
          class="scenario-list__primary"
          @click="createScenario"
        >
          {{ t('maintenance.scenario.list.create') }}
        </button>
      </template>
    </MaintenancePageHeader>

    <form
      class="scenario-list__toolbar"
      @submit.prevent="setKeyword(searchDraft)"
    >
      <label>
        <span>{{ t('maintenance.scenario.list.search') }}</span>
        <input
          v-model="searchDraft"
          type="search"
          :placeholder="t('maintenance.scenario.list.searchPlaceholder')"
        >
      </label>
      <button type="submit">
        {{ t('maintenance.scenario.list.apply') }}
      </button>
      <label class="scenario-list__inactive">
        <input
          type="checkbox"
          :checked="includeInactive"
          @change="setIncludeInactive(($event.target as HTMLInputElement).checked)"
        >
        {{ t('maintenance.scenario.list.includeInactive') }}
      </label>
      <span class="scenario-list__count">
        {{ total }} {{ t('maintenance.scenario.list.records') }}
      </span>
    </form>

    <MaintenanceErrorState
      v-if="error"
      :error="error"
      @retry="refresh"
    />

    <div
      v-if="loading && rows.length === 0"
      class="scenario-list__loading"
    >
      {{ t('maintenance.scenario.loading') }}
    </div>

    <MaintenanceEmptyState
      v-else-if="rows.length === 0"
      :title="t('maintenance.scenario.list.emptyTitle')"
      :description="t('maintenance.scenario.list.emptyDescription')"
    />

    <div
      v-else
      class="scenario-list__table-wrap"
      :aria-busy="loading"
    >
      <table class="scenario-list__table">
        <thead>
          <tr>
            <th>
              <button type="button" @click="setSort('code')">
                {{ t('maintenance.scenario.list.code') }}
              </button>
            </th>
            <th>
              <button type="button" @click="setSort('name')">
                {{ t('maintenance.scenario.list.name') }}
              </button>
            </th>
            <th>{{ t('maintenance.scenario.list.category') }}</th>
            <th>{{ t('maintenance.scenario.list.currentVersion') }}</th>
            <th>{{ t('maintenance.scenario.list.status') }}</th>
            <th>
              <button type="button" @click="setSort('updated_at')">
                {{ t('maintenance.scenario.list.updatedAt') }}
              </button>
            </th>
            <th>{{ t('maintenance.scenario.list.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
          >
            <td>
              <code>{{ row.code }}</code>
            </td>
            <td>
              <strong>{{ row.name }}</strong>
              <small>{{ row.description || '—' }}</small>
            </td>
            <td>{{ row.category || '—' }}</td>
            <td>
              {{
                row.currentVersion?.version_code
                ?? '—'
              }}
            </td>
            <td>
              <MaintenanceStatusTag
                v-if="row.currentVersion"
                :status="row.currentVersion.status"
              />
              <span v-else>—</span>
            </td>
            <td>{{ formatDate(row.updated_at) }}</td>
            <td>
              <div class="scenario-list__actions">
                <button
                  type="button"
                  @click="openScenario(row.id)"
                >
                  {{ t('maintenance.scenario.list.view') }}
                </button>
                <button
                  v-if="
                    canEdit
                    && row.currentVersion?.status === 'DRAFT'
                  "
                  type="button"
                  @click="openVersion(row.id, row.currentVersion.id)"
                >
                  {{ t('maintenance.scenario.list.editDraft') }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer
      v-if="pages > 0"
      class="scenario-list__pagination"
    >
      <button
        type="button"
        :disabled="page <= 1 || loading"
        @click="setPage(page - 1)"
      >
        {{ t('maintenance.scenario.actions.previous') }}
      </button>
      <span>{{ page }} / {{ pages }}</span>
      <button
        type="button"
        :disabled="page >= pages || loading"
        @click="setPage(page + 1)"
      >
        {{ t('maintenance.scenario.actions.next') }}
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onMounted,
  ref,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  scenarioApi,
  type ScenarioTemplate,
  type ScenarioVersionRecord,
} from '@/api/maintenance/scenarios'
import MaintenanceEmptyState from '@/components/maintenance/common/MaintenanceEmptyState.vue'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import { createServerTableState } from '@/composables/maintenance/useServerTable'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

interface ScenarioListRow extends ScenarioTemplate {
  currentVersion: ScenarioVersionRecord | null
}

const { t, locale } = useI18n()
const router = useRouter()
const permissionStore = useMaintenancePermissionsStore()
const searchDraft = ref('')

const table = createServerTableState<ScenarioListRow>({
  initialSortBy: 'updated_at',
  initialSortOrder: 'desc',
  async fetchPage(query) {
    const response = await scenarioApi.listScenarios(
      query,
    )
    const versions = await Promise.all(
      response.data.items.map((item) => (
        scenarioApi.listVersions(item.id)
      )),
    )
    return {
      ...response.data,
      items: response.data.items.map(
        (item, index) => {
          const rows = versions[index]?.data ?? []
          const currentVersion = [...rows].sort(
            (left, right) => right.id - left.id,
          )[0] ?? null
          return {
            ...item,
            currentVersion,
          }
        },
      ),
    }
  },
})

const {
  rows,
  page,
  total,
  pages,
  includeInactive,
  loading,
  error,
  refresh,
  setKeyword,
  setPage,
  setSort,
  setIncludeInactive,
} = table

const canCreate = computed(
  () => permissionStore.permissions.editMasterData,
)
const canEdit = canCreate

function createScenario(): void {
  void router.push({
    name: 'maintenanceScenarioNew',
  })
}

function openScenario(scenarioId: number): void {
  void router.push({
    name: 'maintenanceScenarioDetail',
    params: { scenarioId },
  })
}

function openVersion(
  scenarioId: number,
  versionId: number,
): void {
  void router.push({
    name: 'maintenanceScenarioVersionDetail',
    params: {
      scenarioId,
      versionId,
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

onMounted(() => {
  void refresh()
})
</script>

<style scoped>
.scenario-list {
  max-width: 1440px;
  margin: 0 auto;
  padding: 32px;
}

.scenario-list__primary,
.scenario-list__secondary,
.scenario-list__toolbar button,
.scenario-list__pagination button {
  min-height: 38px;
  padding: 0 15px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
  cursor: pointer;
}

.scenario-list__primary {
  border-color: var(--td-brand-color);
  background: var(--td-brand-color);
  color: var(--td-text-color-anti);
}

.scenario-list__toolbar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.scenario-list__toolbar > label:first-child {
  display: grid;
  flex: 1;
  gap: 5px;
}

.scenario-list__toolbar label span {
  color: var(--td-text-color-secondary);
  font-size: 11px;
}

.scenario-list__toolbar input[type="search"] {
  min-height: 38px;
  padding: 8px 10px;
  border: 1px solid var(--td-component-border);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.scenario-list__inactive {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 38px;
  color: var(--td-text-color-secondary);
  font-size: 12px;
}

.scenario-list__count {
  margin-left: auto;
  color: var(--td-text-color-placeholder);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-list__table-wrap {
  overflow-x: auto;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.scenario-list__table {
  width: 100%;
  border-collapse: collapse;
}

.scenario-list__table th,
.scenario-list__table td {
  padding: 13px 14px;
  border-bottom: 1px solid var(--td-component-stroke);
  color: var(--td-text-color-secondary);
  font-size: 12px;
  text-align: left;
  vertical-align: middle;
}

.scenario-list__table th {
  background: var(--td-bg-color-secondarycontainer);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.scenario-list__table th button {
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.scenario-list__table tbody tr:hover {
  background: color-mix(in srgb, var(--td-brand-color) 4%, transparent);
}

.scenario-list__table td strong,
.scenario-list__table td small {
  display: block;
}

.scenario-list__table td strong {
  color: var(--td-text-color-primary);
  font-size: 13px;
}

.scenario-list__table td small {
  max-width: 300px;
  margin-top: 3px;
  overflow: hidden;
  color: var(--td-text-color-placeholder);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scenario-list__table code {
  color: var(--td-brand-color);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
}

.scenario-list__actions {
  display: flex;
  gap: 6px;
}

.scenario-list__actions button {
  padding: 4px 8px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 4px;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}

.scenario-list__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 18px;
}

.scenario-list__pagination span {
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 11px;
}

.scenario-list__loading {
  display: grid;
  min-height: 260px;
  place-items: center;
  color: var(--td-text-color-secondary);
}

@media (max-width: 760px) {
  .scenario-list {
    padding: 22px 16px;
  }

  .scenario-list__toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .scenario-list__count {
    margin-left: 0;
  }
}
</style>
