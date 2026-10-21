// Minimal OpenAI-compatible mock LLM provider for e2e runs (no API key, no network).
//
// Implements just enough of the Chat Completions API for a Hermes turn:
// - GET  /v1/models
// - POST /v1/chat/completions (stream and non-stream)
//
// Replies are scripted: a reply queue (POST /__mock/script, JSON array of
// replies) is consumed first; otherwise the reply echoes a fixed sentence.
// A reply is either a string (assistant text) or an object:
//   { text: "..." }                          assistant text
//   { tool: "<name>", arguments: {...} }     a single tool call
// Objects may also carry
//   match:   only used for a request whose last user message contains this
//            substring (several sessions share one mock; without `match` a
//            reply goes to whichever turn asks first)
//   delayMs: wait this long before answering (a slow turn, AT4.3)
// Every request is recorded and readable via GET /__mock/requests.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import type { AddressInfo } from 'node:net'

export interface MockReplyOptions {
  match?: string
  delayMs?: number
}
export type MockReply =
  | string
  | (MockReplyOptions & { text: string })
  | (MockReplyOptions & { tool: string; arguments: Record<string, unknown> })

export interface MockLlm {
  url: string
  server: Server
  close(): Promise<void>
}

export const MOCK_MODEL = 'mock-e2e'
export const DEFAULT_REPLY = 'Mock reply from the e2e provider.'

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', c => (data += c))
    req.on('end', () => resolve(data))
    req.on('error', reject)
  })
}

function json(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(body))
}

function contentText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) return content.map(p => (p && typeof p === 'object' && 'text' in p ? String((p as { text: unknown }).text) : '')).join('')
  return ''
}

/** Text of the last user message of a chat request. */
export function lastUserText(body: { messages?: Array<{ role?: string; content?: unknown }> }): string {
  const msgs = body.messages ?? []
  for (let i = msgs.length - 1; i >= 0; i--) if (msgs[i].role === 'user') return contentText(msgs[i].content)
  return ''
}

function takeReply(queue: MockReply[], userText: string): MockReply {
  const i = queue.findIndex(r => typeof r === 'string' || !r.match || userText.includes(r.match))
  if (i < 0) return DEFAULT_REPLY
  return queue.splice(i, 1)[0]
}

function isTool(reply: MockReply): reply is MockReplyOptions & { tool: string; arguments: Record<string, unknown> } {
  return typeof reply !== 'string' && 'tool' in reply
}

function message(reply: MockReply, n: number): Record<string, unknown> {
  if (!isTool(reply)) return { role: 'assistant', content: typeof reply === 'string' ? reply : reply.text }
  return {
    role: 'assistant',
    content: null,
    tool_calls: [{
      id: `call_mock_${n}`,
      type: 'function',
      function: { name: reply.tool, arguments: JSON.stringify(reply.arguments) }
    }]
  }
}

export async function startMockLlm(port = 0): Promise<MockLlm> {
  const queue: MockReply[] = []
  const requests: unknown[] = []
  let n = 0

  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost')
      if (req.method === 'GET' && url.pathname.endsWith('/models')) {
        return json(res, 200, { object: 'list', data: [{ id: MOCK_MODEL, object: 'model', owned_by: 'e2e' }] })
      }
      if (req.method === 'POST' && url.pathname === '/__mock/script') {
        const replies = JSON.parse(await readBody(req)) as MockReply[]
        queue.push(...replies)
        return json(res, 200, { queued: queue.length })
      }
      if (req.method === 'GET' && url.pathname === '/__mock/requests') {
        return json(res, 200, requests)
      }
      if (req.method === 'POST' && url.pathname.endsWith('/chat/completions')) {
        const body = JSON.parse((await readBody(req)) || '{}') as { stream?: boolean; messages?: Array<{ role?: string; content?: unknown }> }
        requests.push(body)
        n += 1
        const reply = takeReply(queue, lastUserText(body))
        if (typeof reply !== 'string' && reply.delayMs) await new Promise(r => setTimeout(r, reply.delayMs))
        const msg = message(reply, n)
        const finish = isTool(reply) ? 'tool_calls' : 'stop'
        const base = { id: `chatcmpl-mock-${n}`, created: Math.floor(Date.now() / 1000), model: MOCK_MODEL }
        const usage = { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 }
        if (!body.stream) {
          return json(res, 200, { ...base, object: 'chat.completion', choices: [{ index: 0, message: msg, finish_reason: finish }], usage })
        }
        res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' })
        const chunk = (delta: unknown, finish_reason: string | null, extra: object = {}) =>
          res.write(`data: ${JSON.stringify({ ...base, object: 'chat.completion.chunk', choices: [{ index: 0, delta, finish_reason }], ...extra })}\n\n`)
        if (!isTool(reply)) {
          chunk({ role: 'assistant', content: msg.content }, null)
        } else {
          const calls = (msg.tool_calls as Array<Record<string, unknown>>).map((c, index) => ({ index, ...c }))
          chunk({ role: 'assistant', tool_calls: calls }, null)
        }
        chunk({}, finish, { usage })
        res.write('data: [DONE]\n\n')
        return res.end()
      }
      json(res, 404, { error: { message: `mock: no route ${req.method} ${url.pathname}` } })
    } catch (err) {
      json(res, 500, { error: { message: String(err) } })
    }
  })

  await new Promise<void>(resolve => server.listen(port, '127.0.0.1', resolve))
  const { port: bound } = server.address() as AddressInfo
  return {
    url: `http://127.0.0.1:${bound}/v1`,
    server,
    close: () => new Promise(resolve => server.close(() => resolve()))
  }
}
