import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const botmsgPath = fileURLToPath(
  new URL('./botmsg.vue', import.meta.url),
)
const source = readFileSync(botmsgPath, 'utf8')

const templateStart = source.indexOf('<template>')
const templateEnd = source.indexOf('<script setup>')
assert.notEqual(templateStart, -1, 'botmsg template start must exist')
assert.notEqual(templateEnd, -1, 'botmsg script boundary must exist')

const template = source.slice(templateStart, templateEnd)

test('botmsg imports the maintenance business card host', () => {
  assert.match(
    source,
    /import\s+MaintenanceBusinessCardHost\s+from\s+['"]@\/components\/maintenance\/chat\/MaintenanceBusinessCardHost\.vue['"]/,
  )
})

test('botmsg mounts exactly one maintenance card host from session maintenance_cards', () => {
  const hostTags = template.match(/<MaintenanceBusinessCardHost\b/g) ?? []

  assert.equal(
    hostTags.length,
    1,
    'botmsg must mount exactly one maintenance card host',
  )

  assert.match(
    template,
    /<MaintenanceBusinessCardHost[\s\S]*?:cards\s*=\s*["']session\?\.maintenance_cards["'][\s\S]*?\/>/,
  )
})

test('maintenance card host is placed after both agent and markdown answer renderers', () => {
  const hostIndex = template.indexOf('<MaintenanceBusinessCardHost')
  const agentIndex = template.lastIndexOf('<AgentStreamDisplay')
  const markdownIndex = template.indexOf('class="ai-markdown-template markdown-content"')

  assert.notEqual(hostIndex, -1, 'maintenance card host must exist')
  assert.notEqual(agentIndex, -1, 'agent renderer marker must exist')
  assert.notEqual(markdownIndex, -1, 'markdown renderer marker must exist')

  assert.ok(
    hostIndex > agentIndex,
    'maintenance cards must render after the agent answer renderer',
  )
  assert.ok(
    hostIndex > markdownIndex,
    'maintenance cards must render after the markdown answer renderer',
  )
})
