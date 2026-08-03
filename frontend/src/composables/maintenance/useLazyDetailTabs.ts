import { reactive } from 'vue'

import { normalizeMaintenanceError } from '../../api/maintenance/client'
import type { MaintenanceClientError } from '../../api/maintenance/types'

export type DetailTabStatus =
  | 'idle'
  | 'loading'
  | 'loaded'
  | 'error'
  | 'unavailable'

export interface DetailTabState<T = unknown> {
  status: DetailTabStatus
  data: T | null
  error: MaintenanceClientError | null
}

export interface LazyDetailTabs<TTab extends string> {
  state(tab: TTab): Readonly<DetailTabState>
  activate(tab: TTab): Promise<void>
  retry(tab: TTab): Promise<void>
  invalidate(tab: TTab): void
  reset(): void
}

type DetailTabLoader = () => Promise<unknown>

function reactiveState(
  status: DetailTabStatus,
): DetailTabState {
  return reactive({
    status,
    data: null,
    error: null,
  }) as DetailTabState
}

export function createLazyDetailTabs<TTab extends string>(
  loaders: Partial<Record<TTab, DetailTabLoader>>,
  unavailableTabs: readonly TTab[] = [],
): LazyDetailTabs<TTab> {
  const unavailable = new Set<TTab>(unavailableTabs)
  const knownTabs = new Set<TTab>([
    ...(Object.keys(loaders) as TTab[]),
    ...unavailableTabs,
  ])
  const states = new Map<TTab, DetailTabState>()
  const requestTokens = new Map<TTab, number>()
  const pending = new Map<TTab, Promise<void>>()
  let generation = 0

  function initialStatus(tab: TTab): DetailTabStatus {
    return unavailable.has(tab) || !loaders[tab]
      ? 'unavailable'
      : 'idle'
  }

  function ensureState(tab: TTab): DetailTabState {
    knownTabs.add(tab)

    const existing = states.get(tab)
    if (existing) {
      return existing
    }

    const created = reactiveState(initialStatus(tab))
    states.set(tab, created)
    return created
  }

  function replaceState(
    tab: TTab,
    status: DetailTabStatus,
    data: unknown = null,
    error: MaintenanceClientError | null = null,
  ): void {
    const target = ensureState(tab)
    target.status = status
    target.data = data
    target.error = error
  }

  async function load(
    tab: TTab,
    retrying: boolean,
  ): Promise<void> {
    const current = ensureState(tab)
    const loader = loaders[tab]

    if (current.status === 'unavailable' || !loader) {
      replaceState(tab, 'unavailable')
      return
    }

    if (current.status === 'loading') {
      await pending.get(tab)
      return
    }

    if (!retrying && current.status !== 'idle') {
      return
    }

    if (retrying && current.status !== 'error') {
      return
    }

    const requestGeneration = generation
    const requestToken = (requestTokens.get(tab) ?? 0) + 1
    requestTokens.set(tab, requestToken)
    replaceState(tab, 'loading')

    let task!: Promise<void>
    task = (async () => {
      try {
        const data = await loader()

        if (
          generation !== requestGeneration
          || requestTokens.get(tab) !== requestToken
        ) {
          return
        }

        replaceState(tab, 'loaded', data)
      } catch (error) {
        if (
          generation !== requestGeneration
          || requestTokens.get(tab) !== requestToken
        ) {
          return
        }

        replaceState(
          tab,
          'error',
          null,
          normalizeMaintenanceError(error),
        )
      } finally {
        if (pending.get(tab) === task) {
          pending.delete(tab)
        }
      }
    })()

    pending.set(tab, task)
    await task
  }

  return {
    state(tab: TTab): Readonly<DetailTabState> {
      return ensureState(tab)
    },

    async activate(tab: TTab): Promise<void> {
      await load(tab, false)
    },

    async retry(tab: TTab): Promise<void> {
      await load(tab, true)
    },

    invalidate(tab: TTab): void {
      requestTokens.set(
        tab,
        (requestTokens.get(tab) ?? 0) + 1,
      )
      pending.delete(tab)
      replaceState(tab, initialStatus(tab))
    },

    reset(): void {
      generation += 1
      pending.clear()
      requestTokens.clear()

      for (const tab of knownTabs) {
        replaceState(tab, initialStatus(tab))
      }
    },
  }
}
