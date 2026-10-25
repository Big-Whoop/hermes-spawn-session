// Desktop half: launch Hermes Desktop (source build) with Playwright `_electron`
// in remote mode against the e2e backend. Mirrors the upstream v0.22.2 harness
// (apps/desktop/e2e/fixtures.ts + e2e/core/remote-helpers.ts):
// `electron <DESKTOP_ROOT> --disable-gpu --no-sandbox` (+ --disable-dev-shm-usage), sandbox HOME + user-data,
// credentials stripped, HERMES_DESKTOP_REMOTE_URL/_TOKEN to attach.
//
// Needs HERMES_DESKTOP_ROOT = a built hermes-agent `apps/desktop` checkout
// (`npm ci && npm run build`); the e2e test image provides it. Under a headless
// Linux run, wrap the command in `xvfb-run -a`.
import { _electron, expect, type ElectronApplication, type Locator, type Page } from '@playwright/test'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import { execFileSync } from 'node:child_process'

import { HERMES_BIN, PLUGIN, REPO_ROOT, cleanEnv, type BackendState } from './backend.js'

export const DESKTOP_ROOT = process.env.HERMES_DESKTOP_ROOT || ''
export const HAS_DESKTOP = Boolean(DESKTOP_ROOT) && fs.existsSync(path.join(DESKTOP_ROOT, 'dist', 'electron-main.mjs'))
export const PLUGIN_NAME = 'Spawn session'

const CREDENTIAL = /(_API_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS|_ACCESS_KEY|_PRIVATE_KEY|_BASE_URL)$/

function electronBinary(): string {
  if (process.env.ELECTRON_BIN) return process.env.ELECTRON_BIN
  for (const root of [DESKTOP_ROOT, path.resolve(DESKTOP_ROOT, '..', '..')]) {
    const bin = path.join(root, 'node_modules', '.bin', process.platform === 'win32' ? 'electron.cmd' : 'electron')
    if (fs.existsSync(bin)) return bin
  }
  throw new Error(`electron binary not found under ${DESKTOP_ROOT}; set ELECTRON_BIN`)
}

export interface DesktopApp {
  app: ElectronApplication
  page: Page
  userDataDir: string
  close(): Promise<void>
}

export async function launchDesktop(backend: BackendState): Promise<DesktopApp> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'spawn-session-e2e-desktop-'))
  const userDataDir = path.join(root, 'electron-user-data')
  fs.mkdirSync(userDataDir, { recursive: true })
  // Fixed window size for stable screenshots (as upstream fixtures).
  fs.writeFileSync(path.join(userDataDir, 'window-state.json'), JSON.stringify({ x: 0, y: 0, width: 1280, height: 860, isMaximized: false }))
  fs.writeFileSync(path.join(userDataDir, 'zoom-state.json'), JSON.stringify({ zoomLevel: 0 }))
  // Electron loads desktop halves from ITS OWN HERMES_HOME, even in remote mode:
  // it copies plugins/<name>/desktop/plugin.js into desktop-plugins/<name> at
  // startup. Without this link the Plugins tab shows the desktop half as
  // "unavailable (remote backend)".
  const desktopHome = path.join(root, 'hermes-home')
  fs.mkdirSync(path.join(desktopHome, 'plugins'), { recursive: true })
  fs.symlinkSync(REPO_ROOT, path.join(desktopHome, 'plugins', PLUGIN))

  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(process.env)) {
    if (v && !/^_?HERMES_/.test(k) && !CREDENTIAL.test(k) && k !== 'VIRTUAL_ENV') env[k] = v
  }
  Object.assign(env, {
    HOME: root,
    HERMES_HOME: desktopHome,
    HERMES_DESKTOP_USER_DATA_DIR: userDataDir,
    HERMES_DESKTOP_IGNORE_EXISTING: '1',
    HERMES_DESKTOP_APP_NAME: `SpawnSessionE2E-${Date.now()}`,
    HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
    HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
    HERMES_DESKTOP_REMOTE_URL: backend.url,
    HERMES_DESKTOP_REMOTE_TOKEN: backend.token,
    // The specs match English labels; the app follows the system locale.
    LANG: 'en_US.UTF-8',
    LANGUAGE: 'en_US',
    LC_ALL: 'en_US.UTF-8'
  })

  const app = await _electron.launch({
    executablePath: electronBinary(),
    // --disable-dev-shm-usage: containers have a 64 MB /dev/shm; without it every renderer chunk fails (net::ERR_FAILED, blank window).
    // E2E_ELECTRON_ARGS: extra switches, e.g. `--ozone-platform=headless` to run
    // without a display server (no xvfb needed).
    args: [DESKTOP_ROOT, '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--lang=en-US', ...(process.env.E2E_ELECTRON_ARGS || '').split(/\s+/).filter(Boolean)],
    env,
    cwd: DESKTOP_ROOT
  })
  const page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
  // Headless ozone ignores window-state.json; size the window explicitly.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1280, 860))
  return {
    app, page, userDataDir,
    close: async () => {
      await app.close().catch(() => {})
      if (!process.env.E2E_KEEP) fs.rmSync(root, { recursive: true, force: true })
    }
  }
}

