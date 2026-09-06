import type {
  ReportAction,
  ReportJobStatus,
  ReportVersionStatus,
} from './report-types'

export type ReportRole = 'VIEWER' | 'CONTRIBUTOR' | 'ADMIN'

export function getReportActions(input: {
  role: ReportRole
  jobStatus: ReportJobStatus
  versionStatus: ReportVersionStatus | null
  backendAllowsRegenerate?: boolean
}): ReportAction[] {
  const actions: ReportAction[] = ['view', 'versions', 'export']

  if (input.role === 'VIEWER') return actions

  actions.push('create')
  const immutable = input.jobStatus === 'FINALIZED' || input.versionStatus === 'FINAL'
  if (!immutable) {
    actions.push('generate', 'validate')
  }
  if (input.backendAllowsRegenerate) {
    actions.push('regenerate')
  }
  if (input.role === 'ADMIN' && !immutable) {
    actions.push('finalize')
  }
  return actions
}

const reportErrorKeys: Record<string, string> = {
  REPORT_VERSION_ALREADY_GENERATED: 'maintenance.reports.errors.versionAlreadyGenerated',
  REPORT_GENERATION_REQUIRED: 'maintenance.reports.errors.generationRequired',
  REPORT_FINAL_VERSION_IMMUTABLE: 'maintenance.reports.errors.finalVersionImmutable',
  REPORT_REGENERATE_SOURCE_NOT_READY: 'maintenance.reports.errors.regenerateSourceNotReady',
  REPORT_VALIDATION_REQUIRED: 'maintenance.reports.errors.validationRequired',
  REPORT_GENERATION_FAILED: 'maintenance.reports.errors.generationFailed',
  REPORT_SOURCE_REQUIRED: 'maintenance.reports.errors.sourceRequired',
  REPORT_SOURCE_CONFLICT: 'maintenance.reports.errors.sourceConflict',
  REPORT_SOURCE_VERSION_CONFLICT: 'maintenance.reports.errors.sourceVersionConflict',
  INSUFFICIENT_MAINTENANCE_ROLE: 'maintenance.reports.errors.insufficientRole',
}

export function reportErrorMessageKey(code: unknown): string {
  return typeof code === 'string'
    ? (reportErrorKeys[code] ?? 'maintenance.reports.errors.generic')
    : 'maintenance.reports.errors.generic'
}
