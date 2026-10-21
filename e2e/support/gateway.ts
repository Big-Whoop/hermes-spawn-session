// JSON-RPC client for the backend's gateway WebSocket (/api/ws), the same
// socket the Desktop renderer uses. Specs use it to keep a session live in the
// serve's gateway (session.resume), run turns (prompt.submit) and dispatch
// plugin slash commands (command.dispatch).
//
// Auth: the loopback serve accepts its session token as `?token=` (legacy
// token path of the WS upgrade); no dashboard auth provider is configured.
import { type BackendState } from './backend.js'

interface RpcFrame {
  id?: string
  result?: any
  error?: { code: number; message: string }
  method?: string
  params?: { type?: string; session_id?: string; payload?: any }
}

export class GatewayClient {
  private ws: WebSocket | null = null
  private seq = 0
  private pending = new Map<string, (f: RpcFrame) => void>()
  readonly events: Array<{ type: string; session_id?: string }> = []

  constructor(readonly state: BackendState) {}

  async open(): Promise<this> {
    const url = `${this.state.url.replace(/^http/, 'ws')}/api/ws?token=${encodeURIComponent(this.state.token)}`
    const ws = new WebSocket(url)
    ws.onmessage = ev => {
      const f = JSON.parse(String(ev.data)) as RpcFrame
      const done = f.id ? this.pending.get(f.id) : undefined
      if (done && f.id) {
        this.pending.delete(f.id)
        done(f)
      } else if (f.method === 'event' && f.params?.type) {
        this.events.push({ type: f.params.type, session_id: f.params.session_id })
      }
    }
    await new Promise<void>((resolve, reject) => {
      ws.onopen = () => resolve()
      ws.onerror = () => reject(new Error(`gateway WS ${url.replace(/token=[^&]+/, 'token=***')} failed`))
    })
    ws.onclose = () => {
      for (const done of this.pending.values()) done({ error: { code: -1, message: 'socket closed' } })
      this.pending.clear()
    }
    this.ws = ws
    return this
  }

  async rpc<T = any>(method: string, params: Record<string, unknown> = {}, timeoutMs = 60_000): Promise<T> {
    if (!this.ws) throw new Error('gateway client not open')
    const id = `e2e-${++this.seq}`
    const frame = await new Promise<RpcFrame>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`${method} timed out after ${timeoutMs} ms`))
      }, timeoutMs)
      this.pending.set(id, f => { clearTimeout(timer); resolve(f) })
      this.ws!.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }))
    })
    if (frame.error) throw new Error(`${method}: ${frame.error.message}`)
    return frame.result as T
  }

  /** Make a stored session live in the serve's gateway; returns its runtime id.
   *  ``eager_build`` builds the agent before answering, so an injected
   *  message right after the resume finds an attached agent. */
  async resume(storedId: string): Promise<string> {
    const res = await this.rpc<{ session_id: string }>('session.resume', { session_id: storedId, eager_build: true })
    return res.session_id
  }

  /** Start a turn in a live session (returns once accepted). */
  submit(runtimeId: string, text: string): Promise<unknown> {
    return this.rpc('prompt.submit', { session_id: runtimeId, text })
  }

  /** Run `/name arg` in a live session; returns the command's text output. */
  async slash(runtimeId: string, name: string, arg = ''): Promise<string> {
    const res = await this.rpc<{ output?: string }>('command.dispatch', { name, arg, session_id: runtimeId })
    return String(res.output ?? '')
  }

  close(): void {
    this.ws?.close()
    this.ws = null
  }
}