/** Upstream chat-ready signal: the composer is mounted (tests-js/scripts/desktop-chat-smoke.ts). */
export async function waitForShell(page: Page): Promise<void> {
  await expect(page.locator('[data-slot="composer-root"]').first()).toBeVisible({ timeout: 120_000 })
}

/**
 * Open the command palette (⌘K / Ctrl+K) and run a command by its label.
 * Extra labels pick rows in the submenu the previous command opened
 * (e.g. 'Change color mode…', 'Dark'); a submenu row that keeps the palette
 * open is closed with Escape afterwards.
 */
export async function runPaletteCommand(page: Page, label: string, ...subLabels: string[]): Promise<void> {
  await page.keyboard.press('ControlOrMeta+K')
  const input = page.getByRole('combobox').or(page.getByPlaceholder(/search|command|type/i)).first()
  await expect(input).toBeVisible()
  for (const step of [label, ...subLabels]) {
    await input.fill(step)
    // v0.22.2: click() on the option never passes Playwright's stability check,
    // and nothing is highlighted after typing, so a bare Enter does nothing.
    // Walk the highlight with ArrowDown to the wanted row, then Enter (the
    // keyboard path a user takes).
    const option = page.getByRole('option', { name: step, exact: true }).first()
    await expect(option).toBeVisible()
    const count = await page.getByRole('option').count()
    for (let i = 0; i < count && (await option.getAttribute('aria-selected')) !== 'true'; i++) await input.press('ArrowDown')
    await expect(option).toHaveAttribute('aria-selected', 'true')
    await input.press('Enter')
  }
  if (subLabels.length && (await input.isVisible())) await input.press('Escape')
}

/**
 * Enable the opt-in desktop half (defaultEnabled: false).
 *
 * No seeded-state mechanism is documented (research lane 2, "untested"), so this
 * clicks the toggle in Capabilities -> Plugins as the README tells users to.
 * Selectors verified on v0.22.2 and v0.22.5.
 */
