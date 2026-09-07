import {
  buildQuery,
  createMaintenanceClient,
  type MaintenanceClient,
  type MaintenanceDownload,
} from './client'
import type { MaintenanceResult, PageData } from './types'
import type {
  CreateReportJobInput,
  ReportDetail,
  ReportExportFormat,
  ReportJobStatus,
  ReportJobStatusRead,
  ReportListItem,
  ReportListQuery,
  PublicSourceProvenance,
  ReportVersionSummary,
} from '../../components/maintenance/report/report-types'

export type {
  CreateReportJobInput,
  PublicSourceVersion,
  PublicSourceProvenance,
  ReportAction,
  ReportDetail,
  ReportExportFormat,
  ReportJobStatus,
  ReportListItem,
  ReportListQuery,
  ReportJobStatusRead,
  ReportVersionStatus,
  ReportVersionSummary,
} from '../../components/maintenance/report/report-types'

export { toPublicSourceProvenance } from '../../components/maintenance/report/report-types'

export type ReportApiClient = Pick<
  MaintenanceClient,
  'get' | 'post' | 'downloadWithMetadata'
>

function reportPath(reportId: number): string {
  return `/v1/reports/${encodeURIComponent(String(reportId))}`
}

function exportPath(reportId: number, format: ReportExportFormat): string {
  return `${reportPath(reportId)}/exports/${format.toLowerCase()}`
}

export function createReportApi(
  client: ReportApiClient = createMaintenanceClient(),
) {
  return {
    listReports(
      query: ReportListQuery,
    ): Promise<MaintenanceResult<PageData<ReportListItem>>> {
      const encodedQuery = buildQuery({ ...query })
      return client.get<PageData<ReportListItem>>(
        encodedQuery ? `/v1/reports?${encodedQuery}` : '/v1/reports',
      )
    },
    createReportJob(
      body: CreateReportJobInput,
    ): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.post<ReportJobStatusRead>('/v1/reports/jobs', body)
    },
    getReportJob(reportId: number): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.get<ReportJobStatusRead>(
        `/v1/reports/jobs/${encodeURIComponent(String(reportId))}`,
      )
    },
    getReport(reportId: number): Promise<MaintenanceResult<ReportDetail>> {
      return client.get<ReportDetail>(reportPath(reportId))
    },
    listReportVersions(
      reportId: number,
    ): Promise<MaintenanceResult<ReportVersionSummary[]>> {
      return client.get<ReportVersionSummary[]>(`${reportPath(reportId)}/versions`)
    },
    generateReport(reportId: number): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.post<ReportJobStatusRead>(`${reportPath(reportId)}/generate`, {})
    },
    validateReport(reportId: number): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.post<ReportJobStatusRead>(`${reportPath(reportId)}/validate`, {})
    },
    finalizeReport(reportId: number): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.post<ReportJobStatusRead>(`${reportPath(reportId)}/finalize`, {})
    },
    regenerateReport(reportId: number): Promise<MaintenanceResult<ReportJobStatusRead>> {
      return client.post<ReportJobStatusRead>(`${reportPath(reportId)}/regenerate`, {})
    },
    exportReport(
      reportId: number,
      format: ReportExportFormat,
    ): Promise<MaintenanceDownload> {
      return client.downloadWithMetadata(exportPath(reportId, format))
    },
  }
}

export const reportApi = createReportApi()
