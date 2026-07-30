import {
  normalizeMaintenanceError,
} from '../../../api/maintenance/client'
import {
  masterDataTransferApi,
  type MasterDataExportQuery,
} from '../../../api/maintenance/imports'
import type { MaintenanceClientError } from '../../../api/maintenance/types'
import type {
  MasterDataResourceDefinition,
} from '../../../components/maintenance/master-data/MasterDataRegistry'

export type MasterDataTransferApi = Pick<
  typeof masterDataTransferApi,
  'downloadTemplate' | 'exportResource'
>

export interface MasterDataTransferToken {
  resourceKey: string
  generation: number
}

export interface XlsxDownloadLink {
  href: string
  download: string
  style: { display: string }
  click(): void
  remove(): void
}

export interface XlsxDownloadDocument {
  body: { append(node: XlsxDownloadLink): void }
  createElement(tag: 'a'): XlsxDownloadLink
}

export interface XlsxObjectUrls {
  createObjectURL(blob: Blob): string
  revokeObjectURL(url: string): void
}

export interface XlsxDownloadTriggerOptions {
  document: XlsxDownloadDocument
  objectUrls: XlsxObjectUrls
  defer(callback: () => void): unknown
}

export type MasterDataDownloadTrigger = (blob: Blob, filename: string) => void

export interface MasterDataTransferActionsOptions {
  api: MasterDataTransferApi
  getResource(): Pick<MasterDataResourceDefinition, 'key' | 'transfer'>
  getQuery(): MasterDataExportQuery
  getGeneration(): number
  download: MasterDataDownloadTrigger
  onBusyChange(busy: boolean): void
  onError(error: MaintenanceClientError): void
  refresh(): Promise<void>
  normalizeError?(value: unknown): MaintenanceClientError
}

export interface MasterDataTransferActions {
  downloadTemplate(): Promise<void>
  exportCurrentResults(): Promise<void>
  handleCompleted(token: MasterDataTransferToken): Promise<void>
}

function sanitizeDownloadBase(value: string): string {
  const sanitized = value
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')
  return sanitized || 'master-data'
}

function sameToken(
  token: MasterDataTransferToken,
  options: Pick<
    MasterDataTransferActionsOptions,
    'getGeneration' | 'getResource'
  >,
): boolean {
  return (
    token.generation === options.getGeneration()
    && token.resourceKey === options.getResource().key
  )
}

export function createXlsxDownloadTrigger(
  options: XlsxDownloadTriggerOptions,
): MasterDataDownloadTrigger {
  return (blob, filename) => {
    const url = options.objectUrls.createObjectURL(blob)
    const link = options.document.createElement('a')
    link.href = url
    link.download = filename
    link.style.display = 'none'
    options.document.body.append(link)

    try {
      link.click()
    } finally {
      link.remove()
      options.defer(() => options.objectUrls.revokeObjectURL(url))
    }
  }
}

export function createMasterDataTransferActions(
  options: MasterDataTransferActionsOptions,
): MasterDataTransferActions {
  const normalizeError = options.normalizeError ?? normalizeMaintenanceError
  let busy = false

  async function run(action: () => Promise<void>): Promise<void> {
    if (busy) return
    busy = true
    options.onBusyChange(true)
    try {
      await action()
    } catch (value) {
      options.onError(normalizeError(value))
    } finally {
      busy = false
      options.onBusyChange(false)
    }
  }

  return {
    downloadTemplate(): Promise<void> {
      return run(async () => {
        const blob = await options.api.downloadTemplate()
        options.download(blob, 'master-data-import-template.xlsx')
      })
    },

    exportCurrentResults(): Promise<void> {
      const resource = options.getResource()
      const transfer = resource.transfer
      const token: MasterDataTransferToken = {
        resourceKey: resource.key,
        generation: options.getGeneration(),
      }
      if (!transfer) return Promise.resolve()

      return run(async () => {
        const query = options.getQuery()
        const blob = await options.api.exportResource(transfer.exportKey, {
          keyword: query.keyword,
          include_inactive: query.include_inactive,
          sort_by: query.sort_by,
          sort_order: query.sort_order,
        })
        if (!sameToken(token, options)) return
        options.download(
          blob,
          `${sanitizeDownloadBase(transfer.exportKey)}-export.xlsx`,
        )
      })
    },

    async handleCompleted(token: MasterDataTransferToken): Promise<void> {
      if (!sameToken(token, options)) return
      await options.refresh()
    },
  }
}