export async function enableDesktopPlugin(page: Page): Promise<void> {
  const openCapabilities = async () => {
    const nav = page.getByRole('link', { name: /capabilities/i }).or(page.getByRole('button', { name: /capabilities/i })).first()
    if (await nav.isVisible().catch(() => false)) return nav.click()
    await runPaletteCommand(page, 'Capabilities')
  }
  await openCapabilities()
  await page.getByRole('button', { name: /^plugins$/i }).or(page.getByRole('tab', { name: /^plugins$/i })).first().click()
  // v0.22.2: one table row per package, with a "Desktop: <package>" switch.
  // v0.22.5: the tab is a catalog; a git/symlink install has no discover
  // section, so search for it and open its card. The detail pane keeps the
  // per-half "Desktop: <package>" switch.
  const toggle = page.getByRole('switch', { name: `Desktop: ${PLUGIN_NAME}` })
  const search = page.getByPlaceholder(/search plugins/i)
  await expect(toggle.or(search).first()).toBeVisible()
  if (!(await toggle.isVisible())) {
    // The package key ("spawn-session") finds nothing; the display name does.
    await search.fill(PLUGIN_NAME)
    await page.locator('article').filter({ has: page.getByRole('switch', { name: PLUGIN_NAME, exact: true }) })
      .getByRole('button', { name: PLUGIN_NAME, exact: true }).click()
  }
  await expect(toggle).toBeVisible()
  if ((await toggle.getAttribute('aria-checked')) !== 'true') await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  await page.keyboard.press('Escape')
}

/** Open a session by its sidebar title. */
export async function openSessionByTitle(page: Page, title: string): Promise<Locator> {
  // The sidebar row is a button named after the title (B's carries the `↳ `
  // prefix and the badge). A bare getByText would also hit the status card's
  // title in A's composer, which is not a link.
  const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  // Skip the row's drag handle ("Reorder <title>").
  const row = page.getByRole('button', { name: new RegExp(`^(?!Reorder ).*${escaped}`) }).filter({ visible: true }).first()
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.click()
  await expect(page.getByRole('tab', { selected: true, name: new RegExp(escaped) })).toBeVisible()
  return row
}

/** Screenshot into the catalog dir (E2E_ARTIFACTS_DIR/screenshots). */
export async function catalogShot(page: Page, name: string): Promise<void> {
  const dir = path.resolve(process.env.E2E_ARTIFACTS_DIR || 'test-results', 'screenshots')
  fs.mkdirSync(dir, { recursive: true })
  await page.screenshot({ path: path.join(dir, `${name}.png`) })
}

/** Parent model ref of a seeded A (config default) and a higher-ranked child model. */
export const CHEAP_MODEL_REF = 'custom:mock-e2e'
export const PRICEY_MODEL_REF = 'custom:mock-e2e-pricey'

/**
 * AT2.3 prerequisite: rank the parent model below a pricier child model in the
 * plugin config (`plugins.entries.spawn-session.cost_rank`). With an empty map
 * both rank as infinity and no cost proposal is created. Idempotent: a
 * `cost_rank` already written by the global setup is kept. The helper process
 * reads config.yaml fresh, so no backend restart is needed for proposals.
 */
export function ensureCostRank(backend: BackendState): void {
  const file = path.join(backend.hermesHome, 'config.yaml')
  if (!fs.existsSync(file)) return
  const text = fs.readFileSync(file, 'utf8')
  if (/^\s+cost_rank:/m.test(text)) return
  const anchor = `    ${PLUGIN}:\n`
  if (!text.includes(anchor)) throw new Error(`config.yaml has no plugins.entries.${PLUGIN} block`)
  const block = `      cost_rank:\n        "${CHEAP_MODEL_REF}": 1\n        "${PRICEY_MODEL_REF}": 5\n`
  fs.writeFileSync(file, text.replace(anchor, anchor + block))
}

/** AT2.4: register `folder` as a Desktop project in the backend's HERMES_HOME (`hermes project create`). */
export function registerProject(backend: BackendState, name: string, folder: string): void {
  execFileSync(HERMES_BIN, ['project', 'create', name, folder], {
    env: { ...cleanEnv(), ...(backend.sandboxRoot ? { HOME: path.join(backend.sandboxRoot, 'home') } : {}), HERMES_HOME: backend.hermesHome },
    encoding: 'utf8',
    timeout: 60_000,
    stdio: ['ignore', 'pipe', 'pipe']
  })
}

/** Host toasts (sonner) and alerts; used to assert that no plugin error surfaced. */
export function toasts(page: Page): Locator {
  return page.locator('[data-sonner-toast], [role="alert"], [role="status"]')
}
