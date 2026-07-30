import {
  createMasterDataTransferApi,
  masterDataTransferApi,
  type ImportMapping,
  type ImportTaskUploadResult,
  type ImportTaskView,
} from '../../../api/maintenance/imports'
import type { MaintenanceClientError } from '../../../api/maintenance/types'
import {
  canExecuteImport,
  createImportState,
  importReducer,
  type ImportWorkflowState,
} from './import-state'
import {
  createImportTaskPolling,
  type ImportTaskPolling,
  type ImportTaskPollingOptions,
} from './useImportTaskPolling'

export type MasterDataTransferApi = ReturnType<typeof createMasterDataTransferApi>

export interface ImportWorkflowOptions {
  api?: MasterDataTransferApi
  createPoller?: (options: ImportTaskPollingOptions) => ImportTaskPolling
  resourceKey?: string
}

export interface ImportWorkflow {
  readonly state: ImportWorkflowState
  readonly busy: boolean
  selectFile(file: File): void
  upload(): Promise<void>
  setMapping(sheet: string, source: string, target: string): void
  preview(): Promise<void>
  confirm(): void
  execute(): Promise<void>
  retryStatus(): Promise<void>
  reset(resourceKey: string): void
  cancel(): void
  setVisible(visible: boolean): void
  setActive(active: boolean): void
  runExclusive<T>(operation: () => Promise<T>): Promise<T | undefined>
  subscribe(
    listener: (state: ImportWorkflowState, busy: boolean) => void,
  ): () => void
  dispose(): void
}

export interface ImportDialogObjectUrls {
  createObjectURL(blob: Blob): string
  revokeObjectURL(url: string): void
}

export interface ImportDialogLifecycleOptions {
  workflow: Pick<
    ImportWorkflow,
    'busy' | 'cancel' | 'dispose' | 'runExclusive' | 'setVisible'
  >
  api: Pick<MasterDataTransferApi, 'downloadTemplate' | 'downloadErrors'>
  objectUrls: ImportDialogObjectUrls
  triggerDownload: (url: string, filename: string) => void
  onError: (error: MaintenanceClientError) => void
  onClose: () => void
  onCompleted: () => void
}

export interface ImportDialogLifecycle {
  deactivate(): void
  close(): void
  completed(): void
  setVisible(visible: boolean): void
  downloadTemplate(): Promise<void>
  downloadErrors(taskId: string): Promise<void>
  reportWorkflowError(error: MaintenanceClientError | null): void
  dispose(): void
}

export function normalizeImportWorkflowError(error: unknown): MaintenanceClientError {
  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) {
    return error as MaintenanceClientError
  }
  return {
    code: 'IMPORT_REQUEST_FAILED',
    message: error instanceof Error ? error.message : 'Import request failed',
    retryable: true,
  }
}

function isMissingTask(error: MaintenanceClientError): boolean {
  return error.status === 404 || error.code === 'TASK_NOT_FOUND'
}

function expiredTask(
  task: ImportTaskUploadResult | ImportTaskView,
): ImportTaskView {
  if ('can_execute' in task) {
    return { ...task, status: 'EXPIRED', can_execute: false }
  }
  return {
    ...task,
    status: 'EXPIRED',
    sheets: [],
    preview: {},
    errors: [],
    warnings: [],
    can_execute: false,
    created_at: '',
    started_at: null,
    finished_at: null,
    result: null,
    error_code: 'TASK_NOT_FOUND',
    error_message: 'The import task has expired or is no longer available.',
  }
}

function suggestedMapping(task: ImportTaskUploadResult): ImportMapping {
  return Object.fromEntries(
    task.sheets.map((sheet) => [sheet.name, { ...sheet.suggested_mapping }]),
  )
}

export function sanitizeImportDownloadTaskId(taskId: string): string {
  const sanitized = taskId
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')
  return sanitized || 'task'
}

