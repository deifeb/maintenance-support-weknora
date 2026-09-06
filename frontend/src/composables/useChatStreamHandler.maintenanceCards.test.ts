import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const sourcePath = fileURLToPath(
  new URL('./useChatStreamHandler.ts', import.meta.url),
)
const source = readFileSync(sourcePath, 'utf8')

const sliceBetween = (
  startMarker: string,
  endMarker: string,
): string => {
  const start = source.indexOf(startMarker)
  assert.notEqual(start, -1, `missing start marker: ${startMarker}`)

  const end = source.indexOf(endMarker, start)
  assert.notEqual(end, -1, `missing end marker: ${endMarker}`)

  return source.slice(start, end)
}

test('chat stream handler imports the maintenance snapshot helper', () => {
  assert.match(
    source,
    /import\s*\{[^}]*applyMaintenanceCardSnapshot[^}]*\}\s*from\s*['"]@\/utils\/maintenanceCards['"]/s,
  )
})

test('history ingestion normalizes maintenance cards on the message row before insertion', () => {
  const block = sliceBetween(
    'const handleMsgList = async (',
    'const updateAssistantSession =',
  )

  const applyIndex = block.indexOf(
    'applyMaintenanceCardSnapshot(item, item.maintenance_cards)',
  )
  const pushIndex = block.indexOf('processed.push(item)')

  assert.notEqual(
    applyIndex,
    -1,
    'history ingestion must apply maintenance_cards to the message snapshot',
  )
  assert.notEqual(pushIndex, -1, 'history ingestion must still push the row')
  assert.ok(
    applyIndex < pushIndex,
    'maintenance_cards must be normalized before the history row is inserted',
  )
})

test('terminal complete replaces the same assistant message snapshot before turn completion', () => {
  const block = sliceBetween(
    "case 'complete': {",
    "case 'stop': {",
  )

  const applyIndex = block.indexOf(
    'applyMaintenanceCardSnapshot(message, dataPayload?.maintenance_cards)',
  )
  const completeCallbackIndex = block.indexOf('onTurnComplete?.(message)')

  assert.notEqual(
    applyIndex,
    -1,
    'complete must replace message.maintenance_cards from data.data.maintenance_cards',
  )
  assert.notEqual(
    completeCallbackIndex,
    -1,
    'complete must still invoke onTurnComplete with the assistant message',
  )
  assert.ok(
    applyIndex < completeCallbackIndex,
    'terminal cards must be on the message before onTurnComplete observes it',
  )
})

test('terminal replay resolves nested assistant_message_id before legacy fallbacks', () => {
  const block = sliceBetween(
    'const resolveActiveAssistantMessage = (data: ChatMessage) => {',
    'const applyKnowledgeReferences =',
  )

  const payloadDeclIndex = block.indexOf(
    'const dataPayload = data.data as ChatMessage | undefined',
  )
  const payloadIdIndex = block.indexOf(
    'const payloadAssistantId = dataPayload?.assistant_message_id as string | undefined',
  )
  const exactLookupIndex = block.indexOf(
    "item.role === 'assistant' && item.id === payloadAssistantId",
  )
  const legacyRootIndex = block.indexOf(
    '(data.assistant_message_id as string | undefined)',
  )
  const currentFallbackIndex = block.indexOf(
    'currentAssistantMessageId.value',
  )

  assert.notEqual(
    payloadDeclIndex,
    -1,
    'resolver must inspect terminal/replay data payload',
  )
  assert.notEqual(
    payloadIdIndex,
    -1,
    'resolver must read data.assistant_message_id from the nested payload',
  )
  assert.notEqual(
    exactLookupIndex,
    -1,
    'nested assistant_message_id must perform an exact message.id lookup',
  )
  assert.notEqual(
    legacyRootIndex,
    -1,
    'legacy root assistant_message_id fallback must remain supported',
  )
  assert.notEqual(
    currentFallbackIndex,
    -1,
    'current assistant id fallback must remain supported',
  )

  assert.ok(
    payloadIdIndex < exactLookupIndex,
    'nested assistant id must be read before its exact lookup',
  )
  assert.ok(
    exactLookupIndex < legacyRootIndex,
    'exact nested assistant id lookup must run before root/current fallbacks',
  )
  assert.ok(
    legacyRootIndex < currentFallbackIndex,
    'root assistant id must remain ahead of the mutable current-id fallback',
  )
})

test('agent chunk dispatch resolves the active assistant before it may create a row', () => {
  const start = source.indexOf(
    'const handleAgentChunk = (data: ChatMessage) => {',
  )
  assert.notEqual(start, -1, 'handleAgentChunk must exist')

  const switchIndex = source.indexOf('switch (responseType)', start)
  assert.notEqual(
    switchIndex,
    -1,
    'handleAgentChunk response switch must exist',
  )

  const setup = source.slice(start, switchIndex)

  const resolveIndex = setup.indexOf(
    'let message = resolveActiveAssistantMessage(data)',
  )
  const createIndex = setup.indexOf('if (!message) {')

  assert.notEqual(
    resolveIndex,
    -1,
    'handleAgentChunk must select its message through the exact-aware resolver',
  )
  assert.notEqual(
    createIndex,
    -1,
    'handleAgentChunk must retain the existing create-if-missing behavior',
  )
  assert.ok(
    resolveIndex < createIndex,
    'exact-aware resolution must happen before any synthetic assistant row can be created',
  )

  assert.doesNotMatch(
    setup,
    /let message = findLastMessage\(\s*\(item\) => item\.request_id === dataId \|\| item\.id === dataId,\s*\)/s,
    'handleAgentChunk must not bypass the exact-aware resolver with its legacy direct lookup',
  )
})
