// Backend-only e2e: the REST routes behind the desktop half, against a real
// `hermes serve` with this repo installed. No Desktop needed.
//
// Maps to the manual checklists of PR #5 / PR #7 and card t_787f6427:
// spawn (⌘K), proposal Start/Edit/Dismiss, child header, sidebar tree,
// status cards, report delivery, Abort, Detach, nested-spawn refusal (D10).
import { expect, test } from '@playwright/test'

import { spawnSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'

import { readLogs, readState, type BackendState } from '../support/backend.js'
import {
  MOCK_MODEL_REF, PRICEY_MODEL_REF, PluginApi, hermesHelper, mockRequests, mockScript, seedParent,
  storedSession, toolCallReply, uniqueTitle, waitFor
} from '../support/api.js'
import { GatewayClient } from '../support/gateway.js'

test.describe.configure({ mode: 'serial' })

// Read lazily: the state file only exists after global setup (not for --list).
let state: BackendState
let api: PluginApi
let gw: GatewayClient
test.beforeAll(async () => {
  state = readState()
  api = new PluginApi(state)
  gw = await new GatewayClient(state).open()
})
test.afterAll(() => gw?.close())

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
  // AT7.3: retitled B, report_back and nested spawn refused afterwards.
  expect(res.body.title_set).toBe(true)
  expect(storedSession(state, b.child_session_id).title).toBe(`↳ Detached: ${b.title}`)
  const rb = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'after detach'])
  expect(rb.ok).toBe(false)
  expect(rb.error).toMatch(/detached/)
  expect(hermesHelper(state, ['propose', '--session-id', b.child_session_id, '--title', 'nested', '--task', 'x']).ok).toBe(false)
})

test('handover ids are validated (404 unknown, 400 path-like)', async () => {
  expect((await api.post('/abort', { handover_id: 'hs_does_not_exist' })).status).toBe(404)
  expect((await api.post('/abort', { handover_id: '../etc/passwd' })).status).toBe(400)
  expect((await api.post('/dismiss', { handover_id: '' })).status).toBe(400)
})

// ---------------------------------------------------------------------------
// Completeness: every backend-reachable acceptance test of docs/at-matrix.md.
// Flow tests keep sessions live in the serve's gateway through the same /api/ws
// socket the Desktop uses (GatewayClient), and script agent turns on the mock
// LLM. Every title carries its AT id.

function git(cwd: string, ...args: string[]): string {
  const r = spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' })
  if (r.status !== 0) throw new Error(`git ${args.join(' ')} failed in ${cwd}: ${r.stderr}`)
  return r.stdout.trim()
}

async function card(parent: string, handoverId: string): Promise<any> {
  const res = await api.get(`/children?session_id=${parent}`)
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  return res.body.children.find((c: any) => c.handover_id === handoverId)
}

async function cardStatus(parent: string, handoverId: string, status: string, timeoutMs = 60_000): Promise<any> {
  return waitFor(`${handoverId} status ${status}`, async () => {
    const c = await card(parent, handoverId)
    return c?.status === status ? c : null
  }, timeoutMs)
}

/** A desktop parent A that is live in the serve's gateway. */
async function liveParent(title = uniqueTitle('E2E live A')): Promise<{ a: string; aRun: string }> {
  const a = seedParent(state, title)
  return { a, aRun: await gw.resume(a) }
}

/** User messages of a stored session that start with ``prefix``. */
function userMessages(sessionId: string, prefix: string): string[] {
  return storedSession(state, sessionId).messages.filter(m => m.role === 'user' && m.content.startsWith(prefix)).map(m => m.content)
}

async function waitForUserMessage(sessionId: string, prefix: string, count = 1, timeoutMs = 60_000): Promise<string[]> {
  return waitFor(`${count} user message(s) "${prefix}" in ${sessionId}`, () => {
    const found = userMessages(sessionId, prefix)
    return found.length >= count ? found : null
  }, timeoutMs)
}

