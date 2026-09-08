import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, extname, relative, resolve } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import enUS from './en-US.ts'
import koKR from './ko-KR.ts'
import ruRU from './ru-RU.ts'
import zhCN from './zh-CN.ts'

type LocaleValue = string | Record<string, unknown> | unknown[]

function collectStrings(value: LocaleValue, path = ''): Array<{ path: string; value: string }> {
  if (typeof value === 'string') return [{ path, value }]
  if (Array.isArray(value)) {
    return value.flatMap((item, index) =>
      collectStrings(item as LocaleValue, `${path}[${index}]`),
    )
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, item]) =>
      collectStrings(item as LocaleValue, path ? `${path}.${key}` : key),
    )
  }
  return []
}

function withoutTechnicalTenantTokens(value: string): string {
  return value
    .replace(/\{tenant(?:Id)?\}/g, '')
    .replace(/\btenant_id\b/gi, '')
    .replace(/\btenantless\b/gi, '')
    .replace(/\bX-Tenant-ID\b/g, '')
}

const localeChecks = [
  { name: 'zh-CN', locale: zhCN, forbidden: /租户/ },
  { name: 'en-US', locale: enUS, forbidden: /\btenants?\b/i },
  { name: 'ko-KR', locale: koKR, forbidden: /테넌트/ },
  { name: 'ru-RU', locale: ruRU, forbidden: /(?:тенант|арендатор)/i },
]

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const publicDocumentationRoots = [
  '.env.example',
  'README_CN.md',
  'client',
  'docker-compose.yml',
  'docs',
  'mcp-server',
]
const documentationExtensions = new Set(['.go', '.json', '.md', '.yaml', '.yml'])
const excludedDocumentationDirectories = new Set(['docs/superpowers'])

function isSameOrDescendant(path: string, root: string): boolean {
  const relation = relative(root, path)
  return relation === '' || (!relation.startsWith('..') && !relation.includes(':'))
}

function collectDocumentationFiles(path: string): string[] {
  const entries = readdirSync(path, { withFileTypes: true })
  return entries.flatMap((entry) => {
    const child = resolve(path, entry.name)
    const repositoryRelativePath = child.slice(repositoryRoot.length + 1).replace(/\\/g, '/')
    if (entry.isDirectory()) {
      return excludedDocumentationDirectories.has(repositoryRelativePath)
        ? []
        : collectDocumentationFiles(child)
    }
    return documentationExtensions.has(extname(entry.name)) ? [child] : []
  })
}

test('documentation scanner excludes superpowers artifacts but keeps public API docs', () => {
  const documentationRoot = resolve(repositoryRoot, 'docs')
  const superpowersRoot = resolve(documentationRoot, 'superpowers')
  const apiRoot = resolve(documentationRoot, 'api')
  const documentationFiles = collectDocumentationFiles(documentationRoot)

  assert.equal(documentationFiles.some((file) => isSameOrDescendant(file, superpowersRoot)), false)
  assert.equal(documentationFiles.some((file) => isSameOrDescendant(file, apiRoot)), true)
  assert.equal(isSameOrDescendant(`${superpowersRoot}-sibling\\guide.md`, superpowersRoot), false)
  assert.equal(isSameOrDescendant(`${apiRoot}-sibling\\guide.md`, apiRoot), false)
})

test('user-facing locale values use workspace terminology', () => {
  for (const check of localeChecks) {
    const legacyValues = collectStrings(check.locale)
      .filter(({ value }) => check.forbidden.test(withoutTechnicalTenantTokens(value)))
      .map(({ path, value }) => `${check.name}:${path}=${value}`)

    assert.deepEqual(
      legacyValues,
      [],
      `${check.name} still contains user-facing tenant terminology`,
    )
  }
})

test('public documentation uses workspace terminology', () => {
  const legacyLines = publicDocumentationRoots.flatMap((relativePath) => {
    const absolutePath = resolve(repositoryRoot, relativePath)
    const files = extname(absolutePath) ? [absolutePath] : collectDocumentationFiles(absolutePath)
    return files.flatMap((file) =>
      readFileSync(file, 'utf8')
        .split('\n')
        .flatMap((line, index) =>
          line.includes('租户')
            ? [`${file.slice(repositoryRoot.length + 1)}:${index + 1}=${line.trim()}`]
            : [],
        ),
    )
  })

  assert.deepEqual(legacyLines, [], 'public documentation still contains legacy tenant terminology')
})
