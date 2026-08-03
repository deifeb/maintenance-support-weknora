export type MaintenanceLocale = 'zh-CN' | 'en-US'

export type MaintenanceTagTheme =
  | 'default'
  | 'primary'
  | 'success'
  | 'warning'
  | 'danger'

type LocalizedLabels = Record<MaintenanceLocale, string>

const SOURCE_LABELS: Record<string, LocalizedLabels> = {
  USER_CONFIRMED: {
    'zh-CN': '人工确认',
    'en-US': 'User confirmed',
  },
  USER_PROVIDED: {
    'zh-CN': '用户录入',
    'en-US': 'User provided',
  },
  MASTER_DATA: {
    'zh-CN': '主数据',
    'en-US': 'Master data',
  },
  KNOWLEDGE_RETRIEVED: {
    'zh-CN': '知识检索',
    'en-US': 'Retrieved evidence',
  },
  SYSTEM_DEFAULT: {
    'zh-CN': '系统默认',
    'en-US': 'System default',
  },
  LLM_INFERRED: {
    'zh-CN': '模型推断',
    'en-US': 'Model inferred',
  },
}

const RISK_LABELS: Record<string, LocalizedLabels> = {
  LOW: {
    'zh-CN': '低',
    'en-US': 'Low',
  },
  MEDIUM: {
    'zh-CN': '中',
    'en-US': 'Medium',
  },
  HIGH: {
    'zh-CN': '高',
    'en-US': 'High',
  },
  BLOCKING: {
    'zh-CN': '阻断',
    'en-US': 'Blocking',
  },
}

const LIFECYCLE_LABELS: Record<string, LocalizedLabels> = {
  ACTIVE: {
    'zh-CN': '启用',
    'en-US': 'Active',
  },
  INACTIVE: {
    'zh-CN': '停用',
    'en-US': 'Inactive',
  },
  DRAFT: {
    'zh-CN': '草稿',
    'en-US': 'Draft',
  },
  PENDING: {
    'zh-CN': '待处理',
    'en-US': 'Pending',
  },
  RUNNING: {
    'zh-CN': '运行中',
    'en-US': 'Running',
  },
  APPROVED: {
    'zh-CN': '已批准',
    'en-US': 'Approved',
  },
  REJECTED: {
    'zh-CN': '已拒绝',
    'en-US': 'Rejected',
  },
  COMPLETED: {
    'zh-CN': '已完成',
    'en-US': 'Completed',
  },
  FAILED: {
    'zh-CN': '失败',
    'en-US': 'Failed',
  },
  CANCELLED: {
    'zh-CN': '已取消',
    'en-US': 'Cancelled',
  },
  ARCHIVED: {
    'zh-CN': '已归档',
    'en-US': 'Archived',
  },
}

function normalizedCode(value: string): string {
  return value.trim().toUpperCase()
}

function localizedLabel(
  labels: Record<string, LocalizedLabels>,
  value: string,
  locale?: string,
): string {
  const code = normalizedCode(value)
  return labels[code]?.[normalizeMaintenanceLocale(locale)] ?? value
}

export function normalizeMaintenanceLocale(
  locale?: string,
): MaintenanceLocale {
  return locale?.toLowerCase().startsWith('zh')
    ? 'zh-CN'
    : 'en-US'
}

export function sourceLabel(
  source: string,
  locale?: string,
): string {
  return localizedLabel(SOURCE_LABELS, source, locale)
}

export function sourceTheme(
  source: string,
): MaintenanceTagTheme {
  switch (normalizedCode(source)) {
    case 'USER_CONFIRMED':
      return 'success'
    case 'USER_PROVIDED':
    case 'KNOWLEDGE_RETRIEVED':
      return 'primary'
    case 'LLM_INFERRED':
      return 'warning'
    default:
      return 'default'
  }
}

export function riskLabel(
  risk: string,
  locale?: string,
): string {
  return localizedLabel(RISK_LABELS, risk, locale)
}

export function riskTheme(
  risk: string,
): MaintenanceTagTheme {
  switch (normalizedCode(risk)) {
    case 'LOW':
      return 'success'
    case 'MEDIUM':
      return 'warning'
    case 'HIGH':
    case 'BLOCKING':
      return 'danger'
    default:
      return 'default'
  }
}

export function lifecycleLabel(
  status: string,
  locale?: string,
): string {
  return localizedLabel(LIFECYCLE_LABELS, status, locale)
}

export function lifecycleTheme(
  status: string,
): MaintenanceTagTheme {
  switch (normalizedCode(status)) {
    case 'ACTIVE':
    case 'APPROVED':
    case 'COMPLETED':
      return 'success'
    case 'PENDING':
    case 'RUNNING':
      return 'primary'
    case 'REJECTED':
    case 'FAILED':
      return 'danger'
    case 'CANCELLED':
      return 'warning'
    default:
      return 'default'
  }
}
