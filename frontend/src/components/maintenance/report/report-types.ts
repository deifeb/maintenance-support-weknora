export type ReportJobStatus =
  | 'CREATED'
  | 'BUILDING_SKELETON'
  | 'GENERATING_SECTIONS'
  | 'VALIDATING_NUMBERS'
  | 'VALIDATING_CITATIONS'
  | 'READY_FOR_REVIEW'
  | 'PARTIALLY_COMPLETED'
  | 'FAILED'
  | 'FINALIZED'

export type ReportVersionStatus = 'DRAFT' | 'REVIEWED' | 'FINAL' | 'SUPERSEDED'

export type ReportType =
  | 'DEMAND_CALCULATION'
  | 'MODEL_COMPARISON'
  | 'DEMAND_REVIEW'
  | 'INVENTORY_GAP'
  | 'ALLOCATION_PLAN'
  | 'STOCKTAKE'
  | 'SPARE_PART_RISK'
  | 'MANAGEMENT_DECISION'

export const REPORT_TYPES: readonly ReportType[] = [
  'DEMAND_CALCULATION', 'MODEL_COMPARISON', 'DEMAND_REVIEW',
  'INVENTORY_GAP', 'ALLOCATION_PLAN', 'STOCKTAKE', 'SPARE_PART_RISK',
  'MANAGEMENT_DECISION',
]

export const REPORT_JOB_STATUSES: readonly ReportJobStatus[] = [
  'CREATED', 'BUILDING_SKELETON', 'GENERATING_SECTIONS',
  'VALIDATING_NUMBERS', 'VALIDATING_CITATIONS', 'READY_FOR_REVIEW',
  'PARTIALLY_COMPLETED', 'FAILED', 'FINALIZED',
]

export const REPORT_VERSION_STATUSES: readonly ReportVersionStatus[] = [
  'DRAFT', 'REVIEWED', 'FINAL', 'SUPERSEDED',
]

export type ReportExportFormat = 'MARKDOWN' | 'JSON' | 'DOCX'

export type PublicReportSourceType =
  | 'AI_SESSION'
  | 'SCENARIO_VERSION'
  | 'CALCULATION_RUN'
  | 'CALCULATION_GROUP'
  | 'DEMAND_LIST'
  | 'DEMAND_REVIEW'
  | 'ALLOCATION_PLAN'
  | 'INVENTORY_STOCKTAKE'

export type RequiredPublicScalar = string | number | boolean

export interface PublicSourceVersion {
  type: PublicReportSourceType
  id: RequiredPublicScalar
  version: RequiredPublicScalar
  lineage_id: PublicScalar
  digest: string | null
}

export interface AuthoritativeSourceProvenance {
  kind: 'authoritative'
  capture_mode: 'AUTHORITATIVE_CREATE'
  provenance_completeness: 'AUTHORITATIVE'
  sources: PublicSourceVersion[]
}

export type LegacySourceName =
  | 'session'
  | 'scenario_version'
  | 'calculation_run'
  | 'review_run'
  | 'inventory'

export type PublicScalar = string | number | boolean | null
export type LegacySourceValues = Partial<Record<
  'id' | 'version' | 'session_code' | 'version_code' | 'formula_version'
  | 'input_schema_version' | 'calculation_id' | 'attempt_number' | 'run_mode'
  | 'engine_version' | 'input_snapshot_hash' | 'inventory_snapshot_at'
  | 'rule_set_version' | 'scenario_version_id' | 'calculation_run_id' | 'snapshot_at',
  PublicScalar
>>

export interface LegacySourceProvenance {
  kind: 'legacy'
  capture_mode: PublicScalar
  provenance_completeness?: PublicScalar
  sources: Partial<Record<LegacySourceName, LegacySourceValues | null>>
}

export interface UnavailableSourceProvenance {
  kind: 'unavailable'
}

export type PublicSourceProvenance =
  | AuthoritativeSourceProvenance
  | LegacySourceProvenance
  | UnavailableSourceProvenance

