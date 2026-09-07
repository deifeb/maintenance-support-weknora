import { reactive } from 'vue'

// Report ownership survives child and route unmounts while a request is in flight.
export const pendingReportMutations = reactive(new Set<number>())
const readers = new Map<number, Set<() => Promise<void>>>()

export function registerReportReader(reportId: number, read: () => Promise<void>): () => void {
  const current = readers.get(reportId) ?? new Set()
  current.add(read)
  readers.set(reportId, current)
  return () => {
    current.delete(read)
    if (current.size === 0) readers.delete(reportId)
  }
}

export async function refreshReportReaders(reportId: number, fallback: () => Promise<void>): Promise<void> {
  const current = readers.get(reportId)
  await Promise.all(current?.size ? [...current].map((read) => read()) : [fallback()])
}

export async function runReportMutation(reportId: number, operation: () => Promise<void>): Promise<void> {
  if (pendingReportMutations.has(reportId)) return
  pendingReportMutations.add(reportId)
  try { await operation() } finally { pendingReportMutations.delete(reportId) }
}
