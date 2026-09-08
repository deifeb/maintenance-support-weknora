export interface MaintenanceMenuChild {
  title: string
  titleKey: string
  path: string
  routeName: string
}

export const maintenanceMenuChildren: MaintenanceMenuChild[] = [
  {
    title: '',
    titleKey: 'maintenance.pages.dashboard',
    path: 'maintenance/dashboard',
    routeName: 'maintenanceDashboard',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.masterData',
    path: 'maintenance/master-data',
    routeName: 'maintenanceMasterData',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.scenarios',
    path: 'maintenance/scenarios',
    routeName: 'maintenanceScenarios',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.calculations',
    path: 'maintenance/calculations',
    routeName: 'maintenanceCalculations',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.inventoryGap',
    path: 'maintenance/inventory-gap',
    routeName: 'maintenanceInventoryGap',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.reviews',
    path: 'maintenance/reviews',
    routeName: 'maintenanceReviews',
  },
  {
    title: '',
    titleKey: 'maintenance.pages.reports',
    path: 'maintenance/reports',
    routeName: 'maintenanceReports',
  },
]