/** B's agent calls report_back in a real turn (mock-scripted tool call). */
async function reportFromB(bRun: string, result: string): Promise<void> {
  const trigger = `e2e-report-trigger ${uniqueTitle('r')}`
  await mockScript(state, [toolCallReply(trigger, 'report_back', { result, open_items: ['parent: acknowledge'] })])
  await gw.submit(bRun, trigger)
}

test('AT2.3 cost rule: a more expensive model is a proposal, Start creates B; the same model starts at once', async () => {
  const a = seedParent(state)
  const pricey = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle('E2E pricey'), '--task', 'x', '--model', PRICEY_MODEL_REF])
  expect(pricey.ok, JSON.stringify(pricey)).toBe(true)
  expect(pricey.status).toBe('proposed')
  expect(pricey.child_session_id).toBeNull()
  expect(pricey.confirmation_required.join(' ')).toMatch(/more expensive than the parent's custom:mock-e2e/)

  const list = await api.get(`/proposals?session_id=${a}`)
  const proposal = list.body.proposals.find((p: any) => p.handover_id === pricey.handover_id)
  expect(proposal).toMatchObject({ model: PRICEY_MODEL_REF, initiation: 'user_asked' })
  expect(proposal.reasons.join(' ')).toMatch(/more expensive/)

  const started = await api.post('/confirm', { handover_id: pricey.handover_id })
  expect(started.status, JSON.stringify(started.body)).toBe(200)
  expect(started.body).toMatchObject({ status: 'running' })
  expect(started.body.child_session_id).toBeTruthy()

  // Negative control: the parent's own (ranked) model starts immediately.
  const same = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle('E2E same model'), '--task', 'x', '--model', MOCK_MODEL_REF])
  expect(same.ok, JSON.stringify(same)).toBe(true)
  expect(same.status).toBe('running')
})

test('AT2.5 worktree: true creates spawn/<slug> and B\'s cwd is the worktree (tool and ⌘K)', async () => {
  const a = seedParent(state)
  // Agent tool path.
  const viaTool = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle('E2E wt tool'), '--task', 'x', '--model', MOCK_MODEL_REF, '--worktree'])
  expect(viaTool.ok, JSON.stringify(viaTool)).toBe(true)
  // ⌘K path (REST, in the serve).
  const title = uniqueTitle('E2E wt rest')
  const viaRest = await api.post('/spawn', { session_id: a, title, task: 'x', model: MOCK_MODEL_REF, worktree: true })
  expect(viaRest.status, JSON.stringify(viaRest.body)).toBe(200)
  await waitForChildRow(viaRest.body.child_session_id)

  for (const res of [viaTool, viaRest.body]) {
    const c = await card(a, res.handover_id)
    expect(c.worktree, JSON.stringify(c)).toBeTruthy()
    const slug = String(c.worktree.branch).replace(/^spawn\//, '')
    expect(c.worktree.branch).toBe(`spawn/${slug}`)
    expect(c.worktree.path).toBe(path.join(state.projectDir, '.worktrees', `spawn-${slug}`))
    expect(fs.existsSync(c.worktree.path)).toBe(true)
    expect(git(state.projectDir, 'branch', '--list', c.worktree.branch)).toContain(c.worktree.branch)
    expect(git(c.worktree.path, 'rev-parse', '--abbrev-ref', 'HEAD')).toBe(c.worktree.branch)
    expect(fs.readFileSync(c.handover_path, 'utf8')).toContain(`cwd: ${c.worktree.path}`)
  }
  // B's session row (created by the serve on the ⌘K path) runs in the worktree.
  // The tool path above ran in the short-lived helper process, which exits
  // before B's first turn persists its row; its cwd is checked in the handover.
  const restCard = await card(a, viaRest.body.handover_id)
  expect(storedSession(state, viaRest.body.child_session_id).cwd).toBe(restCard.worktree.path)
})

