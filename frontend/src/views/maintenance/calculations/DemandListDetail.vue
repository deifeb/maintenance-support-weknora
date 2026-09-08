<template>
  <main class="demand-list-detail">
    <button
      type="button"
      class="demand-list-detail__back"
      @click="back"
    >
      ← {{
        t(
          'maintenance.calculation.demandList.detail.back',
        )
      }}
    </button>

    <section
      v-if="invalidRoute"
      class="demand-list-detail__invalid"
      role="alert"
    >
      <h1>
        {{
          t(
            'maintenance.calculation.demandList.errors.invalidRoute',
          )
        }}
      </h1>
    </section>

    <template v-else>
      <MaintenanceErrorState
        v-if="error"
        :error="error"
        :locale="locale"
        @retry="load"
      />

      <div
        v-if="loading && !current"
        class="demand-list-detail__loading"
      >
        {{
          t(
            'maintenance.calculation.demandList.detail.loading',
          )
        }}
      </div>

      <template v-if="current">
        <MaintenancePageHeader
          :title="current.name"
          :description="current.description || '—'"
        >
          <template #secondaryActions>
            <MaintenanceStatusTag :status="current.status" />
          </template>
          <template #primaryActions>
            <DemandListLifecycleActions
              :status="current.status"
              :permissions="permissionStore.permissions"
              :busy="mutating"
              @select="selectLifecycleAction"
            />
          </template>
        </MaintenancePageHeader>

        <section class="demand-list-detail__facts">
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.listId',
                )
              }}
            </span>
            <strong>#{{ current.id }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.versionNumber',
                )
              }}
            </span>
            <strong>{{ current.version_number }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.optimisticVersion',
                )
              }}
            </span>
            <strong>{{ current.version }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.lineage',
                )
              }}
            </span>
            <strong>{{ current.lineage_id }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.scenarioVersion',
                )
              }}
            </span>
            <strong>#{{ current.scenario_version_id }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.calculationGroup',
                )
              }}
            </span>
            <button
              type="button"
              @click="openComparison"
            >
              #{{ current.calculation_group_id }}
            </button>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.currentPublished',
                )
              }}
            </span>
            <strong>
              {{
                current.is_current
                  ? t('common.yes')
                  : t('common.no')
              }}
            </strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.createdBy',
                )
              }}
            </span>
            <strong>{{ current.created_by_user_id }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.createdAt',
                )
              }}
            </span>
            <strong>{{ formatDate(current.created_at) }}</strong>
          </article>
          <article>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.detail.updatedAt',
                )
              }}
            </span>
            <strong>{{ formatDate(current.updated_at) }}</strong>
          </article>
        </section>

        <section
          v-if="(
            current.derived_from_id
            || current.superseded_by_id
          )"
          class="demand-list-detail__lineage-links"
        >
          <button
            v-if="current.derived_from_id"
            type="button"
            @click="openDemandList(current.derived_from_id)"
          >
            {{
              t(
                'maintenance.calculation.demandList.detail.openDerivedFrom',
                { id: current.derived_from_id },
              )
            }}
          </button>
          <button
            v-if="current.superseded_by_id"
            type="button"
            @click="openDemandList(current.superseded_by_id)"
          >
            {{
              t(
                'maintenance.calculation.demandList.detail.openSupersededBy',
                { id: current.superseded_by_id },
              )
            }}
          </button>
        </section>

        <section class="demand-list-detail__lifecycle">
          <header>
            <h2>
              {{
                t(
                  'maintenance.calculation.demandList.detail.lifecycle',
                )
              }}
            </h2>
            <button
              type="button"
              @click="focusItems"
            >
              {{
                t(
                  'maintenance.calculation.demandList.items.title',
                )
              }}
            </button>
          </header>
          <ol>
            <li
              v-for="status in lifecycleStatuses"
              :key="status"
              :class="{
                'demand-list-detail__lifecycle--reached': (
                  statusReached(status)
                ),
                'demand-list-detail__lifecycle--current': (
                  current.status === status
                ),
              }"
            >
              {{
                t(
                  `maintenance.calculation.demandList.status.${status}`,
                )
              }}
            </li>
          </ol>
        </section>

        <section
          ref="itemTable"
          class="demand-list-detail__items"
        >
          <header>
            <div>
              <h2>
                {{
                  t(
                    'maintenance.calculation.demandList.items.title',
                  )
                }}
              </h2>
              <p>
                {{
                  t(
                    'maintenance.calculation.demandList.items.description',
                  )
                }}
              </p>
            </div>
            <span>{{ current.items.length }}</span>
          </header>

          <div class="demand-list-detail__table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.part',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.unit',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.criticality',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.model',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.mode',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.original',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.final',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.decision',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.risk',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.confirmed',
                      )
                    }}
                  </th>
                  <th>
                    {{
                      t(
                        'maintenance.calculation.demandList.items.actions',
                      )
                    }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in current.items"
                  :key="item.id"
                >
                  <td>
                    <strong>
                      {{ item.spare_part_code_snapshot }}
                    </strong>
                    <span>
                      {{ item.spare_part_name_snapshot }}
                    </span>
                  </td>
                  <td>{{ item.spare_part_unit_snapshot }}</td>
                  <td>
                    {{ item.criticality_level_snapshot || '—' }}
                  </td>
                  <td>{{ item.reliability_model || '—' }}</td>
                  <td>{{ item.execution_mode || '—' }}</td>
                  <td>{{ item.original_quantity }}</td>
                  <td>{{ item.final_quantity }}</td>
                  <td>{{ item.decision_type || '—' }}</td>
                  <td>{{ item.decision_risk || '—' }}</td>
                  <td>
                    {{
                      item.confirmed_by_admin
                        ? t('common.yes')
                        : t('common.no')
                    }}
                  </td>
                  <td>
                    <button
                      v-if="canEditItems"
                      type="button"
                      :disabled="mutating"
                      @click="openItemEditor(item)"
                    >
                      {{
                        t(
                          'maintenance.calculation.demandList.actions.edit',
                        )
                      }}
                    </button>
                    <span v-else>—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="demand-list-detail__timeline">
          <header>
            <h2>
              {{
                t(
                  'maintenance.calculation.demandList.timeline.title',
                )
              }}
            </h2>
          </header>

          <ol v-if="current.events.length">
            <li
              v-for="event in current.events"
              :key="event.id"
            >
              <header>
                <strong>
                  {{
                    t(
                      `maintenance.calculation.demandList.timeline.events.${event.event_type}`,
                    )
                  }}
                </strong>
                <time>{{ formatDate(event.occurred_at) }}</time>
              </header>
              <dl>
                <div>
                  <dt>
                    {{
                      t(
                        'maintenance.calculation.demandList.timeline.actor',
                      )
                    }}
                  </dt>
                  <dd>{{ event.actor_user_id }}</dd>
                </div>
                <div>
                  <dt>
                    {{
                      t(
                        'maintenance.calculation.demandList.timeline.roles',
                      )
                    }}
                  </dt>
                  <dd>{{ event.actor_roles_json.join(', ') }}</dd>
                </div>
                <div>
                  <dt>
                    {{
                      t(
                        'maintenance.calculation.demandList.timeline.request',
                      )
                    }}
                  </dt>
                  <dd>{{ event.request_id }}</dd>
                </div>
                <div v-if="event.idempotency_key">
                  <dt>
                    {{
                      t(
                        'maintenance.calculation.demandList.timeline.idempotency',
                      )
                    }}
                  </dt>
                  <dd>{{ event.idempotency_key }}</dd>
                </div>
              </dl>
              <details
                v-if="(
                  event.before_summary_json
                  || event.after_summary_json
                )"
              >
                <summary>
                  {{
                    t(
                      'maintenance.calculation.demandList.timeline.details',
                    )
                  }}
                </summary>
                <pre v-if="event.before_summary_json">{{
                  JSON.stringify(
                    event.before_summary_json,
                    null,
                    2,
                  )
                }}</pre>
                <pre v-if="event.after_summary_json">{{
                  JSON.stringify(
                    event.after_summary_json,
                    null,
                    2,
                  )
                }}</pre>
              </details>
            </li>
          </ol>

          <p v-else>
            {{
              t(
                'maintenance.calculation.demandList.timeline.empty',
              )
            }}
          </p>
        </section>
      </template>
    </template>

    <div
      v-if="selectedItem"
      class="demand-list-detail__dialog-backdrop"
    >
      <section
        class="demand-list-detail__dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="
          t(
            'maintenance.calculation.demandList.items.editTitle',
          )
        "
      >
        <header>
          <div>
            <span>
              {{ selectedItem.spare_part_code_snapshot }}
            </span>
            <h2>
              {{ selectedItem.spare_part_name_snapshot }}
            </h2>
          </div>
          <button
            type="button"
            :disabled="mutating"
            @click="closeItemEditor"
          >
            ×
          </button>
        </header>

        <dl>
          <div>
            <dt>
              {{
                t(
                  'maintenance.calculation.demandList.items.original',
                )
              }}
            </dt>
            <dd>{{ selectedItem.original_quantity }}</dd>
          </div>
          <div>
            <dt>
              {{
                t(
                  'maintenance.calculation.demandList.items.currentFinal',
                )
              }}
            </dt>
            <dd>{{ selectedItem.final_quantity }}</dd>
          </div>
        </dl>

        <label>
          <span>
            {{
              t(
                'maintenance.calculation.demandList.items.newFinal',
              )
            }}
          </span>
          <input
            v-model="editQuantity"
            type="text"
            inputmode="decimal"
            autocomplete="off"
          >
        </label>

        <label>
          <span>
            {{
              t(
                'maintenance.calculation.demandList.items.reason',
              )
            }}
          </span>
          <textarea
            v-model="editReason"
            maxlength="1000"
          />
        </label>

        <footer>
          <button
            type="button"
            :disabled="mutating"
            @click="closeItemEditor"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            :disabled="(
              mutating
              || !editQuantity.trim()
              || !editReason.trim()
            )"
            @click="saveItem"
          >
            {{
              mutating
                ? t(
                    'maintenance.calculation.demandList.items.saving',
                  )
                : t(
                    'maintenance.calculation.demandList.items.save',
                  )
            }}
          </button>
        </footer>
      </section>
    </div>

    <div
      v-if="confirmationNoteOpen"
      class="demand-list-detail__dialog-backdrop"
    >
      <section
        class="demand-list-detail__dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="
          t(
            'maintenance.calculation.demandList.dialogs.confirmTitle',
          )
        "
      >
        <header>
          <div>
            <span>
              {{
                t(
                  'maintenance.calculation.demandList.dialogs.confirmEyebrow',
                )
              }}
            </span>
            <h2>
              {{
                t(
                  'maintenance.calculation.demandList.dialogs.confirmTitle',
                )
              }}
            </h2>
          </div>
        </header>

        <p>
          {{
            t(
              'maintenance.calculation.demandList.dialogs.confirmBody',
            )
          }}
        </p>

        <label>
          <span>
            {{
              t(
                'maintenance.calculation.demandList.dialogs.confirmationNote',
              )
            }}
          </span>
          <textarea
            v-model="confirmationNote"
            maxlength="1000"
          />
        </label>

        <footer>
          <button
            type="button"
            :disabled="mutating"
            @click="closeConfirmationNote"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            :disabled="(
              mutating
              || !confirmationNote.trim()
            )"
            @click="submitConfirmationNote"
          >
            {{
              t(
                'maintenance.calculation.demandList.actions.confirm',
              )
            }}
          </button>
        </footer>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import {
  useRoute,
  useRouter,
} from 'vue-router'
import {
  DialogPlugin,
  MessagePlugin,
} from 'tdesign-vue-next'

