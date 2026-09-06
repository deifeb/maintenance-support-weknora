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
        path: 'master-data/spare-parts/:sparePartId',
        name: 'maintenanceSparePartDetail',
        component: () => import(
          '@/views/maintenance/master-data/SparePartDetail.vue'
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
        path: 'scenarios/new',
        name: 'maintenanceScenarioNew',
        component: () => import(
          '@/views/maintenance/scenarios/ScenarioWizard.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'scenarios/:scenarioId',
        name: 'maintenanceScenarioDetail',
        component: () => import(
          '@/views/maintenance/scenarios/ScenarioDetail.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: (
          'scenarios/:scenarioId/versions/:versionId'
        ),
        name: 'maintenanceScenarioVersionDetail',
        component: () => import(
          '@/views/maintenance/scenarios/ScenarioDetail.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'calculations',
        name: 'maintenanceCalculations',
        component: () => import('@/views/maintenance/calculations/CalculationList.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'calculations/new',
        name: 'maintenanceCalculationNew',
        component: () => import(
          '@/views/maintenance/calculations/CalculationSetup.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'calculations/:groupId/progress',
        name: 'maintenanceCalculationProgress',
        component: () => import(
          '@/views/maintenance/calculations/CalculationProgress.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'calculations/:groupId/comparison',
        name: 'maintenanceCalculationComparison',
        component: () => import(
          '@/views/maintenance/calculations/CalculationComparison.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'calculations/demand-lists/:listId',
        name: 'maintenanceDemandListDetail',
        component: () => import(
          '@/views/maintenance/calculations/DemandListDetail.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
      },
      {
        path: 'inventory-gap',
        name: 'maintenanceInventoryGap',
        component: () => import('@/views/maintenance/inventory-gap/InventoryGapPage.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'inventory-gap/rules',
        name: 'maintenanceAllocationRules',
        component: () => import('@/views/maintenance/inventory-gap/AllocationRuleList.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/allocations/:planId',
        name: 'maintenanceAllocationPlanDetail',
        component: () => import('@/views/maintenance/inventory-gap/AllocationPlanDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/balances/:balanceId',
        name: 'maintenanceInventoryBalanceDetail',
        component: () => import('@/views/maintenance/inventory-gap/InventoryBalanceDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/transactions/:transactionId',
        name: 'maintenanceInventoryTransactionDetail',
        component: () => import('@/views/maintenance/inventory-gap/InventoryTransactionDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/reservations/:reservationId',
        name: 'maintenanceInventoryReservationDetail',
        component: () => import('@/views/maintenance/inventory-gap/InventoryReservationDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/transfers/:transferId',
        name: 'maintenanceInventoryTransferDetail',
        component: () => import('@/views/maintenance/inventory-gap/InventoryTransferDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'inventory-gap/stocktakes/:stocktakeId',
        name: 'maintenanceInventoryStocktakeDetail',
        component: () => import('@/views/maintenance/inventory-gap/InventoryStocktakeDetail.vue'),
        meta: { ...maintenanceRouteMeta, hideInMaintenanceMenu: true },
      },
      {
        path: 'reviews',
        name: 'maintenanceReviews',
        component: () => import('@/views/maintenance/reviews/ReviewList.vue'),
        meta: { ...maintenanceRouteMeta },
      },
      {
        path: 'reviews/:reviewId',
        name: 'maintenanceReviewDetail',
        component: () => import(
          '@/views/maintenance/reviews/ReviewDetail.vue'
        ),
        meta: {
          ...maintenanceRouteMeta,
          hideInMaintenanceMenu: true,
        },
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