export interface ReportListQuery {
  page: number
  page_size: number
  keyword?: string
  report_type?: ReportType
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

export function normalizeReportListQuery(input: Record<string, unknown> = {}): ReportListQuery {
  const value = (key: string) => Array.isArray(input[key]) ? input[key][0] : input[key]
  const text = (key: string, limit?: number) => typeof value(key) === 'string' && value(key).trim() && (!limit || value(key).trim().length <= limit) ? value(key).trim() : undefined
  const positive = (key: string, fallback: number, maximum?: number) => { const parsed = Number(value(key)); return Number.isInteger(parsed) && parsed > 0 && (!maximum || parsed <= maximum) ? parsed : fallback }
  const reportType = text('report_type'); const jobStatus = text('job_status'); const versionStatus = text('version_status')
  const sortBy = text('sort_by'); const sortOrder = text('sort_order')
  return {
    page: positive('page', 1), page_size: positive('page_size', 20, 200), sort_by: ['created_at', 'report_code', 'title', 'report_type', 'job_status'].includes(sortBy ?? '') ? sortBy as ReportListQuery['sort_by'] : 'created_at', sort_order: ['asc', 'desc'].includes(sortOrder ?? '') ? sortOrder as ReportListQuery['sort_order'] : 'desc',
    ...(text('keyword', 255) ? { keyword: text('keyword', 255) } : {}), ...(reportType && REPORT_TYPES.includes(reportType as ReportType) ? { report_type: reportType as ReportType } : {}), ...(jobStatus && REPORT_JOB_STATUSES.includes(jobStatus as ReportJobStatus) ? { job_status: jobStatus as ReportJobStatus } : {}), ...(versionStatus && REPORT_VERSION_STATUSES.includes(versionStatus as ReportVersionStatus) ? { version_status: versionStatus as ReportVersionStatus } : {}),
    ...(positive('session_id', 0) ? { session_id: positive('session_id', 0) } : {}), ...(positive('scenario_version_id', 0) ? { scenario_version_id: positive('scenario_version_id', 0) } : {}), ...(positive('calculation_run_id', 0) ? { calculation_run_id: positive('calculation_run_id', 0) } : {}), ...(positive('review_run_id', 0) ? { review_run_id: positive('review_run_id', 0) } : {}), ...(text('source_type') ? { source_type: text('source_type') } : {}), ...(positive('source_id', 0) ? { source_id: positive('source_id', 0) } : {}), ...(text('source_version', 128) ? { source_version: text('source_version', 128) } : {}),
  }
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
  source_versions: unknown
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

const LEGACY_SOURCE_FIELDS: Record<LegacySourceName, readonly (keyof LegacySourceValues)[]> = {
  session: ['id', 'version', 'session_code'],
  scenario_version: ['id', 'version', 'version_code', 'formula_version', 'input_schema_version'],
  calculation_run: ['id', 'calculation_id', 'attempt_number', 'run_mode', 'engine_version', 'formula_version', 'input_snapshot_hash', 'inventory_snapshot_at'],
  review_run: ['id', 'version', 'rule_set_version', 'scenario_version_id', 'calculation_run_id'],
  inventory: ['snapshot_at'],
}

function isPublicScalar(value: unknown): value is PublicScalar {
  return value === null || typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
}

function isRequiredPublicScalar(value: unknown): value is RequiredPublicScalar {
  return value !== null && isPublicScalar(value)
}

function isPublicReportSourceType(value: unknown): value is PublicReportSourceType {
  return typeof value === 'string' && [
    'AI_SESSION',
    'SCENARIO_VERSION',
    'CALCULATION_RUN',
    'CALCULATION_GROUP',
    'DEMAND_LIST',
    'DEMAND_REVIEW',
    'ALLOCATION_PLAN',
    'INVENTORY_STOCKTAKE',
  ].includes(value)
}

function isPublicSource(value: unknown): value is PublicSourceVersion {
  if (typeof value !== 'object' || value === null) return false
  const source = value as Record<string, unknown>
  return isPublicReportSourceType(source.type)
    && isRequiredPublicScalar(source.id)
    && isRequiredPublicScalar(source.version)
    && isPublicScalar(source.lineage_id)
    && (typeof source.digest === 'string' || source.digest === null)
}

export function toPublicSourceProvenance(
  value: unknown,
): PublicSourceProvenance {
  if (typeof value !== 'object' || value === null) return { kind: 'unavailable' }
  const provenance = value as Record<string, unknown>
  if (Object.keys(provenance).length === 0) return { kind: 'unavailable' }
  if (
    provenance.capture_mode === 'AUTHORITATIVE_CREATE'
    && provenance.provenance_completeness === 'AUTHORITATIVE'
    && Array.isArray(provenance.sources)
    && provenance.sources.every(isPublicSource)
  ) {
    return {
      kind: 'authoritative',
      capture_mode: 'AUTHORITATIVE_CREATE',
      provenance_completeness: 'AUTHORITATIVE',
      sources: provenance.sources.map((source) => ({
        type: source.type,
        id: source.id,
        version: source.version,
        lineage_id: source.lineage_id,
        digest: source.digest,
      })),
    }
  }
  if (!isPublicScalar(provenance.capture_mode) || typeof provenance.sources !== 'object' || provenance.sources === null || Array.isArray(provenance.sources)) {
    return { kind: 'unavailable' }
  }
  const sourceRecord = provenance.sources as Record<string, unknown>
  const sources: LegacySourceProvenance['sources'] = {}
  for (const [name, fields] of Object.entries(LEGACY_SOURCE_FIELDS) as Array<[LegacySourceName, readonly (keyof LegacySourceValues)[]]>) {
    if (!(name in sourceRecord)) continue
    const source = sourceRecord[name]
    if (source === null) {
      sources[name] = null
      continue
    }
    if (typeof source !== 'object' || source === null || Array.isArray(source)) {
      return { kind: 'unavailable' }
    }
    const selected: LegacySourceValues = {}
    for (const field of fields) {
      const fieldValue = (source as Record<string, unknown>)[field]
      if (fieldValue !== undefined && isPublicScalar(fieldValue)) selected[field] = fieldValue
    }
    sources[name] = selected
  }
  const completeness = provenance.provenance_completeness
  if (completeness !== undefined && !isPublicScalar(completeness)) return { kind: 'unavailable' }
  return {
    kind: 'legacy',
    capture_mode: provenance.capture_mode,
    ...(completeness === undefined
      ? {}
      : { provenance_completeness: completeness }),
    sources,
  }
}
