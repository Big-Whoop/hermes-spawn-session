// Desktop e2e: Hermes Desktop (source build) under Playwright `_electron`,
// attached to the e2e backend by HERMES_DESKTOP_REMOTE_URL/_TOKEN.
//
// Covers the GUI parts of the PR #5 / PR #7 checklists and card t_787f6427:
// ⌘K spawn dialog, proposal card Start/Edit/Dismiss, child header, ↳ sidebar
// badge, status cards, open-report notice + Deliver, Abort, Detach, nested-spawn
// refusal in B, theme switch without hardcoded colours, catalog screenshots.
//
// Skipped unless HERMES_DESKTOP_ROOT points at a built `apps/desktop`. The
// selectors for host UI (palette, Capabilities -> Plugins, theme) are
// unverified against v0.22.2 until the first Job run; plugin UI is matched by
// its own `data-spawn-session-*` attributes and button labels from desktop/plugin.js.
import { expect, test } from '@playwright/test'

import { MOCK_MODEL_REF, PluginApi, hermesHelper, seedParent, uniqueTitle } from '../support/api.js'
import { readState, type BackendState } from '../support/backend.js'
import {
  HAS_DESKTOP, catalogShot, enableDesktopPlugin, launchDesktop, openSessionByTitle,
  runPaletteCommand, waitForShell, type DesktopApp
} from '../support/desktop.js'

test.describe.configure({ mode: 'serial' })
test.skip(!HAS_DESKTOP, 'HERMES_DESKTOP_ROOT with a built apps/desktop (dist/electron-main.mjs) is required')

let state: BackendState
let api: PluginApi
let desk: DesktopApp
let parentTitle: string
let parentId: string

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

test('⌘K spawn dialog starts a child B', async () => {
  const { page } = desk
  await openSessionByTitle(page, parentTitle)
  await runPaletteCommand(page, 'Spawn session with report')
  const title = uniqueTitle('E2E dialog child')
  await page.getByPlaceholder('Short title for the new session').fill(title)
  await page.getByPlaceholder('Detailed instructions for the new session').fill('e2e: reply OK')
  await catalogShot(page, '01-spawn-dialog')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await expect(page.getByText(`Spawned “${title}”`)).toBeVisible()

  const children = await api.get(`/children?session_id=${parentId}`)
  expect(children.body.children.map((c: any) => c.title)).toContain(title)
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
  await header.getByRole('button', { name: /Task/ }).click()
  await catalogShot(page, '03-child-header')

  await runPaletteCommand(page, 'Spawn session with report')
  await expect(page.getByText(/cannot spawn further sessions/)).toBeVisible()
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
