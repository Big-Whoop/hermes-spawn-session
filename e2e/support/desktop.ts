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

import { HERMES_BIN, PLUGIN, cleanEnv, type BackendState } from './backend.js'

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

  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(process.env)) {
    if (v && !/^_?HERMES_/.test(k) && !CREDENTIAL.test(k) && k !== 'VIRTUAL_ENV') env[k] = v
  }
  Object.assign(env, {
    HOME: root,
    HERMES_HOME: path.join(root, 'hermes-home'),
    HERMES_DESKTOP_USER_DATA_DIR: userDataDir,
    HERMES_DESKTOP_IGNORE_EXISTING: '1',
    HERMES_DESKTOP_APP_NAME: `SpawnSessionE2E-${Date.now()}`,
    HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
    HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
    HERMES_DESKTOP_REMOTE_URL: backend.url,
    HERMES_DESKTOP_REMOTE_TOKEN: backend.token
  })

  const app = await _electron.launch({
    executablePath: electronBinary(),
    // --disable-dev-shm-usage: containers have a 64 MB /dev/shm; without it every renderer chunk fails (net::ERR_FAILED, blank window).
    args: [DESKTOP_ROOT, '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage'],
    env,
    cwd: DESKTOP_ROOT
  })
  const page = await app.firstWindow()
  await page.waitForLoadState('domcontentloaded')
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

/** Open the command palette (⌘K / Ctrl+K) and run a command by its label. */
export async function runPaletteCommand(page: Page, label: string): Promise<void> {
  await page.keyboard.press('ControlOrMeta+K')
  const input = page.getByRole('combobox').or(page.getByPlaceholder(/search|command|type/i)).first()
  await expect(input).toBeVisible()
  await input.fill(label)
  await page.getByRole('option', { name: label }).first().click()
}

/**
 * Enable the opt-in desktop half (defaultEnabled: false).
 *
 * No seeded-state mechanism is documented (research lane 2, "untested"), so this
 * clicks the toggle in Capabilities -> Plugins as the README tells users to.
 * The navigation selectors are best guesses from the docs wording and must be
 * confirmed on the first real run (record fixes here).
 */
export async function enableDesktopPlugin(page: Page): Promise<void> {
  const openCapabilities = async () => {
    const nav = page.getByRole('link', { name: /capabilities/i }).or(page.getByRole('button', { name: /capabilities/i })).first()
    if (await nav.isVisible().catch(() => false)) return nav.click()
    await runPaletteCommand(page, 'Capabilities')
  }
  await openCapabilities()
  await page.getByRole('tab', { name: /plugins/i }).or(page.getByRole('link', { name: /^plugins$/i })).first().click()
  const row = page.locator('li, [role="row"], [data-slot*="card"], div').filter({ hasText: PLUGIN_NAME }).last()
  const rescan = page.getByRole('button', { name: /rescan/i })
  if (!(await row.isVisible().catch(() => false)) && (await rescan.isVisible().catch(() => false))) await rescan.click()
  const toggle = row.getByRole('switch').first()
  await expect(toggle).toBeVisible()
  if ((await toggle.getAttribute('aria-checked')) !== 'true') await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  await page.keyboard.press('Escape')
}

/** Open a session by its sidebar title. */
export async function openSessionByTitle(page: Page, title: string): Promise<Locator> {
  const row = page.getByText(title, { exact: false }).first()
  await expect(row).toBeVisible({ timeout: 30_000 })
  await row.click()
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