test('AT2.6 allowed_toolsets: B is narrowed (guard blocks a foreign tool), spawn-session is stripped', async () => {
  // A's agent calls spawn_session in a real turn in the serve.
  const { a, aRun } = await liveParent()
  const title = uniqueTitle('E2E narrowed')
  const trigger = `e2e-spawn-narrowed ${title}`
  await mockScript(state, [
    toolCallReply(trigger, 'spawn_session', { title, task: 'narrowed task', initiation: 'user_asked', model: MOCK_MODEL_REF, allowed_toolsets: ['file', 'spawn-session'] }),
    { match: trigger, text: 'spawned' }
  ])
  await gw.submit(aRun, trigger)
  const c = await waitFor('narrowed child card', async () => {
    const res = await api.get(`/children?session_id=${a}`)
    return res.body.children.find((x: any) => x.title === title && x.child_session_id) ?? null
  })
  const handover = fs.readFileSync(c.handover_path, 'utf8')
  const toolsets = handover.match(/allowed_toolsets:\n((?:\s*- .+\n)+)/)?.[1] ?? ''
  expect(toolsets).toMatch(/- file/)
  expect(toolsets).not.toMatch(/spawn-session/)

  // A real agent turn in B tries a tool outside the narrowed set.
  await waitForChildRow(c.child_session_id)
  const bRun = await gw.resume(c.child_session_id)
  const probe = `e2e-narrowed-probe ${title}`
  await mockScript(state, [{ match: probe, tool: 'terminal', arguments: { command: 'echo should-not-run' } }, { match: probe, text: 'ok' }])
  await gw.submit(bRun, probe)
  await waitFor('guard message in a tool result', async () => {
    const reqs = await mockRequests(state)
    return reqs.some(r => JSON.stringify(r.messages ?? []).includes("is not in this session's allowed_toolsets"))
  })

  // Unknown toolset names are rejected.
  const unknown = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle('E2E bad ts'), '--task', 'x', '--model', MOCK_MODEL_REF, '--allowed-toolset', 'teleport'])
  expect(unknown.ok).toBe(false)
  expect(unknown.error).toMatch(/unknown toolset/)
})

test('AT2.6 allowed_toolsets: a superset of A\'s toolsets is rejected, a narrowing is accepted', async () => {
  // A's toolsets are pinned to file + web via the gateway's operator pin
  // (HERMES_TUI_TOOLSETS); the helper's in-process gateway answers tools.list
  // for A from it, exactly as the serve does for a live session.
  const a = seedParent(state)
  const pin = { HERMES_TUI_TOOLSETS: 'file,web' }
  const spawn = (title: string, ...toolsets: string[]) => hermesHelper(state, [
    'spawn', '--session-id', a, '--title', uniqueTitle(title), '--task', 'x', '--model', MOCK_MODEL_REF,
    ...toolsets.flatMap(t => ['--allowed-toolset', t])
  ], pin)

  const superset = spawn('E2E superset', 'file', 'terminal')
  expect(superset.ok, JSON.stringify(superset)).toBe(false)
  expect(superset.error).toMatch(/exceeds the parent session's toolsets: terminal/)

  const narrowed = spawn('E2E narrowing', 'file', 'spawn-session')
  expect(narrowed.ok, JSON.stringify(narrowed)).toBe(true)
  const toolsets = fs.readFileSync(narrowed.handover_path, 'utf8').match(/allowed_toolsets:\n((?:\s*- .+\n)+)/)?.[1] ?? ''
  expect(toolsets).toMatch(/- file/)
  expect(toolsets).not.toMatch(/spawn-session/)
})

test('AT3.2 D10 cap: the 4th running agent spawn is a "limit reached" proposal, ⌘K spawns are not capped', async () => {
  const a = seedParent(state)
  for (let i = 1; i <= 3; i++) {
    const r = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle(`E2E cap ${i}`), '--task', 'x', '--model', MOCK_MODEL_REF])
    expect(r.ok, JSON.stringify(r)).toBe(true)
    expect(r.status).toBe('running')
  }
  const fourth = hermesHelper(state, ['spawn', '--session-id', a, '--title', uniqueTitle('E2E cap 4'), '--task', 'x', '--model', MOCK_MODEL_REF])
  expect(fourth.ok, JSON.stringify(fourth)).toBe(true)
  expect(fourth.status).toBe('proposed')
  const proposal = (await api.get(`/proposals?session_id=${a}`)).body.proposals.find((p: any) => p.handover_id === fourth.handover_id)
  expect(proposal.reasons.join(' ')).toMatch(/limit reached/)

  for (let i = 1; i <= 2; i++) {
    const b = await spawnChild(a, uniqueTitle(`E2E user ${i}`))
    expect(b.status).toBe('running')
  }
})

