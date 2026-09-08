import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getDashboardSummary,
  type DashboardSummary,
} from '../../api/maintenance/dashboard'
import { normalizeMaintenanceError } from '../../api/maintenance/client'
import type {
  MaintenanceClientError,
  MaintenanceResult,
} from '../../api/maintenance/types'

export type DashboardFetcher = (
) => Promise<MaintenanceResult<DashboardSummary>>

export function createDashboardState(
  fetchSummary: DashboardFetcher = getDashboardSummary,
) {
  const summary = ref<DashboardSummary | null>(null)
  const loading = ref(false)
  const error = ref<MaintenanceClientError | null>(null)

  async function refresh(): Promise<void> {
    if (loading.value) {
      return
    }

    loading.value = true

    try {
      const result = await fetchSummary()
      summary.value = result.data
      error.value = null
    } catch (value) {
      error.value = normalizeMaintenanceError(value)
    } finally {
      loading.value = false
    }
  }

  return {
    summary,
    loading,
    error,
    refresh,
  }
}

export const useMaintenanceDashboardStore = defineStore(
  'maintenanceDashboard',
  () => createDashboardState(),
)
