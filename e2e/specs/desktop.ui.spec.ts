// Desktop e2e: Hermes Desktop (source build) under Playwright `_electron`,
// attached to the e2e backend by HERMES_DESKTOP_REMOTE_URL/_TOKEN.
//
// Covers the GUI parts of the PR #5 / PR #7 checklists and the manual e2e checklist,
// plus the desktop rows of docs/at-matrix.md (spec titles carry the AT id):
// ⌘K spawn dialog, proposal card Start/Edit/Dismiss, child header, ↳ sidebar
// badge, status cards, open-report notice + Deliver, Abort, Detach, nested-spawn
// refusal in B, theme switch without hardcoded colours, catalog screenshots.
//
// Skipped unless HERMES_DESKTOP_ROOT points at a built `apps/desktop`. The
// selectors for host UI (palette, Capabilities -> Plugins, theme) are
// unverified against v0.22.2 until the first Job run; plugin UI is matched by
// its own `data-spawn-session-*` attributes (see the header of desktop/plugin.js).
import * as fs from 'node:fs'
import * as path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

import { MOCK_MODEL_REF, PluginApi, hermesHelper, seedParent, uniqueTitle } from '../support/api.js'
import { readState, type BackendState } from '../support/backend.js'
import {
  CHEAP_MODEL_REF, HAS_DESKTOP, PRICEY_MODEL_REF, catalogShot, enableDesktopPlugin, ensureCostRank,
  launchDesktop, openSessionByTitle, registerProject, runPaletteCommand, toasts, waitForShell, type DesktopApp
} from '../support/desktop.js'

test.describe.configure({ mode: 'serial' })
test.skip(!HAS_DESKTOP, 'HERMES_DESKTOP_ROOT with a built apps/desktop (dist/electron-main.mjs) is required')

let state: BackendState
let api: PluginApi
let desk: DesktopApp
let parentTitle: string
let parentId: string

/** A fresh Desktop parent A (own child count, own proposals); returns id + title. */
function freshParent(prefix: string, cwd?: string): { id: string; title: string } {
  const title = uniqueTitle(prefix)
  if (!cwd) return { id: seedParent(state, title), title }
  const res = hermesHelper(state, ['seed-parent', '--title', title, '--cwd', cwd])
  if (!res.ok || !res.stored_session_id) throw new Error(`seed-parent failed: ${JSON.stringify(res)}`)
  return { id: res.stored_session_id, title }
}

/** The header in B renders only for the focused session: proof that B is the focused tab. */
const childHeader = (page: Page, handoverId: string) => page.locator(`[data-spawn-session-header="${handoverId}"]`)

/** Poll a REST child view of A until `pred` holds. */
async function pollChild(a: string, handoverId: string, pred: (c: any) => boolean): Promise<any> {
  let last: any = null
  await expect.poll(async () => {
    const res = await api.get(`/children?session_id=${a}`)
    last = res.body.children.find((c: any) => c.handover_id === handoverId)
    return Boolean(last && pred(last))
  }, { timeout: 60_000 }).toBe(true)
  return last
}

test.beforeAll(async () => {
  state = readState()
  api = new PluginApi(state)
  parentTitle = uniqueTitle('E2E Desktop A')
  parentId = seedParent(state, parentTitle)
  desk = await launchDesktop(state)
  await waitForShell(desk.page)
  await enableDesktopPlugin(desk.page)
})

test.afterAll(async () => {
  await desk?.close()
})

test('AT5.6: plugin loads without an error toast', async () => {
  const { page } = desk
  await openSessionByTitle(page, parentTitle)
  // Give late plugin errors (load, first REST calls) 10 s to surface.
  await page.waitForTimeout(10_000)
  await expect(toasts(page).filter({ hasText: /spawn-session|Spawn session/i })).toHaveCount(0)
})

test('AT5.1: ⌘K spawn dialog starts a child B and focuses its tab', async () => {
  const { page } = desk
  await openSessionByTitle(page, parentTitle)
  await runPaletteCommand(page, 'Spawn session with report')
  const dialog = page.locator('[data-spawn-session-dialog="new"]')
  await expect(dialog).toBeVisible()
  const title = uniqueTitle('E2E dialog child')
  await dialog.locator('[data-spawn-session-field="title"]').fill(title)
  await dialog.locator('[data-spawn-session-field="task"]').fill('e2e: reply OK')
  await catalogShot(page, '01-spawn-dialog')
  await dialog.locator('[data-spawn-session-action="start"]').click()
  await expect(page.getByText(`Spawned “${title}”`)).toBeVisible()

  const children = await api.get(`/children?session_id=${parentId}`)
  const b = children.body.children.find((c: any) => c.title === title)
  expect(b, JSON.stringify(children.body)).toBeTruthy()
  // The dialog opens B as a tab: B's header is visible only when B is focused.
  await expect(childHeader(page, b.handover_id)).toBeVisible({ timeout: 30_000 })
})

