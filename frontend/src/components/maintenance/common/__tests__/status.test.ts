import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  lifecycleLabel,
  lifecycleTheme,
  normalizeMaintenanceLocale,
  riskLabel,
  riskTheme,
  sourceLabel,
  sourceTheme,
} from '../status'

test('source labels preserve authority distinctions', () => {
  assert.deepEqual(
    [
      'USER_CONFIRMED',
      'USER_PROVIDED',
      'MASTER_DATA',
      'KNOWLEDGE_RETRIEVED',
      'SYSTEM_DEFAULT',
      'LLM_INFERRED',
    ].map((source) => sourceLabel(source, 'zh-CN')),
    [
      '人工确认',
      '用户录入',
      '主数据',
      '知识检索',
      '系统默认',
      '模型推断',
    ],
  )

  assert.equal(sourceLabel('LLM_INFERRED', 'en-US'), 'Model inferred')
  assert.equal(sourceTheme('USER_CONFIRMED'), 'success')
  assert.equal(sourceTheme('LLM_INFERRED'), 'warning')
})

test('risk labels and themes keep four severity levels distinct', () => {
  assert.equal(riskLabel('LOW', 'zh-CN'), '低')
  assert.equal(riskLabel('MEDIUM', 'en-US'), 'Medium')
  assert.equal(riskTheme('LOW'), 'success')
  assert.equal(riskTheme('MEDIUM'), 'warning')
  assert.equal(riskTheme('HIGH'), 'danger')
  assert.equal(riskTheme('BLOCKING'), 'danger')
})

test('lifecycle labels expose common maintenance states', () => {
  assert.equal(lifecycleLabel('ACTIVE', 'zh-CN'), '启用')
  assert.equal(lifecycleLabel('PENDING', 'en-US'), 'Pending')
  assert.equal(lifecycleLabel('COMPLETED', 'zh-CN'), '已完成')
  assert.equal(lifecycleTheme('ACTIVE'), 'success')
  assert.equal(lifecycleTheme('RUNNING'), 'primary')
  assert.equal(lifecycleTheme('FAILED'), 'danger')
})

test('unknown values remain visible instead of disappearing', () => {
  assert.equal(lifecycleLabel('CUSTOM_STATE', 'zh-CN'), 'CUSTOM_STATE')
  assert.equal(sourceLabel('ERP_IMPORT', 'en-US'), 'ERP_IMPORT')
  assert.equal(riskLabel('EXTREME', 'zh-CN'), 'EXTREME')
  assert.equal(lifecycleTheme('CUSTOM_STATE'), 'default')
})

test('locale normalization supports Chinese and safe English fallback', () => {
  assert.equal(normalizeMaintenanceLocale('zh-CN'), 'zh-CN')
  assert.equal(normalizeMaintenanceLocale('zh-Hans'), 'zh-CN')
  assert.equal(normalizeMaintenanceLocale('ko-KR'), 'en-US')
  assert.equal(normalizeMaintenanceLocale(undefined), 'en-US')
})

test('page header exposes separate primary and secondary action slots', () => {
  const path = fileURLToPath(
    new URL('../MaintenancePageHeader.vue', import.meta.url),
  )
  const source = readFileSync(path, 'utf8')

  assert.match(source, /<slot name="secondaryActions" \/>/)
  assert.match(source, /<slot name="primaryActions" \/>/)
})