import type {
  DemandListItem,
  DemandListStatus,
} from '@/api/maintenance/demand-lists'
import DemandListLifecycleActions from '@/components/maintenance/calculation/DemandListLifecycleActions.vue'
import {
  canEditDemandListItem,
  type DemandListAction,
} from '@/components/maintenance/calculation/demand-list-lifecycle'
import MaintenanceErrorState from '@/components/maintenance/common/MaintenanceErrorState.vue'
import MaintenancePageHeader from '@/components/maintenance/common/MaintenancePageHeader.vue'
import MaintenanceStatusTag from '@/components/maintenance/common/MaintenanceStatusTag.vue'
import { useDemandListStore } from '@/stores/maintenance/demandList'
import { useMaintenancePermissionsStore } from '@/stores/maintenance/permissions'

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const store = useDemandListStore()
const permissionStore = useMaintenancePermissionsStore()

const {
  current,
  loading,
  mutating,
  error,
} = storeToRefs(store)

const selectedItem = ref<DemandListItem | null>(null)
const editQuantity = ref('')
const editReason = ref('')
const confirmationNoteOpen = ref(false)
const confirmationNote = ref('')
const itemTable = ref<HTMLElement | null>(null)

const lifecycleStatuses = [
  'DRAFT',
  'PENDING_CONFIRMATION',
  'CONFIRMED',
  'PUBLISHED',
  'VOIDED',
] as const satisfies readonly DemandListStatus[]

