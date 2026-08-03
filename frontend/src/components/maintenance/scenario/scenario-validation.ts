import type {
  ScenarioDraftPayload,
  ScenarioFieldState,
} from '../../../api/maintenance/scenarios'

export type WizardStepKey =
  | 'basics'
  | 'configuration'
  | 'mission'
  | 'reliabilityRepair'
  | 'calculation'
  | 'confirmation'

export interface WizardStepDefinition {
  key: WizardStepKey
  number: number
  requiredFields: readonly string[]
}

export const WIZARD_STEPS: readonly WizardStepDefinition[] = [
  {
    key: 'basics',
    number: 1,
    requiredFields: [
      'scenario_name',
      'mission_code',
      'start_at',
      'end_at',
      'priority',
    ],
  },
  {
    key: 'configuration',
    number: 2,
    requiredFields: [
      'equipment_model_id',
      'configuration_version_id',
      'fleet_groups',
    ],
  },
  {
    key: 'mission',
    number: 3,
    requiredFields: ['stages'],
  },
  {
    key: 'reliabilityRepair',
    number: 4,
    requiredFields: ['reliability_profiles'],
  },
  {
    key: 'calculation',
    number: 5,
    requiredFields: [
      'service_level',
      'execution_preference',
      'missing_parameter_policy',
    ],
  },
  {
    key: 'confirmation',
    number: 6,
    requiredFields: [],
  },
] as const

export interface WizardEvaluation {
  completion: Record<WizardStepKey, boolean>
  blockingFields: string[]
  canMaterialize: boolean
}

function hasValue(value: unknown): boolean {
  if (value === null || value === undefined) {
    return false
  }
  if (typeof value === 'string') {
    return value.trim().length > 0
  }
  if (Array.isArray(value)) {
    return value.length > 0
  }
  if (typeof value === 'object') {
    return Object.keys(value).length > 0
  }
  return true
}

function fieldValue(
  draft: ScenarioDraftPayload,
  fieldName: string,
): unknown {
  if (fieldName === 'scenario_name') {
    return draft.scenario_name
  }
  return draft.fields[fieldName]?.value
}

function isUnconfirmedBlocking(
  field: ScenarioFieldState | undefined,
): boolean {
  return (
    field?.risk === 'BLOCKING'
    && !field.confirmed
  )
}

export function evaluateWizard(
  draft: ScenarioDraftPayload,
): WizardEvaluation {
  const blocking = new Set<string>()
  const completion = {} as Record<
    WizardStepKey,
    boolean
  >

  for (const step of WIZARD_STEPS) {
    if (step.key === 'confirmation') {
      continue
    }
    const missing = step.requiredFields.filter(
      (fieldName) => !hasValue(
        fieldValue(draft, fieldName),
      ),
    )
    for (const fieldName of missing) {
      blocking.add(fieldName)
    }
    completion[step.key] = missing.length === 0
  }

  for (
    const [fieldName, field]
    of Object.entries(draft.fields)
  ) {
    if (isUnconfirmedBlocking(field)) {
      blocking.add(fieldName)
    }
  }

  const blockingFields = [...blocking].sort()
  completion.confirmation = (
    blockingFields.length === 0
  )

  return {
    completion,
    blockingFields,
    canMaterialize: (
      blockingFields.length === 0
    ),
  }
}

export function canNavigateToStep(
  target: WizardStepKey,
  completion: Record<WizardStepKey, boolean>,
): boolean {
  const targetIndex = WIZARD_STEPS.findIndex(
    (step) => step.key === target,
  )
  if (targetIndex <= 0) return true
  return WIZARD_STEPS
    .slice(0, targetIndex)
    .every((step) => completion[step.key])
}
