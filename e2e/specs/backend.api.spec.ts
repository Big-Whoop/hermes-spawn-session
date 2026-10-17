// Backend-only e2e: the REST routes behind the desktop half, against a real
// `hermes serve` with this repo installed. No Desktop needed.
//
// Maps to the manual checklists of PR #5 / PR #7 and card t_787f6427:
// spawn (⌘K), proposal Start/Edit/Dismiss, child header, sidebar tree,
// status cards, report delivery, Abort, Detach, nested-spawn refusal (D10).
import { expect, test } from '@playwright/test'

import { readLogs, readState, type BackendState } from '../support/backend.js'
import { MOCK_MODEL_REF, PluginApi, hermesHelper, seedParent, uniqueTitle } from '../support/api.js'

test.describe.configure({ mode: 'serial' })

// Read lazily: the state file only exists after global setup (not for --list).
let state: BackendState
let api: PluginApi
test.beforeAll(() => {
  state = readState()
  api = new PluginApi(state)
})

async function spawnChild(parent: string, title = uniqueTitle('E2E child')) {
  const res = await api.post('/spawn', { session_id: parent, title, task: 'e2e task: reply OK', context: 'e2e context', model: MOCK_MODEL_REF })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  expect(res.body.ok).toBe(true)
  const child = { title, ...res.body } as { title: string; handover_id: string; child_session_id: string; status: string }
  await waitForChildRow(child.child_session_id)
  return child
}

/** The child's state.db row is persisted shortly after spawn (async seed turn); wait for it. */
async function waitForChildRow(childSessionId: string, timeoutMs = 30_000): Promise<void> {
  const end = Date.now() + timeoutMs
  let last = 'not yet'
  while (Date.now() < end) {
    const res = await api.get(`/defaults?session_id=${childSessionId}`)
    if (res.status === 200) return
    last = `HTTP ${res.status}`
    await new Promise(r => setTimeout(r, 1_000))
  }
  throw new Error(`child session row for ${childSessionId} not visible after ${timeoutMs} ms (${last})`)
}