function positiveInteger(
  value: unknown,
): number | null {
  const raw = Array.isArray(value)
    ? value[0]
    : value
  const parsed = Number(raw)

  return (
    Number.isInteger(parsed)
    && parsed > 0
      ? parsed
      : null
  )
}

const listId = computed(() => (
  positiveInteger(route.params.listId)
))

const invalidRoute = computed(() => (
  listId.value === null
))

const canEditItems = computed(() => (
  current.value !== null
  && canEditDemandListItem(
    current.value.status,
    permissionStore.permissions,
  )
))

function statusReached(
  status: DemandListStatus,
): boolean {
  const currentIndex = lifecycleStatuses.indexOf(
    current.value?.status ?? 'DRAFT',
  )
  const targetIndex = lifecycleStatuses.indexOf(status)

  return targetIndex <= currentIndex
}

async function load(): Promise<void> {
  const targetId = listId.value

  if (targetId === null) {
    store.dispose()
    return
  }

  try {
    await store.load(targetId)
  } catch {
    // The Task 5 store retains normalized error state.
  }
}

function back(): void {
  if (current.value) {
    void router.push({
      name: 'maintenanceCalculationComparison',
      params: {
        groupId: current.value.calculation_group_id,
      },
    })
    return
  }

  void router.push({
    name: 'maintenanceCalculations',
  })
}