test('AT4.2 report to an idle live A is delivered and A runs a mock-LLM turn on it', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)
  await reportFromB(bRun, 'AT4.2 child finished')
  await cardStatus(a, b.handover_id, 'delivered')
  const marker = `[spawn-session report: ${b.title} (${b.handover_id})]`
  await waitForUserMessage(a, marker)
  const reqs = await mockRequests(state)
  expect(reqs.some(r => JSON.stringify(r.messages ?? []).includes(marker.replace(/[[\]]/g, '')))).toBe(true)
})

test('AT4.3 report while A is mid-turn stays reported and is delivered as A\'s next turn', async () => {
  const { a, aRun } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)
  const slow = `e2e-slow-turn ${uniqueTitle('s')}`
  await mockScript(state, [{ match: slow, text: 'slow turn done', delayMs: 20_000 }])
  await gw.submit(aRun, slow)
  await waitFor('A\'s slow turn reached the mock', async () => (await mockRequests(state)).some(r => JSON.stringify(r.messages ?? []).includes(slow)))

  await reportFromB(bRun, 'AT4.3 child finished')
  const during = await waitFor('report appended', async () => { const c = await card(a, b.handover_id); return c?.reports >= 1 ? c : null })
  expect(during.status).toBe('reported') // A is still busy

  await cardStatus(a, b.handover_id, 'delivered', 90_000)
  const msgs = storedSession(state, a).messages
  const iSlow = msgs.findIndex(m => m.role === 'user' && m.content.startsWith(slow))
  const iDone = msgs.findIndex(m => m.role === 'assistant' && m.content.includes('slow turn done'))
  const iReport = msgs.findIndex(m => m.role === 'user' && m.content.startsWith(`[spawn-session report: ${b.title}`))
  expect(iSlow, JSON.stringify(msgs.map(m => [m.role, m.content.slice(0, 60)]))).toBeGreaterThanOrEqual(0)
  expect(iDone).toBeGreaterThan(iSlow) // A's turn was not interrupted
  expect(iReport).toBeGreaterThan(iDone) // the report is a separate, later turn
})

test('AT4.4 A not live: report stays reported, reopen + Deliver delivers', async () => {
  const a = seedParent(state) // never resumed in the serve: not live
  const b = await spawnChild(a)
  const rb = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'AT4.4 child finished'])
  expect(rb.ok, JSON.stringify(rb)).toBe(true)
  expect(rb.delivery).toBe('pending')

  const before = await api.get(`/children?session_id=${a}`)
  expect(before.body.open_reports).toBe(1)
  expect((await card(a, b.handover_id)).status).toBe('reported')
  const notLive = await api.post('/deliver', { session_id: a })
  expect(notLive.body.queued).toBe(0)
  expect((await card(a, b.handover_id)).status).toBe('reported')

  await gw.resume(a) // the user reopens A
  const deliver = await api.post('/deliver', { session_id: a })
  expect(deliver.status).toBe(200)
  expect(deliver.body.queued).toBeGreaterThanOrEqual(1)
  await cardStatus(a, b.handover_id, 'delivered')
  await waitForUserMessage(a, `[spawn-session report: ${b.title} (${b.handover_id})]`)
  expect((await api.get(`/children?session_id=${a}`)).body.open_reports).toBe(0)
})

