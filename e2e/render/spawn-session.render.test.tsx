/**
 * Render tests for desktop/plugin.js against the REAL @hermes/plugin-sdk.
 *
 * Runs inside a hermes-agent checkout (apps/desktop) under its vitest `ui`
 * project (jsdom). e2e/render/run_render_tests.sh copies this file and
 * desktop/plugin.js into <checkout>/apps/desktop/src/__spawn_session__/.
 *
 * Only ctx.rest is a stub: register() gets the host's real createPluginContext
 * with `rest` replaced, so registry, areas, host.state, queryClient, Button,
 * Badge are all the real SDK.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createElement, Fragment } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { COMPOSER_AREAS, queryClient } from '@hermes/plugin-sdk'
import { createPluginContext } from '@/contrib/plugin'
import { registry } from '@/contrib/registry'
import { $selectedStoredSessionId } from '@/store/session'

// @ts-expect-error plain ESM plugin, no types
import plugin from './plugin.js'

const SESSION = 'sess-A'

type RestCall = { path: string; opts?: { method?: string; body?: unknown } }

function mount(routes: Record<string, unknown>) {
  const calls: RestCall[] = []
  const rest = vi.fn(async (path: string, opts?: RestCall['opts']) => {
    calls.push({ path, opts })
    const key = Object.keys(routes).find(k => path.startsWith(k))
    return key ? routes[key] : {}
  })
  const disposers: Array<() => void> = []
  const ctx = { ...createPluginContext('spawn-session', d => disposers.push(d)), rest }
  plugin.register(ctx)

  const slots = registry.getArea(COMPOSER_AREAS.top)
  expect(slots.map(s => s.id)).toEqual(
    expect.arrayContaining(['spawn-session:proposals', 'spawn-session:children', 'spawn-session:child-header'])
  )
  // The desktop app mounts the SDK's queryClient at its root; mirror that.
  const view = render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      ...slots.map(s => createElement(Fragment, { key: s.id }, s.render?.({} as never)))
    )
  )

  return { calls, rest, disposers, view }
}

let current: ReturnType<typeof mount> | undefined

beforeEach(() => {
  queryClient.clear()
  $selectedStoredSessionId.set(SESSION)
})

afterEach(() => {
  cleanup()
  current?.disposers.forEach(d => d())
  current = undefined
  $selectedStoredSessionId.set(null)
})

describe('spawn-session desktop half (real SDK, jsdom)', () => {
  it('renders a status card and Abort posts /abort with the handover id', async () => {
    current = mount({
      '/children': {
        open_reports: 0,
        children: [{ handover_id: 'h-1', title: 'Research child', status: 'running', reports: 2, child_session_id: 'sess-B' }]
      },
      '/proposals': { proposals: [] },
      '/child': { is_child: false }
    })

    expect(await screen.findByText('Research child')).toBeTruthy()
    expect(screen.getByText('running')).toBeTruthy()
    expect(screen.getByText('2 reports')).toBeTruthy()
    expect(current.calls.some(c => c.path === `/children?session_id=${SESSION}`)).toBe(true)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Abort' }))
    })

    await waitFor(() =>
      expect(current!.calls).toContainEqual({ path: '/abort', opts: { method: 'POST', body: { handover_id: 'h-1' } } })
    )
  })

  it('renders a proposal card; Start posts /confirm and Dismiss posts /dismiss', async () => {
    current = mount({
      '/proposals': {
        proposals: [
          { handover_id: 'h-2', parent_session_id: SESSION, title: 'Proposed child', task: 'Do X', model: 'prov:model-1', reasons: ['cost'] }
        ]
      },
      '/children': { children: [], open_reports: 0 },
      '/child': { is_child: false },
      '/confirm': { child_session_id: 'sess-C' },
      '/dismiss': { ok: true }
    })

    expect(await screen.findByText('Proposed child')).toBeTruthy()
    expect(screen.getByText('Proposed session')).toBeTruthy()
    expect(screen.getByText('prov:model-1')).toBeTruthy()
    expect(screen.getByText('cost')).toBeTruthy()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    })
    await waitFor(() =>
      expect(current!.calls).toContainEqual({ path: '/confirm', opts: { method: 'POST', body: { handover_id: 'h-2' } } })
    )

    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }))
    })
    await waitFor(() =>
      expect(current!.calls).toContainEqual({ path: '/dismiss', opts: { method: 'POST', body: { handover_id: 'h-2' } } })
    )
  })
})