export function createImportDialogLifecycle(
  options: ImportDialogLifecycleOptions,
): ImportDialogLifecycle {
  const urls = new Set<string>()
  let disposed = false
  let lastWorkflowError: MaintenanceClientError | null = null

  function download(blob: Blob, filename: string): void {
    const url = options.objectUrls.createObjectURL(blob)
    urls.add(url)
    try {
      options.triggerDownload(url, filename)
    } finally {
      options.objectUrls.revokeObjectURL(url)
      urls.delete(url)
    }
  }

  function deactivate(): void {
    if (!disposed) options.workflow.cancel()
  }

  async function requestDownload(
    request: () => Promise<Blob>,
    filename: string,
  ): Promise<void> {
    await options.workflow.runExclusive(async () => {
      try {
        download(await request(), filename)
      } catch (error) {
        options.onError(normalizeImportWorkflowError(error))
      }
    })
  }

  return {
    deactivate,
    close(): void {
      deactivate()
      options.onClose()
    },
    completed(): void {
      options.onCompleted()
      deactivate()
      options.onClose()
    },
    setVisible(visible: boolean): void {
      if (!disposed) options.workflow.setVisible(visible)
    },
    async downloadTemplate(): Promise<void> {
      await requestDownload(
        options.api.downloadTemplate,
        'master-data-import-template.xlsx',
      )
    },
    async downloadErrors(taskId: string): Promise<void> {
      const filename = `import-errors-${sanitizeImportDownloadTaskId(taskId)}.xlsx`
      await requestDownload(() => options.api.downloadErrors(taskId), filename)
    },
    reportWorkflowError(error: MaintenanceClientError | null): void {
      if (error === null) {
        lastWorkflowError = null
        return
      }
      if (error === lastWorkflowError) return
      lastWorkflowError = error
      options.onError(error)
    },
    dispose(): void {
      if (disposed) return
      disposed = true
      options.workflow.cancel()
      urls.forEach((url) => options.objectUrls.revokeObjectURL(url))
      urls.clear()
      options.workflow.dispose()
    },
  }
}