test('plugin loads: no "Failed to load plugin" and routes are mounted', async () => {
  const logs = readLogs(state)
  expect(logs).not.toMatch(/Failed to load plugin spawn-session/)
  if (state.owned) expect(logs).toMatch(/Mounted plugin API routes: \/api\/plugins\/spawn-session\//)
  const tree = await api.get('/tree')
  expect(tree.status).toBe(200)
  expect(tree.body).toHaveProperty('children')
})

test('routes require the session token', async () => {
  const res = await fetch(`${state.url}/api/plugins/spawn-session/tree`)
  expect(res.status).toBe(401)
})

test('defaults: a desktop parent can spawn', async () => {
  const a = seedParent(state)
  const res = await api.get(`/defaults?session_id=${a}`)
  expect(res.status).toBe(200)
  expect(res.body).toMatchObject({ session_id: a, source: 'desktop', is_child: false, can_spawn: true })
})

test('defaults: unknown session is 404', async () => {
  const res = await api.get('/defaults?session_id=does-not-exist')
  expect(res.status).toBe(404)
})

test('⌘K spawn: validation errors are 400', async () => {
  const a = seedParent(state)
  const missingTitle = await api.post('/spawn', { session_id: a, title: '', task: 'x', model: MOCK_MODEL_REF })
  expect(missingTitle.status).toBe(400)
  const longTitle = await api.post('/spawn', { session_id: a, title: 'x'.repeat(81), task: 'x', model: MOCK_MODEL_REF })
  expect(longTitle.status).toBe(400)
  const badModel = await api.post('/spawn', { session_id: a, title: 't', task: 'x', model: 'no-provider' })
  expect(badModel.status).toBe(400)
  const badEffort = await api.post('/spawn', { session_id: a, title: 't', task: 'x', model: MOCK_MODEL_REF, effort: 'extreme' })
  expect(badEffort.status).toBe(400)
})

test('⌘K spawn: child starts, shows in status cards, tree and header', async () => {
  const a = seedParent(state, uniqueTitle('E2E parent A'))
  const b = await spawnChild(a)
  expect(b.status).toBe('running')
  expect(b.handover_id).toMatch(/^hs_/)

  const children = await api.get(`/children?session_id=${a}`)
  expect(children.status).toBe(200)
  const card = children.body.children.find((c: any) => c.handover_id === b.handover_id)
  expect(card).toMatchObject({ title: b.title, status: 'running', initiator: 'user', model: MOCK_MODEL_REF, child_session_id: b.child_session_id })
  expect(children.body.open_reports).toBe(0)

  // Sidebar badge source (↳ prefix / badge): child -> parent map.
  const tree = await api.get('/tree')
  expect(tree.body.children[b.child_session_id]).toMatchObject({ parent_session_id: a, handover_id: b.handover_id, status: 'running' })

  // Header in B: parent link, Task, Context.
  const header = await api.get(`/child?session_id=${b.child_session_id}`)
  expect(header.body).toMatchObject({ is_child: true, handover_id: b.handover_id, parent_session_id: a, task: 'e2e task: reply OK', context: 'e2e context', detached: false })
  expect(header.body.parent_title).toContain('E2E parent A')

  // A itself is not a child.
  const notChild = await api.get(`/child?session_id=${a}`)
  expect(notChild.body).toEqual({ is_child: false })
})

test('D10: nested spawn from B is refused', async () => {
  const a = seedParent(state)
  const b = await spawnChild(a)
  const defaults = await api.get(`/defaults?session_id=${b.child_session_id}`)
  expect(defaults.body).toMatchObject({ is_child: true, can_spawn: false })
  const nested = await api.post('/spawn', { session_id: b.child_session_id, title: 'nested', task: 'x', model: MOCK_MODEL_REF })
  expect(nested.status).toBe(400)
  expect(String(nested.body.detail)).toMatch(/not available in a spawned session/)
  // The agent path refuses too (tool contract: JSON, never raises).
  const viaTool = hermesHelper(state, ['propose', '--session-id', b.child_session_id, '--title', 'nested', '--task', 'x'])
  expect(viaTool.ok).toBe(false)
})

test('D13: a non-desktop parent cannot spawn', async () => {
  const res = hermesHelper(state, ['seed-parent', '--title', uniqueTitle('E2E cli parent'), '--cwd', state.projectDir, '--source', 'cli'])
  expect(res.ok).toBe(true)
  const defaults = await api.get(`/defaults?session_id=${res.stored_session_id}`)
  expect(defaults.body.can_spawn).toBe(false)
  const spawn = await api.post('/spawn', { session_id: res.stored_session_id, title: 't', task: 'x', model: MOCK_MODEL_REF })
  expect(spawn.status).toBe(400)
})

test('own_initiative proposal: card listed, Dismiss abandons it', async () => {
  const a = seedParent(state)
  const p = hermesHelper(state, ['propose', '--session-id', a, '--title', uniqueTitle('E2E proposal'), '--task', 'proposed task', '--model', MOCK_MODEL_REF])
  expect(p.ok, JSON.stringify(p)).toBe(true)
  expect(p.status).toBe('proposed')

  const list = await api.get(`/proposals?session_id=${a}`)
  expect(list.body.proposals.map((x: any) => x.handover_id)).toContain(p.handover_id)
  // Proposals are not status cards.
  const children = await api.get(`/children?session_id=${a}`)
  expect(children.body.children.map((x: any) => x.handover_id)).not.toContain(p.handover_id)

  const dismissed = await api.post('/dismiss', { handover_id: p.handover_id })
  expect(dismissed.status).toBe(200)
  expect(dismissed.body).toMatchObject({ ok: true, status: 'abandoned' })
  const after = await api.get(`/proposals?session_id=${a}`)
  expect(after.body.proposals.map((x: any) => x.handover_id)).not.toContain(p.handover_id)

  // Dismissing twice is refused.
  const again = await api.post('/dismiss', { handover_id: p.handover_id })
  expect(again.status).toBe(400)
})

test('own_initiative proposal: Edit + Start creates B with the edited fields', async () => {
  const a = seedParent(state)
  const p = hermesHelper(state, ['propose', '--session-id', a, '--title', uniqueTitle('E2E proposal'), '--task', 'original task', '--model', MOCK_MODEL_REF])
  expect(p.ok, JSON.stringify(p)).toBe(true)
  const edited = uniqueTitle('E2E edited')
  const started = await api.post('/confirm', { handover_id: p.handover_id, title: edited, task: 'edited task' })
  expect(started.status, JSON.stringify(started.body)).toBe(200)
  expect(started.body.child_session_id).toBeTruthy()

  const header = await api.get(`/child?session_id=${started.body.child_session_id}`)
  expect(header.body).toMatchObject({ is_child: true, title: edited, task: 'edited task' })
  const confirmAgain = await api.post('/confirm', { handover_id: p.handover_id })
  expect(confirmAgain.status).toBe(400)
})

test('report: B reports, A gets an open report or a delivered one', async () => {
  const a = seedParent(state)
  const b = await spawnChild(a)
  const rb = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'E2E child finished', '--open-item', 'parent: acknowledge'])
  expect(rb.ok, JSON.stringify(rb)).toBe(true)

  const children = await api.get(`/children?session_id=${a}`)
  const card = children.body.children.find((c: any) => c.handover_id === b.handover_id)
  expect(card.reports).toBeGreaterThanOrEqual(1)

  // "N open report(s) -> Deliver": always answers with the delivery summary.
  const deliver = await api.post('/deliver', { session_id: a })
  expect(deliver.status).toBe(200)
  expect(deliver.body).toHaveProperty('reports')
  expect(deliver.body).toHaveProperty('queued')
})

test('report_back outside a child session is refused', async () => {
  const a = seedParent(state)
  const rb = hermesHelper(state, ['report', '--session-id', a, '--result', 'not a child'])
  expect(rb.ok).toBe(false)
})

test('Abort: running child becomes abandoned', async () => {
  const a = seedParent(state)
  const b = await spawnChild(a)
  const res = await api.post('/abort', { handover_id: b.handover_id })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  expect(res.body.status).toBe('abandoned')
  const tree = await api.get('/tree')
  expect(tree.body.children[b.child_session_id]?.status).toBe('abandoned')
})

test('Detach: needs confirm=true, then the child is detached', async () => {
  const a = seedParent(state)
  const b = await spawnChild(a)
  const noConfirm = await api.post('/detach', { handover_id: b.handover_id })
  expect(noConfirm.status).toBe(400)
  expect(String(noConfirm.body.detail)).toMatch(/confirm=true/)

  const res = await api.post('/detach', { handover_id: b.handover_id, confirm: true })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  expect(res.body.status).toBe('detached')
  const header = await api.get(`/child?session_id=${b.child_session_id}`)
  expect(header.body).toMatchObject({ detached: true, status: 'detached' })
})

test('handover ids are validated (404 unknown, 400 path-like)', async () => {
  expect((await api.post('/abort', { handover_id: 'hs_does_not_exist' })).status).toBe(404)
  expect((await api.post('/abort', { handover_id: '../etc/passwd' })).status).toBe(400)
  expect((await api.post('/dismiss', { handover_id: '' })).status).toBe(400)
})