test('status card in A, ↳ sidebar badge', async () => {
  const { page } = desk
  await openSessionByTitle(page, parentTitle)
  const card = page.locator('[data-spawn-session-status]').first()
  await expect(card).toBeVisible()
  await expect(card.getByRole('button', { name: 'Abort' })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Detach' })).toBeVisible()
  await expect(page.locator('[data-spawn-session-row]').first()).toHaveText(/↳/)
  await catalogShot(page, '02-status-card-and-sidebar-badge')
})

test('child header in B and nested-spawn refusal', async () => {
  const { page } = desk
  const children = await api.get(`/children?session_id=${parentId}`)
  const b = children.body.children[0]
  await openSessionByTitle(page, b.title)
  const header = page.locator(`[data-spawn-session-header="${b.handover_id}"]`)
  await expect(header).toBeVisible()
  await expect(header).toContainText(parentTitle)
  await header.locator('[data-spawn-session-action="toggle-task"]').click()
  await expect(header.locator('[data-spawn-session-collapsible-body="task"]')).toBeVisible()
  await catalogShot(page, '03-child-header')

  await runPaletteCommand(page, 'Spawn session with report')
  await expect(page.getByText(/cannot spawn further sessions/)).toBeVisible()
})

test('AT5.4: the parent link in B\'s header focuses A', async () => {
  const { page } = desk
  const children = await api.get(`/children?session_id=${parentId}`)
  const b = children.body.children[0]
  await openSessionByTitle(page, b.title)
  const header = childHeader(page, b.handover_id)
  await expect(header).toBeVisible()
  await expect(header.locator('[data-spawn-session-action="open-parent"]')).toHaveAttribute('data-spawn-session-parent', parentId)
  await header.locator('[data-spawn-session-action="open-parent"]').click()
  // A is focused: B's header is gone and A's status card for B is shown.
  await expect(header).toBeHidden()
  await expect(page.locator(`[data-spawn-session-status="${b.handover_id}"]`)).toBeVisible({ timeout: 30_000 })
})

test('AT5.5: ⌘K spawn is blocked while a child is focused', async () => {
  const { page } = desk
  const children = await api.get(`/children?session_id=${parentId}`)
  const b = children.body.children[0]
  const defaults = await api.get(`/defaults?session_id=${b.child_session_id}`)
  expect(defaults.body).toMatchObject({ can_spawn: false, is_child: true })

  await openSessionByTitle(page, b.title)
  await expect(childHeader(page, b.handover_id)).toBeVisible()
  const before = (await api.get(`/children?session_id=${parentId}`)).body.children.length
  await runPaletteCommand(page, 'Spawn session with report')
  await expect(page.getByText(/cannot spawn further sessions \(one level only\)/)).toBeVisible()
  // No dialog opens, so nothing can be started from B.
  await expect(page.locator('[data-spawn-session-dialog]')).toHaveCount(0)
  expect((await api.get(`/children?session_id=${parentId}`)).body.children.length).toBe(before)
})

test('proposal card: Dismiss, Edit, Start', async () => {
  const { page } = desk
  await openSessionByTitle(page, parentTitle)
  const p1 = hermesHelper(state, ['propose', '--session-id', parentId, '--title', uniqueTitle('E2E proposal dismiss'), '--task', 'x', '--model', MOCK_MODEL_REF])
  const card1 = page.locator(`[data-spawn-session-card="${p1.handover_id}"]`)
  await expect(card1).toBeVisible({ timeout: 30_000 })
  await catalogShot(page, '04-proposal-card')
  await card1.getByRole('button', { name: 'Dismiss' }).click()
  await expect(card1).toBeHidden()

  const p2 = hermesHelper(state, ['propose', '--session-id', parentId, '--title', uniqueTitle('E2E proposal edit'), '--task', 'x', '--model', MOCK_MODEL_REF])
  const card2 = page.locator(`[data-spawn-session-card="${p2.handover_id}"]`)
  await expect(card2).toBeVisible({ timeout: 30_000 })
  await card2.getByRole('button', { name: 'Edit' }).click()
  const edited = uniqueTitle('E2E proposal edited')
  await page.getByPlaceholder('Short title for the new session').fill(edited)
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await expect(page.getByText(`Spawned “${edited}”`)).toBeVisible()

  const p3 = hermesHelper(state, ['propose', '--session-id', parentId, '--title', uniqueTitle('E2E proposal start'), '--task', 'x', '--model', MOCK_MODEL_REF])
  const card3 = page.locator(`[data-spawn-session-card="${p3.handover_id}"]`)
  await expect(card3).toBeVisible({ timeout: 30_000 })
  await card3.getByRole('button', { name: 'Start' }).click()
  await expect(card3).toBeHidden()
})

test('report: open-report notice in A and Deliver', async () => {
  const { page } = desk
  const b = (await api.post('/spawn', { session_id: parentId, title: uniqueTitle('E2E reporter'), task: 'x', model: MOCK_MODEL_REF })).body
  hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'E2E report body'])
  await openSessionByTitle(page, parentTitle)
  // Either delivered straight away (A live -> A turn) or shown as an open report.
  const notice = page.locator('[data-spawn-session-open-reports]')
  const delivered = page.getByText(/spawn-session report/).first()
  await expect(notice.or(delivered)).toBeVisible({ timeout: 30_000 })
  await catalogShot(page, '05-report')
  if (await notice.isVisible()) {
    await notice.getByRole('button', { name: 'Deliver' }).click()
    await expect(page.getByText(/Delivered|Nothing could be delivered/)).toBeVisible()
  }
})

