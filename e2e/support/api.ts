// Small helpers shared by the specs: REST client for the plugin routes and
// the Hermes-side helper (seed parent, propose, report).
import { execFileSync } from 'node:child_process'
import * as path from 'node:path'

import { API, E2E_DIR, HERMES_PYTHON, cleanEnv, readState, type BackendState } from './backend.js'

export interface ApiResult<T = any> {
  status: number
  body: T
}

export class PluginApi {
  constructor(readonly state: BackendState = readState()) {}

  async call<T = any>(method: 'GET' | 'POST', route: string, body?: unknown): Promise<ApiResult<T>> {
    const init: RequestInit = {
      method,
      headers: { Authorization: `Bearer ${this.state.token}`, 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    }
    let res: Response
    try {
      res = await fetch(`${this.state.url}${API}${route}`, init)
    } catch {
      // undici reuses keep-alive sockets; the server drops idle ones while a
      // slow seed call runs ("other side closed"). One retry on a fresh socket.
      res = await fetch(`${this.state.url}${API}${route}`, init)
    }
    const text = await res.text()
    let parsed: unknown = text
    try { parsed = JSON.parse(text) } catch { /* keep text */ }
    return { status: res.status, body: parsed as T }
  }

  get<T = any>(route: string): Promise<ApiResult<T>> { return this.call<T>('GET', route) }
  post<T = any>(route: string, body: unknown): Promise<ApiResult<T>> { return this.call<T>('POST', route, body) }
}

/** Run e2e/support/hermes_helper.py against the backend's HERMES_HOME; returns its JSON line. */
export function hermesHelper(state: BackendState, args: string[]): any {
  const script = path.join(E2E_DIR, 'support', 'hermes_helper.py')
  let out: string
  try {
    out = execFileSync(HERMES_PYTHON, [script, ...args], {
      // Same isolation as the backend: no inherited HERMES_* / credentials,
      // and the sandbox HOME when global setup owns the backend.
      env: { ...cleanEnv(), ...(state.sandboxRoot ? { HOME: `${state.sandboxRoot}/home` } : {}), HERMES_HOME: state.hermesHome },
      encoding: 'utf8',
      timeout: 90_000,
      stdio: ['ignore', 'pipe', 'pipe']
    })
  } catch (err: any) {
    out = String(err.stdout ?? '')
    if (!out.trim()) throw new Error(`hermes_helper ${args[0]} failed: ${err.stderr ?? err}`)
  }
  const line = out.trim().split('\n').filter(Boolean).pop() ?? '{}'
  return JSON.parse(line)
}

let counter = 0
export function uniqueTitle(prefix: string): string {
  counter += 1
  return `${prefix} ${Date.now().toString(36)}-${counter}`
}

/** Create a Desktop-sourced parent session A; returns its durable (stored) id. */
export function seedParent(state: BackendState, title = uniqueTitle('E2E parent')): string {
  const res = hermesHelper(state, ['seed-parent', '--title', title, '--cwd', state.projectDir])
  if (!res.ok || !res.stored_session_id) throw new Error(`seed-parent failed: ${JSON.stringify(res)}`)
  return res.stored_session_id as string
}

export const MOCK_MODEL_REF = 'custom:mock-e2e'