export function createImportWorkflow(
  options: ImportWorkflowOptions = {},
): ImportWorkflow {
  const api = options.api ?? masterDataTransferApi
  const pollerFactory = options.createPoller ?? createImportTaskPolling
  const listeners = new Set<(
    state: ImportWorkflowState,
    busy: boolean,
  ) => void>()
  let state = createImportState(options.resourceKey ?? '')
  let selectedFile: File | null = null
  let poller: ImportTaskPolling | null = null
  let disposed = false
  let requestBusy = false

  function publish(): void {
    listeners.forEach((listener) => listener(state, requestBusy))
  }

  function dispatch(event: Parameters<typeof importReducer>[1]): void {
    const next = importReducer(state, event)
    if (next !== state) {
      state = next
      publish()
    }
  }

  function stopPolling(): void {
    poller?.stop()
    poller = null
  }

  function taskForRequest(): { generation: number; taskId: string } | null {
    return state.task === null
      ? null
      : { generation: state.generation, taskId: state.task.task_id }
  }

  function applyTaskFailure(
    generation: number,
    taskId: string | undefined,
    rawError: unknown,
  ): void {
    const error = normalizeImportWorkflowError(rawError)
    if (taskId && isMissingTask(error) && state.task?.task_id === taskId) {
      dispatch({
        type: 'TASK_UPDATED', generation, taskId, task: expiredTask(state.task),
      })
      return
    }
    dispatch({ type: 'REQUEST_FAILED', generation, taskId, error })
  }

  function startPolling(generation: number, taskId: string): void {
    stopPolling()
    const nextPoller = pollerFactory({
      load: async () => (await api.getTask(taskId)).data,
      onTask: (task) => {
        dispatch({ type: 'TASK_UPDATED', generation, taskId, task })
      },
      onError: (error) => applyTaskFailure(generation, taskId, error),
    })
    poller = nextPoller
    void nextPoller.start()
  }

  function selectFile(file: File): void {
    stopPolling()
    selectedFile = file
    dispatch({ type: 'FILE_SELECTED', fileName: file.name })
  }

  async function runExclusive<T>(
    operation: () => Promise<T>,
  ): Promise<T | undefined> {
    if (requestBusy || disposed) return undefined
    requestBusy = true
    publish()
    try {
      return await operation()
    } finally {
      requestBusy = false
      publish()
    }
  }

  function upload(): Promise<void> {
    if (!selectedFile) {
      return Promise.reject(new Error('Select a file before uploading.'))
    }
    const generation = state.generation
    const file = selectedFile
    return runExclusive(async () => {
      try {
        const task = (await api.uploadTask(file)).data
        dispatch({ type: 'TASK_UPLOADED', generation, task })
        if (state.generation === generation && state.task?.task_id === task.task_id) {
          dispatch({ type: 'MAPPING_CHANGED', mapping: suggestedMapping(task) })
        }
      } catch (error) {
        applyTaskFailure(generation, undefined, error)
      }
    }).then(() => undefined)
  }

  function setMapping(sheet: string, source: string, target: string): void {
    const mapping = Object.fromEntries(
      Object.entries(state.mapping).map(([name, values]) => [name, { ...values }]),
    ) as ImportMapping
    mapping[sheet] ??= {}
    if (target) mapping[sheet][source] = target
    else delete mapping[sheet][source]
    dispatch({ type: 'MAPPING_CHANGED', mapping })
  }

  function preview(): Promise<void> {
    const request = taskForRequest()
    if (!request) return Promise.reject(new Error('Upload a file before previewing.'))
    const mapping = state.mapping
    return runExclusive(async () => {
      try {
        const task = (await api.previewTask(request.taskId, mapping)).data
        dispatch({ type: 'TASK_UPDATED', ...request, task })
      } catch (error) {
        applyTaskFailure(request.generation, request.taskId, error)
      }
    }).then(() => undefined)
  }

  function confirm(): void {
    dispatch({ type: 'CONFIRMED' })
  }

  function execute(): Promise<void> {
    if (!canExecuteImport(state)) {
      return Promise.reject(new Error('Explicit confirmation is required before execution.'))
    }
    const request = taskForRequest()
    if (!request) return Promise.reject(new Error('No import task is available for execution.'))
    return runExclusive(async () => {
      try {
        const task = (await api.executeTask(request.taskId)).data
        dispatch({ type: 'TASK_UPDATED', ...request, task })
        if (
          !disposed
          && state.generation === request.generation
          && state.task?.task_id === request.taskId
        ) startPolling(request.generation, request.taskId)
      } catch (error) {
        applyTaskFailure(request.generation, request.taskId, error)
      }
    }).then(() => undefined)
  }

  function retryStatus(): Promise<void> {
    const request = taskForRequest()
    if (!request) return Promise.resolve()
    return runExclusive(async () => {
      try {
        const task = (await api.getTask(request.taskId)).data
        dispatch({ type: 'TASK_UPDATED', ...request, task })
        if (
          !disposed
          && state.generation === request.generation
          && state.task?.task_id === request.taskId
          && !['COMPLETED', 'FAILED', 'EXPIRED'].includes(task.status.toUpperCase())
        ) startPolling(request.generation, request.taskId)
      } catch (error) {
        applyTaskFailure(request.generation, request.taskId, error)
      }
    }).then(() => undefined)
  }

  function reset(resourceKey: string): void {
    stopPolling()
    selectedFile = null
    if (state.resourceKey === resourceKey) {
      // Task 2 intentionally treats a same-resource event as a no-op. A blank
      // file selection gives this controller an explicit, generation-safe reset.
      dispatch({ type: 'FILE_SELECTED', fileName: '' })
      state = { ...state, fileName: null }
      publish()
      return
    }
    dispatch({ type: 'RESOURCE_CHANGED', resourceKey })
  }

  function cancel(): void {
    reset(state.resourceKey)
  }

  function subscribe(
    listener: (nextState: ImportWorkflowState, busy: boolean) => void,
  ): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  }

  function dispose(): void {
    cancel()
    disposed = true
    stopPolling()
    selectedFile = null
    listeners.clear()
  }

  return {
    get state() { return state },
    get busy() { return requestBusy },
    selectFile,
    upload,
    setMapping,
    preview,
    confirm,
    execute,
    retryStatus,
    reset,
    cancel,
    runExclusive,
    setVisible: (visible) => poller?.setVisible(visible),
    setActive: (active) => poller?.setActive(active),
    subscribe,
    dispose,
  }
}
