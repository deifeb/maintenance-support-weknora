import type {
  ImportMapping,
  ImportTaskUploadResult,
  ImportTaskView,
} from '@/api/maintenance/imports'
import type { MaintenanceClientError } from '@/api/maintenance/types'

export type ImportPhase =
  | 'idle'
  | 'selected'
  | 'uploaded'
  | 'previewed'
  | 'confirmed'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'expired'

export interface ImportWorkflowState {
  resourceKey: string
  generation: number
  phase: ImportPhase
  fileName: string | null
  mapping: ImportMapping
  task: ImportTaskUploadResult | ImportTaskView | null
  confirmed: boolean
  error: MaintenanceClientError | null
}

export type ImportEvent =
  | { type: 'FILE_SELECTED'; fileName: string }
  | { type: 'RESOURCE_CHANGED'; resourceKey: string }
  | { type: 'MAPPING_CHANGED'; mapping: ImportMapping }
  | {
    type: 'TASK_UPLOADED'
    generation: number
    task: ImportTaskUploadResult
  }
  | {
    type: 'TASK_UPDATED'
    generation: number
    taskId: string
    task: ImportTaskView
  }
  | { type: 'CONFIRMED' }
  | {
    type: 'REQUEST_FAILED'
    generation: number
    taskId?: string
    error: MaintenanceClientError
  }
  | { type: 'ERROR_CLEARED' }

const STATUS_PHASES: Record<string, ImportPhase> = {
  UPLOADED: 'uploaded',
  PREVIEW_VALID: 'previewed',
  PREVIEW_INVALID: 'previewed',
  QUEUED: 'queued',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  EXPIRED: 'expired',
}

const TERMINAL_STATUSES = new Set(['COMPLETED', 'FAILED', 'EXPIRED'])

export function isTerminalImportStatus(status: string): boolean {
  return TERMINAL_STATUSES.has(status.toUpperCase())
}

export function createImportState(resourceKey: string): ImportWorkflowState {
  return {
    resourceKey,
    generation: 0,
    phase: 'idle',
    fileName: null,
    mapping: {},
    task: null,
    confirmed: false,
    error: null,
  }
}

function phaseForStatus(status: string): ImportPhase {
  return STATUS_PHASES[status.toUpperCase()] ?? 'uploaded'
}

function matchesTaskUpdate(
  state: ImportWorkflowState,
  event: Extract<ImportEvent, { type: 'TASK_UPDATED' }>,
): boolean {
  return (
    state.task !== null
    && state.task.task_id === event.taskId
    && state.task.task_id === event.task.task_id
  )
}

function matchesFailureTarget(
  state: ImportWorkflowState,
  taskId: string | undefined,
): boolean {
  return state.task === null
    ? taskId === undefined
    : taskId !== undefined && state.task.task_id === taskId
}

function resetForNewFile(
  state: ImportWorkflowState,
  fileName: string,
): ImportWorkflowState {
  return {
    ...state,
    generation: state.generation + 1,
    phase: 'selected',
    fileName,
    mapping: {},
    task: null,
    confirmed: false,
    error: null,
  }
}

export function importReducer(
  state: ImportWorkflowState,
  event: ImportEvent,
): ImportWorkflowState {
  switch (event.type) {
    case 'FILE_SELECTED':
      return resetForNewFile(state, event.fileName)

    case 'RESOURCE_CHANGED':
      if (event.resourceKey === state.resourceKey) {
        return state
      }
      return {
        ...createImportState(event.resourceKey),
        generation: state.generation + 1,
      }

    case 'MAPPING_CHANGED':
      return { ...state, mapping: event.mapping, error: null }

    case 'TASK_UPLOADED':
      if (event.generation !== state.generation) {
        return state
      }
      return {
        ...state,
        phase: phaseForStatus(event.task.status),
        task: event.task,
        confirmed: false,
        error: null,
      }

    case 'TASK_UPDATED':
      if (
        event.generation !== state.generation
        || !matchesTaskUpdate(state, event)
      ) {
        return state
      }
      return {
        ...state,
        phase: phaseForStatus(event.task.status),
        task: event.task,
        confirmed: false,
        error: null,
      }

    case 'CONFIRMED':
      return canConfirmImport(state)
        ? { ...state, phase: 'confirmed', confirmed: true, error: null }
        : state

    case 'REQUEST_FAILED':
      if (
        event.generation !== state.generation
        || !matchesFailureTarget(state, event.taskId)
      ) {
        return state
      }
      return { ...state, error: event.error }

    case 'ERROR_CLEARED':
      return state.error === null ? state : { ...state, error: null }
  }
}

function isImportTaskView(
  task: ImportWorkflowState['task'],
): task is ImportTaskView {
  return task !== null && 'can_execute' in task
}

export function canConfirmImport(state: ImportWorkflowState): boolean {
  return state.phase === 'previewed' && state.error === null
}

export function canExecuteImport(state: ImportWorkflowState): boolean {
  return (
    state.phase === 'confirmed'
    && state.confirmed
    && state.error === null
    && isImportTaskView(state.task)
    && state.task.can_execute
  )
}