function openDemandList(
  demandListId: number,
): void {
  void router.push({
    name: 'maintenanceDemandListDetail',
    params: {
      listId: demandListId,
    },
  })
}

function openComparison(): void {
  if (!current.value) return

  void router.push({
    name: 'maintenanceCalculationComparison',
    params: {
      groupId: current.value.calculation_group_id,
    },
  })
}

function openItemEditor(
  item: DemandListItem,
): void {
  if (!canEditItems.value || mutating.value) {
    return
  }

  selectedItem.value = item
  editQuantity.value = item.final_quantity
  editReason.value = ''
}

function closeItemEditor(): void {
  selectedItem.value = null
  editQuantity.value = ''
  editReason.value = ''
}

async function saveItem(): Promise<void> {
  if (
    selectedItem.value === null
    || !canEditItems.value
    || mutating.value
  ) {
    return
  }

  const quantity = editQuantity.value.trim()
  const reason = editReason.value.trim()

  if (!quantity || !reason) {
    return
  }

  try {
    await store.updateItem(
      selectedItem.value.id,
      quantity,
      reason,
    )
    closeItemEditor()
    MessagePlugin.success(
      t(
        'maintenance.calculation.demandList.items.saved',
      ),
    )
  } catch {
    // Preserve editor values and the last successful aggregate.
  }
}

type ConfirmableLifecycleAction =
  | 'submit'
  | 'publish'
  | 'derive'
  | 'void'

async function runLifecycle(
  action: ConfirmableLifecycleAction,
): Promise<void> {
  try {
    if (action === 'submit') {
      await store.submit()
    } else if (action === 'publish') {
      await store.publish()
    } else if (action === 'derive') {
      const derived = await store.derive()
      await router.push({
        name: 'maintenanceDemandListDetail',
        params: { listId: derived.id },
      })
    } else {
      await store.voidList()
    }

    MessagePlugin.success(
      t(
        `maintenance.calculation.demandList.actions.${action}Success`,
      ),
    )
  } catch {
    // The store preserves the aggregate and normalized error.
  }
}