test('Abort and Detach from the status card', async () => {
  const { page } = desk
  const ab = (await api.post('/spawn', { session_id: parentId, title: uniqueTitle('E2E abort'), task: 'x', model: MOCK_MODEL_REF })).body
  const de = (await api.post('/spawn', { session_id: parentId, title: uniqueTitle('E2E detach'), task: 'x', model: MOCK_MODEL_REF })).body
  await openSessionByTitle(page, parentTitle)

  const abortCard = page.locator(`[data-spawn-session-status="${ab.handover_id}"]`)
  await abortCard.getByRole('button', { name: 'Abort' }).click()
  await expect(abortCard).toBeHidden({ timeout: 30_000 })

  const detachCard = page.locator(`[data-spawn-session-status="${de.handover_id}"]`)
  await detachCard.getByRole('button', { name: 'Detach' }).click()
  await expect(detachCard).toContainText('Detach is irreversible')
  await catalogShot(page, '06-detach-confirm')
  await detachCard.getByRole('button', { name: 'Detach now' }).click()
  await expect(detachCard).toBeHidden({ timeout: 30_000 })
  const tree = await api.get('/tree')
  expect(tree.body.children[de.child_session_id]?.status).toBe('detached')
})

test('theme switch: plugin UI follows theme variables (no hardcoded colours)', async () => {
  const { page } = desk
  await api.post('/spawn', { session_id: parentId, title: uniqueTitle('E2E theme'), task: 'x', model: MOCK_MODEL_REF })
  await openSessionByTitle(page, parentTitle)
  const card = page.locator('[data-spawn-session-status]').first()
  await expect(card).toBeVisible()

  // Inline styles in plugin elements must not carry literal colours.
  const inline = await page.locator('[data-spawn-session-status], [data-spawn-session-card], [data-spawn-session-header], [data-spawn-session-row]')
    .evaluateAll(els => els.flatMap(e => [e, ...Array.from(e.querySelectorAll('*'))]).map(e => e.getAttribute('style') || '').join(';'))
  expect(inline).not.toMatch(/#[0-9a-f]{3,8}\b|rgb\(|hsl\(/i)

  const colours = () => card.evaluate(el => { const s = getComputedStyle(el); return `${s.color}|${s.borderColor}|${s.backgroundColor}` })
  const before = await colours()
  await catalogShot(page, '07-theme-a')
  // Host theme toggle: palette command (label unverified on v0.22.2).
  await runPaletteCommand(page, 'Toggle theme')
  await expect.poll(colours).not.toBe(before)
  await catalogShot(page, '08-theme-b')
})

test('AT2.3: cost-limited proposal card shows the note and Start works', async () => {
  const { page } = desk
  ensureCostRank(state)
  const a = freshParent('E2E Desktop cost A')
  await openSessionByTitle(page, a.title)
  const p = hermesHelper(state, ['propose', '--session-id', a.id, '--title', uniqueTitle('E2E pricey'), '--task', 'x', '--model', PRICEY_MODEL_REF])
  expect(p.ok, JSON.stringify(p)).toBe(true)
  expect(p.confirmation_required.join(' ')).toContain('more expensive')

  const card = page.locator(`[data-spawn-session-card="${p.handover_id}"]`)
  await expect(card).toBeVisible({ timeout: 30_000 })
  await expect(card.locator('[data-spawn-session-model]')).toHaveText(PRICEY_MODEL_REF)
  await expect(card.locator('[data-spawn-session-reasons]')).toContainText(`model ${PRICEY_MODEL_REF} is more expensive than the parent's ${CHEAP_MODEL_REF}`)
  await catalogShot(page, '09-cost-proposal')
  await card.locator('[data-spawn-session-action="start"]').click()
  await expect(card).toBeHidden({ timeout: 30_000 })

  const b = await pollChild(a.id, p.handover_id, c => c.status === 'running')
  expect(b.model).toBe(PRICEY_MODEL_REF)
  expect((await api.get(`/proposals?session_id=${a.id}`)).body.proposals.map((x: any) => x.handover_id)).not.toContain(p.handover_id)
})

test('AT3.2: limit-reached proposal card after three running agent children', async () => {
  const { page } = desk
  const a = freshParent('E2E Desktop cap A')
  // Three agent-initiated children, started through Start (initiator stays agent).
  for (let i = 0; i < 3; i++) {
    const p = hermesHelper(state, ['propose', '--session-id', a.id, '--title', uniqueTitle(`E2E cap ${i}`), '--task', 'x', '--model', MOCK_MODEL_REF])
    expect(p.ok, JSON.stringify(p)).toBe(true)
    expect((await api.post('/confirm', { handover_id: p.handover_id })).status).toBe(200)
  }
  const fourth = hermesHelper(state, ['propose', '--session-id', a.id, '--title', uniqueTitle('E2E cap 4th'), '--task', 'x', '--model', MOCK_MODEL_REF])
  expect(fourth.confirmation_required.join(' ')).toContain('limit reached')

  await openSessionByTitle(page, a.title)
  const card = page.locator(`[data-spawn-session-card="${fourth.handover_id}"]`)
  await expect(card).toBeVisible({ timeout: 30_000 })
  await expect(card.locator('[data-spawn-session-reasons]')).toContainText('limit reached')
  await expect(page.locator('[data-spawn-session-status]')).toHaveCount(3)
  await catalogShot(page, '10-limit-proposal')

  // User spawns are not capped: ⌘K still starts a fifth child.
  await runPaletteCommand(page, 'Spawn session with report')
  const dialog = page.locator('[data-spawn-session-dialog="new"]')
  const title = uniqueTitle('E2E cap user')
  await dialog.locator('[data-spawn-session-field="title"]').fill(title)
  await dialog.locator('[data-spawn-session-field="task"]').fill('x')
  await dialog.locator('[data-spawn-session-action="start"]').click()
  await expect(page.getByText(`Spawned “${title}”`)).toBeVisible()
  const kids = (await api.get(`/children?session_id=${a.id}`)).body.children
  expect(kids.find((c: any) => c.title === title)?.status).toBe('running')
})

test('AT5.2: an agent-created B opens as a tab (child.created event)', async () => {
  const { page } = desk
  const a = freshParent('E2E Desktop agent A')
  await openSessionByTitle(page, a.title)
  // The event must come from the serve process the Desktop listens to, so the
  // agent proposal is started through REST /confirm (initiator stays "agent"),
  // not through the helper process (its broadcast reaches no Desktop client).
  const p = hermesHelper(state, ['propose', '--session-id', a.id, '--title', uniqueTitle('E2E agent tab'), '--task', 'x', '--model', MOCK_MODEL_REF])
  const started = await api.post('/confirm', { handover_id: p.handover_id })
  expect(started.status, JSON.stringify(started.body)).toBe(200)
  await expect(childHeader(page, p.handover_id)).toBeVisible({ timeout: 30_000 })
  await expect(childHeader(page, p.handover_id).locator('[data-spawn-session-status-text]')).toHaveText('running')
})

test('AT2.4: Group by Projects lists B under A\'s project', async () => {
  const { page } = desk
  const folder = path.join(state.projectDir, '..', `project-at24-${Date.now().toString(36)}`)
  fs.mkdirSync(folder, { recursive: true })
  const projectName = uniqueTitle('E2E Project')
  registerProject(state, projectName, folder)
  const a = freshParent('E2E Desktop project A', folder)
  const childTitle = uniqueTitle('E2E project child')
  const b = (await api.post('/spawn', { session_id: a.id, title: childTitle, task: 'x', model: MOCK_MODEL_REF })).body
  expect(b.project, JSON.stringify(b)).toBeTruthy()

  // Host UI (selector unverified on v0.22.2): sidebar "Group by" -> "Projects".
  await page.getByRole('button', { name: /group by/i }).first().click()
  await page.getByRole('menuitemradio', { name: /projects/i }).or(page.getByRole('menuitem', { name: /projects/i })).first().click()
  const group = page.locator('[role="group"], section, li').filter({ hasText: projectName }).first()
  await expect(group).toBeVisible({ timeout: 30_000 })
  await expect(group.getByText(childTitle, { exact: false }).first()).toBeVisible()
  await expect(group.locator(`[data-spawn-session-row="${b.handover_id}"]`)).toHaveText(/↳/)
  await catalogShot(page, '11-group-by-projects')
})

test('AT6.2 / AT4.4: closed A shows N open report(s) and Deliver delivers', async () => {
  const { page } = desk
  // A seeded by the helper process is not live in the serve: the report stays reported.
  const a = freshParent('E2E Desktop closed A')
  const b = (await api.post('/spawn', { session_id: a.id, title: uniqueTitle('E2E closed reporter'), task: 'x', model: MOCK_MODEL_REF })).body
  const r = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'E2E closed-A report'])
  expect(r.ok, JSON.stringify(r)).toBe(true)
  const before = await api.get(`/children?session_id=${a.id}`)
  expect(before.body.open_reports).toBeGreaterThanOrEqual(1)
  expect(before.body.children.find((c: any) => c.handover_id === b.handover_id).status).toBe('reported')

  // Reopen A in the Desktop -> banner -> Deliver.
  await openSessionByTitle(page, a.title)
  const notice = page.locator('[data-spawn-session-open-reports]')
  await expect(notice).toBeVisible({ timeout: 30_000 })
  await expect(notice.locator('[data-spawn-session-open-reports-text]')).toHaveText(/^\d+ open reports?$/)
  await expect(page.locator(`[data-spawn-session-status="${b.handover_id}"] [data-spawn-session-status-text]`)).toHaveText('reported')
  await catalogShot(page, '12-open-reports-banner')
  await notice.locator('[data-spawn-session-action="deliver"]').click()
  await expect(page.getByText(/Delivered \d+ items? to this session/)).toBeVisible()

  await pollChild(a.id, b.handover_id, c => c.status === 'delivered')
  await expect(notice).toBeHidden({ timeout: 30_000 })
})

