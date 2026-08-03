import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  permissionsForAuth,
  type MaintenanceAction,
} from './permission-matrix'

export {
  isTenantRole,
  permissionsForAuth,
  permissionsForRole,
} from './permission-matrix'
export type {
  MaintenanceAction,
  MaintenancePermissions,
  TenantRole,
} from './permission-matrix'

export const useMaintenancePermissionsStore = defineStore(
  'maintenancePermissions',
  () => {
    const authStore = useAuthStore()

    const permissions = computed(() => (
      permissionsForAuth(
        authStore.currentTenantRole,
        authStore.hasRole,
      )
    ))

    const canView = computed(() => permissions.value.view)
    const canMaintain = computed(() => permissions.value.editMasterData)
    const canAdminister = computed(() => permissions.value.publishRules)

    const can = (action: MaintenanceAction): boolean => {
      return permissions.value[action]
    }

    return {
      permissions,
      canView,
      canMaintain,
      canAdminister,
      can,
    }
  },
)