test('AT4.5 /report in B makes B\'s agent call report_back', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)
  const note = `e2e-note ${uniqueTitle('n')}`
  await mockScript(state, [toolCallReply(note, 'report_back', { result: 'reported via /report' })])
  const out = await gw.slash(bRun, 'report', note)
  expect(out).toMatch(/Report requested/)
  await waitFor('report from /report', async () => (await card(a, b.handover_id))?.reports >= 1)
  const asked = await waitForUserMessage(b.child_session_id, 'Please finish up and call the `report_back` tool now')
  expect(asked[0]).toContain(`Guidance from the user: ${note}`)
})

test('AT4.6 follow-up report: Report (2) is appended and delivered again', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)
  const first = `[spawn-session report: ${b.title} (${b.handover_id})]`
  const second = `[spawn-session report: ${b.title} (${b.handover_id}, report 2)]`

  await reportFromB(bRun, 'AT4.6 first result')
  await cardStatus(a, b.handover_id, 'delivered')
  await waitForUserMessage(a, first)

  await reportFromB(bRun, 'AT4.6 follow-up result')
  await waitFor('second report appended', async () => (await card(a, b.handover_id))?.reports === 2)
  const c = await cardStatus(a, b.handover_id, 'delivered')
  expect(c.reports).toBe(2)
  await waitForUserMessage(a, second)

  const msgs = storedSession(state, a).messages
  const i1 = msgs.findIndex(m => m.role === 'user' && m.content.startsWith(first))
  const i2 = msgs.findIndex(m => m.role === 'user' && m.content.startsWith(second))
  expect(msgs[i1].content).toContain('AT4.6 first result')
  expect(msgs[i2].content).toContain('AT4.6 follow-up result')
  expect(msgs.slice(i1 + 1, i2).some(m => m.role === 'assistant')).toBe(true) // separate turns
  expect(fs.readFileSync(c.handover_path, 'utf8')).toMatch(/^# Report \(2\)$/m)
})

test('AT7.1 Abort from A: abandoned, A gets the abort report, B archived', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const res = await api.post('/abort', { handover_id: b.handover_id, reason: 'e2e abort' })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  expect(res.body).toMatchObject({ status: 'abandoned', parent_notified: true, child_archived: true })
  expect(storedSession(state, b.child_session_id).archived).toBe(true)
  const notice = await waitForUserMessage(a, `[spawn-session aborted: ${b.title} (${b.handover_id})]`)
  expect(notice[0]).toContain('Reason: e2e abort')
})

test('AT7.1 /abandon in B: abandoned, A gets the abort report, B archived', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)
  const out = await gw.slash(bRun, 'abandon', 'e2e slash reason')
  expect(out).toMatch(new RegExp(`Abandoned ${b.handover_id}; the parent was notified`))
  expect((await card(a, b.handover_id)).status).toBe('abandoned')
  expect(storedSession(state, b.child_session_id).archived).toBe(true)
  const notice = await waitForUserMessage(a, `[spawn-session aborted: ${b.title} (${b.handover_id})]`)
  expect(notice[0]).toContain('Reason: e2e slash reason')
})