function confirmLifecycle(
  action: Exclude<DemandListAction, 'edit' | 'confirm'>,
): void {
  const dialog = DialogPlugin.confirm({
    header: t(
      `maintenance.calculation.demandList.dialogs.${action}Title`,
    ),
    body: t(
      `maintenance.calculation.demandList.dialogs.${action}Body`,
    ),
    confirmBtn: {
      content: t(
        `maintenance.calculation.demandList.actions.${action}`,
      ),
      theme: action === 'void'
        ? 'danger'
        : 'primary',
    },
    cancelBtn: t('common.cancel'),
    theme: 'warning',
    onConfirm: async () => {
      try {
        await runLifecycle(action)
      } finally {
        dialog.destroy()
      }
    },
    onClose: () => dialog.destroy(),
  })
}

function selectLifecycleAction(
  action: DemandListAction,
): void {
  if (mutating.value) return

  if (action === 'edit') {
    void focusItems()
    return
  }

  if (action === 'confirm') {
    confirmationNote.value = ''
    confirmationNoteOpen.value = true
    return
  }

  confirmLifecycle(action)
}

function closeConfirmationNote(): void {
  if (mutating.value) return
  confirmationNoteOpen.value = false
  confirmationNote.value = ''
}

async function submitConfirmationNote(): Promise<void> {
  const note = confirmationNote.value.trim()

  if (!note || mutating.value) {
    return
  }

  try {
    await store.confirm(note)
    confirmationNoteOpen.value = false
    confirmationNote.value = ''
    MessagePlugin.success(
      t(
        'maintenance.calculation.demandList.actions.confirmSuccess',
      ),
    )
  } catch {
    // Preserve the entered note on failure.
  }
}

async function focusItems(): Promise<void> {
  await nextTick()
  itemTable.value?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function formatDate(
  value: string,
): string {
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
  () => route.params.listId,
  () => {
    closeItemEditor()
    closeConfirmationNote()
    void load()
  },
  { immediate: true },
)

onBeforeUnmount(store.dispose)
</script>

<style scoped>
.demand-list-detail {
  max-width: 1480px;
  margin: 0 auto;
  padding: 32px;
}

.demand-list-detail__back {
  min-height: 36px;
  margin-bottom: 18px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.demand-list-detail__invalid,
.demand-list-detail__loading {
  display: grid;
  min-height: 260px;
  place-items: center;
  color: var(--td-text-color-secondary);
}

.demand-list-detail__invalid {
  color: var(--td-error-color);
}

.demand-list-detail__facts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin: 20px 0;
}

.demand-list-detail__facts article {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 7px;
  background: var(--td-bg-color-container);
}

.demand-list-detail__facts span,
.demand-list-detail__facts strong {
  display: block;
}

.demand-list-detail__facts span {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  text-transform: uppercase;
}

.demand-list-detail__facts strong,
.demand-list-detail__facts button {
  margin-top: 7px;
  overflow-wrap: anywhere;
  color: var(--td-text-color-primary);
  font-family: "Roboto Mono", "Noto Sans Mono", monospace;
  font-size: 12px;
}

.demand-list-detail__facts button,
.demand-list-detail__lineage-links button,
.demand-list-detail__lifecycle header button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.demand-list-detail__lineage-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
}

.demand-list-detail__lifecycle,
.demand-list-detail__items,
.demand-list-detail__timeline {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 8px;
  background: var(--td-bg-color-container);
}

.demand-list-detail__lifecycle > header,
.demand-list-detail__items > header,
.demand-list-detail__timeline > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.demand-list-detail__lifecycle h2,
.demand-list-detail__items h2,
.demand-list-detail__timeline h2 {
  margin: 0;
  color: var(--td-text-color-primary);
}

.demand-list-detail__lifecycle ol {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
}

.demand-list-detail__lifecycle li {
  min-height: 42px;
  padding: 10px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 6px;
  color: var(--td-text-color-placeholder);
  text-align: center;
}

.demand-list-detail__lifecycle--reached {
  color: var(--td-text-color-primary) !important;
}

