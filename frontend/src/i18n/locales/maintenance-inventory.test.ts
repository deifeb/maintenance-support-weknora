import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import test from 'node:test'

function requiredUrl(relative: string): URL {
  const url = new URL(relative, import.meta.url)
  assert.equal(
    existsSync(url),
    true,
    `required inventory locale source is missing: ${relative}`,
  )
  return url
}

function deepKeys(value: unknown, prefix = ''): string[] {
  if (
    value === null
    || typeof value !== 'object'
    || Array.isArray(value)
  ) {
    return [prefix]
  }

  return Object.entries(value as Record<string, unknown>)
    .flatMap(([key, child]) => {
      const next = prefix ? `${prefix}.${key}` : key
      return deepKeys(child, next)
    })
    .sort()
}

test('maintenance inventory locale module has four-language recursive key parity', async () => {
  const localeUrl = requiredUrl('./maintenance-inventory.ts')
  const module = await import(localeUrl.href)
  const locales = module.maintenanceInventoryLocales as Record<string, unknown>

  assert.deepEqual(
    Object.keys(locales),
    ['en-US', 'zh-CN', 'ko-KR', 'ru-RU'],
  )

  const expected = deepKeys(locales['en-US'])
  assert.ok(expected.length > 0)
  for (const locale of ['zh-CN', 'ko-KR', 'ru-RU']) {
    assert.deepEqual(
      deepKeys(locales[locale]),
      expected,
      `maintenance inventory locale key mismatch for ${locale}`,
    )
  }
})

for (const locale of ['en-US', 'zh-CN', 'ko-KR', 'ru-RU'] as const) {
  test(`${locale} wires the modular inventory locale under maintenance.inventory`, () => {
    const localeSource = readFileSync(requiredUrl(`./${locale}.ts`), 'utf8')

    assert.match(localeSource, /maintenanceInventoryLocales/)
    assert.match(
      localeSource,
      new RegExp(
        `inventory\\s*:\\s*maintenanceInventoryLocales\\[['\"]${locale}['\"]\\]`,
      ),
    )
  })
}
