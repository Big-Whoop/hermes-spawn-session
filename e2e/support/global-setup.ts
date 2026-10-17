// Global setup: start the mock LLM and the backend (or adopt an external one).
import * as fs from 'node:fs'
import * as path from 'node:path'

import { E2E_DIR, STATE_FILE, externalBackend, startLocalBackend, writeState } from './backend.js'
import { startMockLlm } from './mock-llm.js'

export default async function globalSetup(): Promise<() => Promise<void>> {
  process.env.E2E_STATE_FILE ||= STATE_FILE
  const ext = externalBackend()
  if (ext) {
    writeState(ext)
    return async () => {}
  }
  const mock = await startMockLlm(Number(process.env.E2E_MOCK_LLM_PORT || 0))
  const { state } = await startLocalBackend(mock.url)
  writeState(state)
  const artifacts = path.resolve(E2E_DIR, process.env.E2E_ARTIFACTS_DIR || 'test-results')
  fs.mkdirSync(artifacts, { recursive: true })
  console.log(`[e2e] backend ${state.url} HERMES_HOME=${state.hermesHome} mock=${mock.url}`)
  // Returned function = teardown in the same process (keeps the mock server handle).
  return async () => {
    if (state.logFile && fs.existsSync(state.logFile)) {
      fs.copyFileSync(state.logFile, path.join(artifacts, 'serve.log'))
    }
    const logs = path.join(state.hermesHome, 'logs')
    if (fs.existsSync(logs)) fs.cpSync(logs, path.join(artifacts, 'hermes-logs'), { recursive: true })
    if (state.pid) {
      try { process.kill(-state.pid, 'SIGTERM') } catch { /* already gone */ }
    }
    await mock.close()
    if (state.sandboxRoot && !process.env.E2E_KEEP) fs.rmSync(state.sandboxRoot, { recursive: true, force: true })
    fs.rmSync(process.env.E2E_STATE_FILE!, { force: true })
  }
}
