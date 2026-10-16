#!/usr/bin/env node
// Smoke test for desktop/plugin.js (no Hermes Desktop needed).
//
// Loads the plugin under Node with stub `@hermes/plugin-sdk`, `react` and
// `react/jsx-runtime` modules (the only specifiers the desktop loader allows),
// then checks the default-export contract and what register(ctx) contributes.
// The real UI behaviour is covered by the manual checklist in the PR.
//
// Usage: node scripts/smoke_desktop_plugin.mjs

import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'

const repo = join(dirname(fileURLToPath(import.meta.url)), '..')
const src = readFileSync(join(repo, 'desktop', 'plugin.js'), 'utf8')

const allowed = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])
for (const m of src.matchAll(/^\s*import\s[^'"]*['"]([^'"]+)['"]/gm)) {
  assert.ok(allowed.has(m[1]), `disallowed import: ${m[1]}`)
}
assert.ok(!/#[0-9a-fA-F]{3,8}\b|\brgb\(|\bblack\b|\bwhite\b/.test(src), 'hardcoded colour found')

const dir = mkdtempSync(join(tmpdir(), 'spawn-session-smoke-'))
try {
  const nm = join(dir, 'node_modules')
  const mk = (name, body) => {
    mkdirSync(join(nm, name), { recursive: true })
    writeFileSync(join(nm, name, 'package.json'), JSON.stringify({ name, type: 'module', main: 'index.js' }))
    writeFileSync(join(nm, name, 'index.js'), body)
  }
  const atom = `export const atom = v => { let x = v; const ls = new Set(); return { get: () => x, set: n => { x = n; ls.forEach(f => f(n)) }, listen: f => (ls.add(f), () => ls.delete(f)) } }`
  const comp = n => `export const ${n} = () => null`
  mk('@hermes/plugin-sdk', [
    atom,
    ...['Badge', 'Button', 'Dialog', 'DialogContent', 'DialogDescription', 'DialogFooter', 'DialogHeader', 'DialogTitle', 'Input', 'Textarea'].map(comp),
    `export const COMPOSER_AREAS = { top: 'composer.top' }`,
    `export const PALETTE_AREA = 'palette'`,
    `export const SESSION_ROW_AREAS = { leading: 'sessionRow.leading', trailing: 'sessionRow.trailing' }`,
    `export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }`,
    `export const queryClient = { invalidateQueries: () => {} }`,
    `export const useQuery = () => ({ data: null })`,
    `export const useValue = a => a.get()`,
    `export const host = { state: { focusedStoredSessionId: { get: () => null } }, notify: () => {}, notifyError: () => {}, openSession: async () => {}, request: async () => ({}) }`
  ].join('\n'))
  mk('react', `export const useState = v => [v, () => {}]; export const useEffect = () => {}; export default {}`)
  // Subpath export so `react/jsx-runtime` resolves under ESM.
  writeFileSync(join(nm, 'react', 'package.json'), JSON.stringify({
    name: 'react', type: 'module', exports: { '.': './index.js', './jsx-runtime': './jsx-runtime.js' }
  }))
  writeFileSync(join(nm, 'react', 'jsx-runtime.js'), `export const jsx = (t, p) => ({ t, p }); export const jsxs = jsx`)

  const file = join(dir, 'plugin.js')
  writeFileSync(file, src)
  const plugin = (await import(pathToFileURL(file).href)).default

  assert.equal(plugin.id, 'spawn-session')
  assert.equal(typeof plugin.register, 'function')

  const contributions = []
  const events = []
  const ctx = {
    rest: async () => ({}),
    register: c => (contributions.push(c), () => {}),
    registerMany: cs => (contributions.push(...cs), () => {}),
    onEvent: (type, fn) => (events.push(type), () => {}),
    onDispose: () => {}
  }
  plugin.register(ctx)

  const palette = contributions.find(c => c.area === 'palette')
  assert.ok(palette, 'palette command registered')
  assert.equal(palette.data.label, 'Spawn session with report')
  assert.equal(typeof palette.data.run, 'function')
  assert.ok(contributions.find(c => c.area === 'composer.top' && typeof c.render === 'function'), 'proposal card strip registered')
  assert.ok(contributions.find(c => c.area === 'statusBar.right' && typeof c.render === 'function'), 'dialog host registered')
  const top = contributions.filter(c => c.area === 'composer.top').map(c => c.id).sort()
  assert.deepEqual(top, ['child-header', 'children', 'proposals'], 'composer.top: header, status cards, proposals')
  const row = contributions.find(c => c.area === 'sessionRow.leading')
  assert.ok(row && typeof row.data.render === 'function', 'sidebar row badge registered')
  row.data.render({ sessionId: 'ses-x' })
  for (const e of ['child.proposed', 'child.dismissed', 'child.created', 'child.status']) {
    assert.ok(events.includes(`plugin.spawn-session.${e}`), `listens to ${e}`)
  }
  // Rendering the mount points must not throw with empty state.
  for (const c of contributions) if (c.render) c.render()
  console.log(`smoke ok: ${contributions.length} contributions, ${events.length} event listeners`)
} finally {
  rmSync(dir, { recursive: true, force: true })
}
