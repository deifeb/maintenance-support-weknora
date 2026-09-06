export type ReportJobStatus =
  | 'CREATED'
  | 'GENERATING_SECTIONS'
  | 'VALIDATING_NUMBERS'
  | 'READY_FOR_REVIEW'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'FINALIZED'

export type ReportVersionStatus = 'DRAFT' | 'REVIEWED' | 'FINAL' | 'SUPERSEDED'

export type ReportExportFormat = 'MARKDOWN' | 'JSON' | 'DOCX'

export interface PublicSourceVersion {
  source_type: string
  source_id: number | null
  source_version: string | null
  display_name?: string | null
}

export interface ReportListQuery {
  page: number
  page_size: number
  keyword?: string
  report_type?: string
  job_status?: ReportJobStatus
  version_status?: ReportVersionStatus
  session_id?: number
  scenario_version_id?: number
  calculation_run_id?: number
  review_run_id?: number
  source_type?: string
  source_id?: number
  source_version?: string
  sort_by?: 'created_at' | 'report_code' | 'title' | 'report_type' | 'job_status'
  sort_order?: 'asc' | 'desc'
}

export interface ReportVersionSummary {
  id: number
  version_number: number
  status: ReportVersionStatus
  parent_version_id: number | null
  template_version: string
  content_digest: string
  input_digest: string | null
  generation_mode: string | null
  generated_at: string | null
}

export interface ReportListItem {
  report_id: number
  report_code: string
  session_id: number | null
  report_type: string
  job_status: ReportJobStatus
  title: string
  progress_percent: number
  error_code: string | null
  created_at: string
  updated_at: string
  latest_version: Pick<ReportVersionSummary, 'id' | 'version_number' | 'status'> | null
}

export interface ReportJobStatusRead {
  report_id: number
  report_code: string
  report_type: string
  job_status: ReportJobStatus
  title: string
  progress_percent: number
  error_code: string | null
  latest_version: ReportVersionSummary
}

export interface ReportSection {
  section_code: string
  title: string
  content: string | null
  tables?: unknown[]
}

export interface ReportCitation {
  citation_id: string
  source_type: string
  source_id: string | number | null
  label: string | null
}

export interface ReportValidationFinding {
  id: number
  code: string
  severity: string
  message: string
  resolved: boolean
}

export interface ReportDetail {
  report_id: number
  report_code: string
  report_type: string
  title: string
  status: ReportVersionStatus
  job_status: ReportJobStatus
  progress_percent: number
  version_id: number
  version_number: number
  parent_version_id: number | null
  template_version: string
  input_digest: string | null
  generation_mode: string | null
  generated_at: string | null
  source_versions: PublicSourceVersion[]
  sections: ReportSection[]
  citations: ReportCitation[]
  findings: ReportValidationFinding[]
}

export interface ReportSourceReference {
  source_type: string
  source_id: number
  source_version?: string | null
}

export interface CreateReportJobInput {
  title: string
  report_type: string
  source_refs: ReportSourceReference[]
  session_id?: number | null
  scenario_version_id?: number | null
  calculation_run_id?: number | null
  review_run_id?: number | null
  sections?: unknown[]
  citations?: unknown[]
  metadata?: Record<string, unknown>
}

export type ReportAction =
  | 'view'
  | 'versions'
  | 'export'
  | 'create'
  | 'generate'
  | 'validate'
  | 'finalize'
  | 'regenerate'
