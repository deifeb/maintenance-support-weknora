import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createScenarioApi,
  type ScenarioDraftPayload,
} from '../scenarios.ts'
import type { MaintenanceResult } from '../types.ts'

const sampleDraft: ScenarioDraftPayload = {
  scenario_name: 'Thirty day readiness',
  current_step: 1,
  fields: {},
}

function result<T>(data: T): MaintenanceResult<T> {
  return {
    data,
    meta: {
      request_id: 'scenario-request',
      tenant_id: 'tenant-a',
    },
  }
}

test('scenario API uses exact draft and publish paths', async () => {
  const calls: Array<{
    method: string
    path: string
    body?: unknown
    config?: unknown
  }> = []
  const client = {
    async get<T>(path: string): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'GET', path })
      return result({} as T)
    },
    async post<T>(
      path: string,
      body: unknown,
      config?: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'POST', path, body, config })
      return result({} as T)
    },
    async put<T>(
      path: string,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      calls.push({ method: 'PUT', path, body })
      return result({} as T)
    },
  }
  const api = createScenarioApi(client)

  await api.getDraft(7)
  await api.saveDraft(7, {
    expected_version: 2,
    draft: sampleDraft,
  })
  await api.materialize(7, 2, 'materialize-key')
  await api.publishVersion(44)
  await api.listScenarios({
    page: 2,
    page_size: 20,
    keyword: 'night mission',
    include_inactive: false,
    sort_by: 'updated_at',
    sort_order: 'desc',
  })
  await api.getScenario(9)
  await api.listVersions(9)
  await api.getFullVersion(44)
  await api.updateVersion(44, {
    version_name: 'Reviewed draft',
  })
  await api.retireVersion(44)

  assert.deepEqual(
    calls.map(({ method, path }) => [method, path]),
    [
      ['GET', '/v1/demand/scenario-drafts/7'],
      ['PUT', '/v1/demand/scenario-drafts/7'],
      [
        'POST',
        '/v1/demand/scenario-drafts/7/materialize',
      ],
      [
        'POST',
        '/v1/demand/scenario-versions/44/publish',
      ],
      [
        'GET',
        '/v1/demand/scenarios?page=2&page_size=20&keyword=night+mission&include_inactive=false&sort_by=updated_at&sort_order=desc',
      ],
      ['GET', '/v1/demand/scenarios/9'],
      ['GET', '/v1/demand/scenarios/9/versions'],
      ['GET', '/v1/demand/scenario-versions/44/full'],
      ['PUT', '/v1/demand/scenario-versions/44'],
      ['POST', '/v1/demand/scenario-versions/44/retire'],
    ],
  )
  assert.deepEqual(calls[2]?.config, {
    headers: {
      'Idempotency-Key': 'materialize-key',
    },
  })
})

test('manual draft creation never forwards a tenant field', async () => {
  let sentBody: unknown
  const api = createScenarioApi({
    async get<T>(): Promise<MaintenanceResult<T>> {
      return result({} as T)
    },
    async put<T>(): Promise<MaintenanceResult<T>> {
      return result({} as T)
    },
    async post<T>(
      _path: string,
      body: unknown,
    ): Promise<MaintenanceResult<T>> {
      sentBody = body
      return result({} as T)
    },
  })

  await api.createDraft({
    title: 'Manual scenario',
    sensitivity_level: 'INTERNAL',
    tenant_id: 'must-not-leave-browser',
  } as never)

  assert.deepEqual(sentBody, {
    title: 'Manual scenario',
    sensitivity_level: 'INTERNAL',
  })
})
