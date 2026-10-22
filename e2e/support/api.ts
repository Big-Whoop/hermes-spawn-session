// Small helpers shared by the specs: REST client for the plugin routes and
// the Hermes-side helper (seed parent, propose, report).
import { execFileSync } from 'node:child_process'
import * as path from 'node:path'

import { API, E2E_DIR, HERMES_PYTHON, cleanEnv, readState, type BackendState } from './backend.js'
import type { MockReply } from './mock-llm.js'

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
export function hermesHelper(state: BackendState, args: string[], extraEnv: Record<string, string> = {}): any {
  const script = path.join(E2E_DIR, 'support', 'hermes_helper.py')
  let out: string
  try {
    out = execFileSync(HERMES_PYTHON, [script, ...args], {
      // Same isolation as the backend: no inherited HERMES_* / credentials,
      // and the sandbox HOME when global setup owns the backend.
      env: { ...cleanEnv(), ...(state.sandboxRoot ? { HOME: `${state.sandboxRoot}/home` } : {}), HERMES_HOME: state.hermesHome, ...extraEnv },
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

/** Create a Desktop-sourced parent session A on the mock model; returns its durable (stored) id. */
export function seedParent(state: BackendState, title = uniqueTitle('E2E parent')): string {
  const res = hermesHelper(state, ['seed-parent', '--title', title, '--cwd', state.projectDir, '--provider', 'custom', '--model', 'mock-e2e'])
  if (!res.ok || !res.stored_session_id) throw new Error(`seed-parent failed: ${JSON.stringify(res)}`)
  return res.stored_session_id as string
}

export const MOCK_MODEL_REF = 'custom:mock-e2e'
/** Ranked above the parent's model in the e2e config's `cost_rank` (D6). */
export const PRICEY_MODEL_REF = 'custom:mock-e2e-pricey'

/** Queue scripted replies on the mock LLM (see mock-llm.ts for the reply shapes). */
export async function mockScript(state: BackendState, replies: MockReply[]): Promise<void> {
  if (!state.mockLlmUrl) throw new Error('no mock LLM URL for this backend')
  const res = await fetch(`${state.mockLlmUrl.replace(/\/v1$/, '')}/__mock/script`, { method: 'POST', body: JSON.stringify(replies) })
  if (!res.ok) throw new Error(`mock script failed: HTTP ${res.status}`)
}

/** Every chat request the mock LLM has received so far. */
export async function mockRequests(state: BackendState): Promise<Array<{ messages?: Array<{ role?: string; content?: unknown }> }>> {
  if (!state.mockLlmUrl) throw new Error('no mock LLM URL for this backend')
  return (await fetch(`${state.mockLlmUrl.replace(/\/v1$/, '')}/__mock/requests`)).json()
}

/** A scripted agent turn that calls a (deferred) tool through `tool_call`. */
export function toolCallReply(match: string, name: string, args: Record<string, unknown>): MockReply {
  return { match, tool: 'tool_call', arguments: { calls: [{ name, arguments: args }] } }
}

export interface StoredSession {
  ok: boolean
  id: string
  title: string
  archived: boolean
  cwd: string | null
  messages: Array<{ role: string; content: string }>
}

/** state.db row + messages of a session (read-only). */
export function storedSession(state: BackendState, sessionId: string): StoredSession {
  const res = hermesHelper(state, ['session', '--session-id', sessionId])
  if (!res.ok) throw new Error(`session ${sessionId}: ${res.error}`)
  return res as StoredSession
}

/** Poll ``fn`` until it returns a truthy value; throws with the last value on timeout. */
export async function waitFor<T>(what: string, fn: () => Promise<T> | T, timeoutMs = 60_000, stepMs = 1_000): Promise<NonNullable<T>> {
  const end = Date.now() + timeoutMs
  let last: T | undefined
  while (Date.now() < end) {
    last = await fn()
    if (last) return last as NonNullable<T>
    await new Promise(r => setTimeout(r, stepMs))
  }
  throw new Error(`timed out after ${timeoutMs} ms waiting for ${what} (last: ${JSON.stringify(last)})`)
}