.demand-list-detail__lifecycle--current {
  border-color: var(--td-brand-color) !important;
  background: var(--td-brand-color-light);
  color: var(--td-brand-color) !important;
  font-weight: 600;
}

.demand-list-detail__items > header p {
  margin: 6px 0 0;
  color: var(--td-text-color-secondary);
}

.demand-list-detail__items > header > span {
  min-width: 34px;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--td-bg-color-secondarycontainer);
  text-align: center;
}

.demand-list-detail__table-wrap {
  margin-top: 16px;
  overflow-x: auto;
}

.demand-list-detail__items table {
  width: 100%;
  min-width: 1220px;
  border-collapse: collapse;
}

.demand-list-detail__items th,
.demand-list-detail__items td {
  padding: 12px;
  border-bottom: 1px solid var(--td-component-stroke);
  text-align: left;
  vertical-align: top;
}

.demand-list-detail__items th {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  text-transform: uppercase;
}

.demand-list-detail__items td {
  color: var(--td-text-color-secondary);
}

.demand-list-detail__items td strong,
.demand-list-detail__items td span {
  display: block;
}

.demand-list-detail__items td strong {
  color: var(--td-text-color-primary);
}

.demand-list-detail__items td button,
.demand-list-detail__dialog button {
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-brand-color);
  font: inherit;
  cursor: pointer;
}

.demand-list-detail button:focus-visible,
.demand-list-detail input:focus-visible,
.demand-list-detail textarea:focus-visible {
  outline: 2px solid var(--td-brand-color);
  outline-offset: 2px;
}

.demand-list-detail button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.demand-list-detail__timeline > ol {
  display: grid;
  gap: 12px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.demand-list-detail__timeline > ol > li {
  padding: 14px;
  border-left: 3px solid var(--td-brand-color);
  background: var(--td-bg-color-secondarycontainer);
}

.demand-list-detail__timeline li > header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
}

.demand-list-detail__timeline time {
  color: var(--td-text-color-placeholder);
}

.demand-list-detail__timeline dl,
.demand-list-detail__dialog dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.demand-list-detail__timeline dt,
.demand-list-detail__dialog dt {
  color: var(--td-text-color-placeholder);
  font-size: 10px;
  text-transform: uppercase;
}

.demand-list-detail__timeline dd,
.demand-list-detail__dialog dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}

.demand-list-detail__timeline pre {
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  background: var(--td-bg-color-page);
  font-size: 11px;
}

.demand-list-detail__dialog-backdrop {
  position: fixed;
  z-index: 1200;
  inset: 0;
  display: grid;
  padding: 20px;
  background: rgb(0 0 0 / 45%);
  place-items: center;
}

.demand-list-detail__dialog {
  width: min(620px, 100%);
  max-height: calc(100vh - 40px);
  overflow: auto;
  padding: 20px;
  border-radius: 9px;
  background: var(--td-bg-color-container);
  box-shadow: var(--td-shadow-3);
}

.demand-list-detail__dialog > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.demand-list-detail__dialog h2 {
  margin: 5px 0 0;
}

.demand-list-detail__dialog > p {
  color: var(--td-text-color-secondary);
  line-height: 1.6;
}

.demand-list-detail__dialog label {
  display: grid;
  gap: 7px;
  margin-top: 16px;
}

.demand-list-detail__dialog input,
.demand-list-detail__dialog textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 9px;
  border: 1px solid var(--td-component-stroke);
  border-radius: 5px;
  background: var(--td-bg-color-container);
  color: var(--td-text-color-primary);
  font: inherit;
}

.demand-list-detail__dialog textarea {
  min-height: 100px;
  resize: vertical;
}

.demand-list-detail__dialog footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

@media (max-width: 980px) {
  .demand-list-detail__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .demand-list-detail {
    padding: 22px 16px;
  }

  .demand-list-detail__facts,
  .demand-list-detail__lifecycle ol,
  .demand-list-detail__timeline dl,
  .demand-list-detail__dialog dl {
    grid-template-columns: 1fr;
  }

  .demand-list-detail__dialog footer {
    display: grid;
  }

  .demand-list-detail__dialog footer button {
    width: 100%;
  }
}
</style>
