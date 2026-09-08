import type {
  ScenarioDraftPayload,
  ScenarioFieldState,
} from '../../../api/maintenance/scenarios'

export function draftField(
  draft: ScenarioDraftPayload,
  key: string,
): ScenarioFieldState {
  return draft.fields[key] ?? {
    value: null,
    source: 'SYSTEM_DEFAULT',
    confidence: null,
    risk: 'BLOCKING',
    confirmed: false,
    evidence_refs: [],
  }
}

export function userField(
  value: unknown,
  previous?: ScenarioFieldState,
): ScenarioFieldState {
  return {
    value,
    source: 'USER_INPUT',
    confidence: null,
    risk: previous?.risk ?? 'LOW',
    confirmed: true,
    evidence_refs: previous?.evidence_refs ?? [],
  }
}

export function confirmedField(
  previous: ScenarioFieldState,
): ScenarioFieldState {
  return {
    ...previous,
    confirmed: true,
  }
}
