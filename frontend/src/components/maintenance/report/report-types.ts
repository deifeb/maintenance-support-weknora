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
  type: string
  id: number
  version: string
  lineage_id?: string | null
  digest?: string | null
}

export interface PublicSourceProvenance {
  capture_mode: string | null
  provenance_completeness?: string | null
  sources: PublicSourceVersion[]
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
  job_status?: ReportJobStatus
  progress_percent?: number
  version_id: number
  version_number: number
  parent_version_id: number | null
  template_version: string
  input_digest: string | null
  generation_mode: string | null
  generated_at: string | null
  source_versions: PublicSourceProvenance | null
  sections: ReportSection[]
  citations: ReportCitation[]
  findings?: ReportValidationFinding[]
}

export interface ReportSourceReference {
  type: string
  id: number
  version?: string | null
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

function isPublicSource(value: unknown): value is PublicSourceVersion {
  if (typeof value !== 'object' || value === null) return false
  const source = value as Record<string, unknown>
  return typeof source.type === 'string'
    && typeof source.id === 'number'
    && typeof source.version === 'string'
}

export function toPublicSourceProvenance(
  value: unknown,
): PublicSourceProvenance | null {
  if (typeof value !== 'object' || value === null) return null
  const provenance = value as Record<string, unknown>
  if (!Array.isArray(provenance.sources) || !provenance.sources.every(isPublicSource)) {
    return null
  }
  const captureMode = provenance.capture_mode
  const completeness = provenance.provenance_completeness
  if (captureMode !== null && typeof captureMode !== 'string') return null
  if (completeness !== undefined && completeness !== null && typeof completeness !== 'string') {
    return null
  }
  return {
    capture_mode: typeof captureMode === 'string' ? captureMode : null,
    ...(completeness === undefined
      ? {}
      : { provenance_completeness: completeness as string | null }),
    sources: provenance.sources.map((source) => ({
      type: source.type,
      id: source.id,
      version: source.version,
      ...(typeof source.lineage_id === 'string' || source.lineage_id === null
        ? { lineage_id: source.lineage_id }
        : {}),
      ...(typeof source.digest === 'string' || source.digest === null
        ? { digest: source.digest }
        : {}),
    })),
  }
}