test('AT7.3: Detached: title, Detached marker and report_back refusal', async () => {
  const { page } = desk
  const a = freshParent('E2E Desktop detach A')
  const title = uniqueTitle('E2E detach me')
  const b = (await api.post('/spawn', { session_id: a.id, title, task: 'x', model: MOCK_MODEL_REF })).body
  await openSessionByTitle(page, a.title)
  const card = page.locator(`[data-spawn-session-status="${b.handover_id}"]`)
  await card.locator('[data-spawn-session-action="detach"]').click()
  await expect(card.locator('[data-spawn-session-detach-warning]')).toBeVisible()
  await card.locator('[data-spawn-session-action="detach-confirm"]').click()
  await expect(card).toBeHidden({ timeout: 30_000 })
  expect((await api.get('/tree')).body.children[b.child_session_id]?.status).toBe('detached')

  // Sidebar: retitled "↳ Detached: <title>" with the detached badge.
  const row = page.getByText(`↳ Detached: ${title}`, { exact: false }).first()
  await expect(row).toBeVisible({ timeout: 30_000 })
  await expect(page.locator(`[data-spawn-session-row="${b.handover_id}"]`).first()).toHaveAttribute('data-spawn-session-row-status', 'detached')

  // report_back from B is refused; B's header keeps showing the detached status.
  const r = hermesHelper(state, ['report', '--session-id', b.child_session_id, '--result', 'too late'])
  expect(r.ok).toBe(false)
  expect(JSON.stringify(r)).toMatch(/detached/i)
  await row.click()
  const header = childHeader(page, b.handover_id)
  await expect(header.locator('[data-spawn-session-detached]')).toHaveText('Detached')
  await expect(header.locator('[data-spawn-session-status-text]')).toHaveText('detached')
  await catalogShot(page, '13-detached-child')
  const after = (await api.get(`/children?session_id=${a.id}`)).body.children.find((c: any) => c.handover_id === b.handover_id)
  expect(after).toMatchObject({ status: 'detached', reports: 0 })
})
