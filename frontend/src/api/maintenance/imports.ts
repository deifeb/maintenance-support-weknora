import {
  buildQuery,
  createMaintenanceClient,
  type MaintenanceClient,
} from './client'
import type { MaintenanceResult } from './types'

export interface ImportIssue {
  sheet: string | null
  row: number | null
  field: string | null
  code: string
  message: string
}

export interface ImportSheetInspection {
  name: string
  source_headers: string[]
  suggested_mapping: Record<string, string>
  required_fields: string[]
}

export interface ImportSheetSummary {
  name: string
  total_rows: number
  valid_rows: number
  invalid_rows: number
}

export interface ImportExecutionResult {
  imported: boolean
  created: Record<string, number>
  updated: Record<string, number>
  total_rows: number
}

export interface ImportTaskUploadResult {
  task_id: string
  status: string
  original_filename: string
  file_sha256: string
  template_version: string
  sheets: ImportSheetInspection[]
  expires_at: string
}

export interface ImportTaskView {
  task_id: string
  status: string
  original_filename: string
  file_sha256: string
  template_version: string
  sheets: ImportSheetSummary[]
  preview: Record<string, Array<Record<string, unknown>>>
  errors: ImportIssue[]
  warnings: ImportIssue[]
  can_execute: boolean
  created_at: string
  expires_at: string
  started_at: string | null
  finished_at: string | null
  result: ImportExecutionResult | null
  error_code: string | null
  error_message: string | null
}

export interface MasterDataExportQuery {
  keyword?: string
  include_inactive?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export type ImportMapping = Record<string, Record<string, string>>

export type MasterDataTransferApiClient = Pick<
  MaintenanceClient,
  'download' | 'get' | 'post'
>

const defaultMasterDataTransferClient = createMaintenanceClient()

function taskPath(taskId: string): string {
  return `/v1/master-data/import/tasks/${encodeURIComponent(taskId)}`
}

export function createMasterDataTransferApi(
  client: MasterDataTransferApiClient = defaultMasterDataTransferClient,
) {
  return {
    downloadTemplate(): Promise<Blob> {
      return client.download('/v1/master-data/import/template')
    },

    uploadTask(file: File): Promise<MaintenanceResult<ImportTaskUploadResult>> {
      const body = new FormData()
      body.append('file', file)
      return client.post<ImportTaskUploadResult>(
        '/v1/master-data/import/tasks',
        body,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        },
      )
    },

    previewTask(
      taskId: string,
      mapping: ImportMapping,
    ): Promise<MaintenanceResult<ImportTaskView>> {
      return client.post<ImportTaskView>(
        `${taskPath(taskId)}/preview`,
        { mapping },
      )
    },

    executeTask(taskId: string): Promise<MaintenanceResult<ImportTaskView>> {
      return client.post<ImportTaskView>(
        `${taskPath(taskId)}/execute`,
        {},
      )
    },

    getTask(taskId: string): Promise<MaintenanceResult<ImportTaskView>> {
      return client.get<ImportTaskView>(taskPath(taskId))
    },

    downloadErrors(taskId: string): Promise<Blob> {
      return client.download(`${taskPath(taskId)}/errors.xlsx`)
    },

    exportResource(
      resourceKey: string,
      query: MasterDataExportQuery,
    ): Promise<Blob> {
      const queryString = buildQuery({
        keyword: query.keyword,
        include_inactive: query.include_inactive,
        sort_by: query.sort_by,
        sort_order: query.sort_order,
      })
      const path = `/v1/master-data/exports/${encodeURIComponent(resourceKey)}`
      return client.download(queryString ? `${path}?${queryString}` : path)
    },
  }
}

export const masterDataTransferApi = createMasterDataTransferApi()
