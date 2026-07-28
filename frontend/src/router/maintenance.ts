import type { RouteRecordRaw } from 'vue-router'

const maintenanceRouteMeta = {
  requiresInit: true,
  requiresAuth: true,
} as const

export const maintenanceRouteRecords: RouteRecordRaw[] = [
  {
    path: 'maintenance',
    name: 'maintenance',
    component: () => import('@/views/maintenance/MaintenanceShell.vue'),
    redirect: '/platform/maintenance/dashboard',
    meta: { ...maintenanceRouteMeta },
    children: [
      {
        path: 'dashboard',
        name: 'maintenanceDashboard',
        component: () => import('@/views/maintenance/dashboard/MaintenanceDashboard.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'master-data',
        name: 'maintenanceMasterData',
        component: () => import('@/views/maintenance/master-data/MasterDataHome.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'master-data/configurations/:configurationId',
        name: 'maintenanceConfigurationDetail',
        component: () => import(
          '@/views/maintenance/master-data/ConfigurationDetail.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'scenarios',
        name: 'maintenanceScenarios',
        component: () => import('@/views/maintenance/scenarios/ScenarioList.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'calculations',
        name: 'maintenanceCalculations',
        component: () => import('@/views/maintenance/calculations/CalculationList.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'inventory-gap',
        name: 'maintenanceInventoryGap',
        component: () => import('@/views/maintenance/inventory-gap/InventoryGapPage.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'reviews',
        name: 'maintenanceReviews',
        component: () => import('@/views/maintenance/reviews/ReviewList.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'reports',
        name: 'maintenanceReports',
        component: () => import('@/views/maintenance/reports/ReportCenter.vue'),
        meta: { ...maintenanceRouteMeta },
      },
    ],
  },
]
