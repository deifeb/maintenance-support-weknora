import type {
  ReportAction,
  ReportExportFormat,
  ReportJobStatus,
  ReportVersionStatus,
} from './report-types'
import type { MaintenanceDownload } from '../../../api/maintenance/client'

export type ReportRole = 'VIEWER' | 'CONTRIBUTOR' | 'ADMIN'

export function getReportActions(input: {
  role: ReportRole
  jobStatus: ReportJobStatus
  versionStatus: ReportVersionStatus | null
  versionGenerated?: boolean
  hasUnresolvedFindings?: boolean
}): ReportAction[] {
  const actions: ReportAction[] = ['view', 'versions', 'export']

  if (input.role === 'VIEWER') return actions

  actions.push('create')
  // List responses omit generation evidence, so fail closed until a detail read supplies it.
  if (typeof input.versionGenerated !== 'boolean') return actions
  const immutable = input.versionStatus === 'FINAL'
  if (!immutable && !input.versionGenerated) actions.push('generate')
  if (!immutable && input.versionGenerated) actions.push('validate')
  if (input.versionGenerated) actions.push('regenerate')
  if (input.role === 'ADMIN' && input.jobStatus === 'READY_FOR_REVIEW' && input.versionStatus === 'REVIEWED' && !input.hasUnresolvedFindings) actions.push('finalize')
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

type ReportLifecycleMutation = 'generate' | 'validate' | 'finalize' | 'regenerate'
type LifecycleMutations = Partial<Record<ReportLifecycleMutation, (reportId: number) => Promise<unknown>>>

export interface ReportLifecycleController {
  run(action: ReportLifecycleMutation): Promise<void>
  messageFor(error: unknown): string
  requestIdFor(error: unknown): string | undefined
}

function errorField(error: unknown, field: 'code' | 'request_id'): unknown {
  if (typeof error !== 'object' || error === null) return undefined
  const value = error as Record<string, unknown>
  if (typeof value[field] === 'string') return value[field]
  const nested = value.error
  return typeof nested === 'object' && nested !== null && typeof (nested as Record<string, unknown>)[field] === 'string'
    ? (nested as Record<string, unknown>)[field]
    : undefined
}

function buildReportLifecycleController(input: {
  reportId: number
  actions: readonly ReportAction[]
  mutations: LifecycleMutations
  refresh: () => Promise<void>
}): ReportLifecycleController {
  return {
    async run(action) {
      if (!input.actions.includes(action)) throw new Error(`Report action ${action} is not allowed`)
      const mutation = input.mutations[action]
      if (!mutation) throw new Error(`Report mutation ${action} is unavailable`)
      await mutation(input.reportId)
      await input.refresh()
    },
    messageFor(error) { return reportErrorMessageKey(errorField(error, 'code')) },
    requestIdFor(error) {
      const requestId = errorField(error, 'request_id')
      return typeof requestId === 'string' ? requestId : undefined
    },
  }
}

export const createReportLifecycleController = Object.assign(
  buildReportLifecycleController,
  {
    regenerateExplanation: 'A new version is created, its source snapshot is copied from the current report version, and no business source data is recalculated.',
  },
)

export interface ReportExportController {
  download(format: ReportExportFormat): Promise<void>
  messageFor(error: unknown): string
  requestIdFor(error: unknown): string | undefined
}

interface DownloadAnchor {
  href: string
  download: string
  click(): void
  remove(): void
}

export function createReportExportController(input: {
  reportId: number
  actions: readonly ReportAction[]
  exportReport: (reportId: number, format: ReportExportFormat) => Promise<MaintenanceDownload>
  createObjectURL: (blob: Blob) => string
  revokeObjectURL: (url: string) => void
  createAnchor: () => DownloadAnchor
}): ReportExportController {
  return {
    async download(format) {
      if (!input.actions.includes('export')) throw new Error('Report action export is not allowed')
      const response = await input.exportReport(input.reportId, format)
      const blob = new Blob([response.blob], { type: response.contentType })
      let objectUrl: string | undefined
      let anchor: DownloadAnchor | undefined
      try {
        objectUrl = input.createObjectURL(blob)
        anchor = input.createAnchor()
        anchor.href = objectUrl
        anchor.download = response.filename
        anchor.click()
      } finally {
        anchor?.remove()
        if (objectUrl) input.revokeObjectURL(objectUrl)
      }
    },
    messageFor(error) { return reportErrorMessageKey(errorField(error, 'code')) },
    requestIdFor(error) {
      const requestId = errorField(error, 'request_id')
      return typeof requestId === 'string' ? requestId : undefined
    },
  }
}