test('AT7.2 abort with a dirty worktree banks WIP (pushed) and deletes nothing without /spawn-cleanup yes', async () => {
  const { a, aRun } = await liveParent()
  const res = await api.post('/spawn', { session_id: a, title: uniqueTitle('E2E dirty wt'), task: 'x', model: MOCK_MODEL_REF, worktree: true })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  await waitForChildRow(res.body.child_session_id)
  const { worktree } = await card(a, res.body.handover_id)
  fs.writeFileSync(path.join(worktree.path, 'wip.txt'), 'unsaved work\n')

  const abort = await api.post('/abort', { handover_id: res.body.handover_id })
  expect(abort.status, JSON.stringify(abort.body)).toBe(200)
  expect(abort.body.question).toMatch(new RegExp(`/spawn-cleanup ${res.body.handover_id} yes`))
  const bank = abort.body.worktree.bank
  expect(bank).toMatchObject({ pushed: true, remote: 'origin' })
  expect(git(worktree.path, 'log', '-1', '--format=%s')).toMatch(/^WIP: spawn-session abandoned/)
  expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(bank.commit)
  expect(git(state.projectDir, 'ls-remote', 'origin', worktree.branch)).toContain(bank.commit)
  expect(fs.existsSync(worktree.path)).toBe(true)
  expect((await card(a, res.body.handover_id)).worktree_cleanup).toBe('awaiting_user')

  // "no" keeps everything; the decision is then closed.
  expect(await gw.slash(aRun, 'spawn-cleanup', `${res.body.handover_id} no`)).toMatch(/Kept worktree/)
  expect(fs.existsSync(worktree.path)).toBe(true)
  expect(git(state.projectDir, 'branch', '--list', worktree.branch)).toContain(worktree.branch)
  expect((await card(a, res.body.handover_id)).worktree_cleanup).toBe('kept')
  expect(await gw.slash(aRun, 'spawn-cleanup', `${res.body.handover_id} yes`)).toMatch(/no pending worktree decision/)
  expect(fs.existsSync(worktree.path)).toBe(true)
})

test('AT7.2 /spawn-cleanup yes removes the banked worktree and its branch', async () => {
  const { a, aRun } = await liveParent()
  const res = await api.post('/spawn', { session_id: a, title: uniqueTitle('E2E cleanup wt'), task: 'x', model: MOCK_MODEL_REF, worktree: true })
  expect(res.status, JSON.stringify(res.body)).toBe(200)
  await waitForChildRow(res.body.child_session_id)
  const { worktree } = await card(a, res.body.handover_id)
  fs.writeFileSync(path.join(worktree.path, 'wip.txt'), 'unsaved work\n')
  const abort = await api.post('/abort', { handover_id: res.body.handover_id })
  expect(abort.body.worktree.bank.commit).toBeTruthy()

  expect(await gw.slash(aRun, 'spawn-cleanup', `${res.body.handover_id} yes`)).toMatch(/Removed worktree/)
  expect(fs.existsSync(worktree.path)).toBe(false)
  expect(git(state.projectDir, 'branch', '--list', worktree.branch)).toBe('')
  // The banked commit survives on the remote.
  expect(git(state.projectDir, 'ls-remote', 'origin', worktree.branch)).toContain(abort.body.worktree.bank.commit)
})

test('AT7.3 /detach in B: confirm prompt, then detached, one-line notice, retitled, report_back and spawn refused', async () => {
  const { a } = await liveParent()
  const b = await spawnChild(a)
  const bRun = await gw.resume(b.child_session_id)

  expect(await gw.slash(bRun, 'detach')).toMatch(/Run `\/detach confirm` to proceed/)
  expect((await card(a, b.handover_id)).status).toBe('running')

  expect(await gw.slash(bRun, 'detach', 'confirm')).toMatch(new RegExp(`Detached ${b.handover_id}`))
  const header = await api.get(`/child?session_id=${b.child_session_id}`)
  expect(header.body).toMatchObject({ detached: true, status: 'detached' })
  expect(storedSession(state, b.child_session_id).title).toBe(`↳ Detached: ${b.title}`)
  const notice = await waitForUserMessage(a, `[spawn-session detached: ${b.title} (${b.handover_id})]`)
  expect(notice[0]).not.toContain('\n')

  const rb = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'after detach'])
  expect(rb.ok).toBe(false)
  expect(rb.error).toMatch(/detached/)
  const nested = hermesHelper(state, ['propose', '--session-id', b.child_session_id, '--title', 'nested', '--task', 'x'])
  expect(nested.ok).toBe(false)
  expect(nested.error).toMatch(/one level only/)
  // Irreversible: no second detach, no abort.
  expect((await api.post('/detach', { handover_id: b.handover_id, confirm: true })).status).toBe(400)
  expect((await api.post('/abort', { handover_id: b.handover_id })).status).toBe(400)
})
