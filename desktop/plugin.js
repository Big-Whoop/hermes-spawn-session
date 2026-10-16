/**
 * spawn-session — desktop half (SPEC.md section 7; decisions D2, D3, D6, D10).
 *
 * - ⌘K palette command "Spawn session with report": dialog with title, task,
 *   context and a model/effort picker defaulting to the focused session's
 *   (A's) model. Start creates B immediately (user-initiated) and opens it as
 *   a tab. Blocked while the focused session is itself a spawned child (D10).
 * - Confirmation card in A for agent `own_initiative` (or cost/cap-limited)
 *   proposals: title, task, context, model; buttons Start / Edit / Dismiss.
 *   Rendered in the composer's top strip of the session that owns it.
 * - `plugin.spawn-session.child.created` -> open B as a tab (SPEC Q2).
 *
 * Backend: dashboard/plugin_api.py via ctx.rest (namespace
 * /api/plugins/spawn-session). Live updates via host.onEvent with a polling
 * fallback (refetchInterval), as the SDK docs require.
 *
 * Plain ESM, loaded uncompiled: jsx() calls only; imports limited to
 * @hermes/plugin-sdk, react and react/jsx-runtime. No hardcoded colours.
 */

import {
  atom,
  Badge,
  Button,
  COMPOSER_AREAS,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  host,
  Input,
  PALETTE_AREA,
  queryClient,
  STATUSBAR_AREAS,
  Textarea,
  useQuery,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'spawn-session'
const EFFORTS = ['low', 'medium', 'high', 'xhigh']
const POLL_MS = 15000

// Dialog state shared by the palette command (writer) and the mounted dialog
// host (reader). `mode: 'new'` = ⌘K spawn; `mode: 'edit'` = edit a proposal.
const $dialog = atom(null)

let rest = null // ctx.rest, bound in register()

const proposalsKey = sessionId => [ID, 'proposals', sessionId]

function errorText(err) {
  if (!err) return 'Unknown error'
  const raw = err.detail || err.message || String(err)
  return typeof raw === 'string' ? raw : JSON.stringify(raw)
}

function openTab(childId) {
  if (!childId) return
  Promise.resolve(host.openSession(childId, { intent: 'tab' })).catch(err =>
    host.notifyError(err, 'Could not open the spawned session')
  )
}

function modelRefsFrom(options) {
  const refs = []
  for (const p of (options && options.providers) || []) {
    for (const m of p.models || []) refs.push(`${p.slug}:${m}`)
  }
  return refs
}

// ------------------------------------------------------------------ form

const fieldLabel = text =>
  jsx('label', { className: 'text-[0.6875rem] font-medium text-(--ui-text-secondary)', children: text })

const selectClass =
  'h-8 w-full rounded-[4px] border border-(--ui-stroke-secondary) bg-transparent px-2 text-xs text-foreground outline-none focus-visible:border-(--ui-accent)'

function SpawnForm({ state, onClose }) {
  const sessionId = state.sessionId
  const proposal = state.proposal || null
  const [title, setTitle] = useState(proposal ? proposal.title || '' : '')
  const [task, setTask] = useState(proposal ? proposal.task || '' : '')
  const [context, setContext] = useState(proposal ? proposal.context || '' : '')
  const [model, setModel] = useState(proposal ? proposal.model || '' : '')
  const [effort, setEffort] = useState(proposal ? proposal.effort || '' : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const defaults = useQuery({
    queryKey: [ID, 'defaults', sessionId],
    queryFn: () => rest(`/defaults?session_id=${encodeURIComponent(sessionId)}`),
    enabled: Boolean(sessionId),
    staleTime: 5000
  })
  const options = useQuery({
    queryKey: [ID, 'model-options', sessionId],
    queryFn: () => host.request('model.options', {}),
    staleTime: 60000
  })

  // D6: default = A's model/effort (only for a fresh ⌘K spawn).
  useEffect(() => {
    const d = defaults.data
    if (!d || proposal) return
    if (!model && d.model) setModel(d.model)
    if (!effort && d.effort) setEffort(d.effort)
  }, [defaults.data])

  const refs = modelRefsFrom(options.data)
  if (model && !refs.includes(model)) refs.unshift(model)
  const blocked = !proposal && defaults.data && !defaults.data.can_spawn

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const body = { title, task, context, model: model || null, effort: effort || null }
      const res = proposal
        ? await rest('/confirm', { method: 'POST', body: { ...body, handover_id: proposal.handover_id } })
        : await rest('/spawn', { method: 'POST', body: { ...body, session_id: sessionId } })
      queryClient.invalidateQueries({ queryKey: [ID, 'proposals'] })
      host.notify({ kind: 'success', message: `Spawned “${title}”` })
      onClose()
      openTab(res && res.child_session_id)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const canSubmit = !busy && !blocked && title.trim() && task.trim()

  return jsxs('div', {
    className: 'flex flex-col gap-3',
    children: [
      blocked &&
        jsx('div', {
          className: 'rounded-[4px] border border-(--ui-stroke-secondary) p-2 text-xs text-(--ui-text-secondary)',
          children: defaults.data.is_child
            ? 'This is a spawned session — it cannot spawn further sessions (one level only).'
            : 'Spawning is only available in Hermes Desktop sessions.'
        }),
      fieldLabel('Title'),
      jsx(Input, { value: title, maxLength: 80, placeholder: 'Short title for the new session', onChange: e => setTitle(e.target.value), autoFocus: true }),
      fieldLabel('Task'),
      jsx(Textarea, { value: task, rows: 5, placeholder: 'Detailed instructions for the new session', onChange: e => setTask(e.target.value) }),
      fieldLabel('Context'),
      jsx(Textarea, { value: context, rows: 3, placeholder: 'Short background (optional)', onChange: e => setContext(e.target.value) }),
      jsxs('div', {
        className: 'grid grid-cols-[1fr_8rem] gap-2',
        children: [
          jsxs('div', {
            className: 'flex flex-col gap-1',
            children: [
              fieldLabel('Model'),
              jsxs('select', {
                className: selectClass,
                value: model,
                onChange: e => setModel(e.target.value),
                children: [
                  !model && jsx('option', { value: '', children: options.isLoading ? 'Loading…' : 'Parent’s model' }),
                  ...refs.map(r => jsx('option', { value: r, children: r }, r))
                ]
              })
            ]
          }),
          jsxs('div', {
            className: 'flex flex-col gap-1',
            children: [
              fieldLabel('Effort'),
              jsxs('select', {
                className: selectClass,
                value: effort,
                onChange: e => setEffort(e.target.value),
                children: [
                  jsx('option', { value: '', children: 'default' }),
                  ...EFFORTS.map(x => jsx('option', { value: x, children: x }, x))
                ]
              })
            ]
          })
        ]
      }),
      error && jsx('div', { className: 'text-xs text-destructive', role: 'alert', children: error }),
      jsxs(DialogFooter, {
        children: [
          jsx(Button, { variant: 'ghost', onClick: onClose, disabled: busy, children: 'Cancel' }),
          jsx(Button, { onClick: submit, disabled: !canSubmit, children: busy ? 'Starting…' : 'Start' })
        ]
      })
    ]
  })
}

function SpawnDialogHost() {
  const state = useValue($dialog)
  const close = () => $dialog.set(null)
  return jsx(Dialog, {
    open: Boolean(state),
    onOpenChange: open => {
      if (!open) close()
    },
    children:
      state &&
      jsxs(DialogContent, {
        className: 'max-w-lg',
        children: [
          jsxs(DialogHeader, {
            children: [
              jsx(DialogTitle, { children: state.proposal ? 'Edit proposed session' : 'Spawn session with report' }),
              jsx(DialogDescription, {
                children: 'Starts a new visible session that reports its result back to this conversation.'
              })
            ]
          }),
          jsx(SpawnForm, { state, onClose: close }, state.key)
        ]
      })
  })
}

// ------------------------------------------------------------------ proposal card

function ProposalCard({ proposal }) {
  const [busy, setBusy] = useState(null)
  const [open, setOpen] = useState(false)

  const act = async (kind) => {
    setBusy(kind)
    try {
      if (kind === 'start') {
        const res = await rest('/confirm', { method: 'POST', body: { handover_id: proposal.handover_id } })
        host.notify({ kind: 'success', message: `Spawned “${proposal.title}”` })
        openTab(res && res.child_session_id)
      } else {
        await rest('/dismiss', { method: 'POST', body: { handover_id: proposal.handover_id } })
      }
      queryClient.invalidateQueries({ queryKey: [ID, 'proposals'] })
    } catch (err) {
      host.notifyError(err, `Could not ${kind} the proposal`)
    } finally {
      setBusy(null)
    }
  }

  return jsxs('div', {
    'data-spawn-session-card': proposal.handover_id,
    className: 'mx-2 mb-1.5 flex flex-col gap-1.5 rounded-[4px] border border-(--ui-stroke-secondary) p-2 text-xs',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx(Badge, { variant: 'secondary', children: 'Proposed session' }),
          jsx('span', { className: 'min-w-0 flex-1 truncate font-medium text-foreground', title: proposal.title, children: proposal.title }),
          jsx('span', { className: 'shrink-0 text-(--ui-text-tertiary)', children: proposal.model || '' })
        ]
      }),
      jsx('button', {
        type: 'button',
        className: 'text-left text-(--ui-text-secondary) hover:text-foreground',
        onClick: () => setOpen(v => !v),
        children: open ? 'Hide task and context' : 'Show task and context'
      }),
      open &&
        jsxs('div', {
          className: 'flex max-h-48 flex-col gap-1 overflow-auto whitespace-pre-wrap text-(--ui-text-secondary)',
          children: [
            jsx('div', { className: 'font-medium text-foreground', children: 'Task' }),
            jsx('div', { children: proposal.task }),
            proposal.context && jsx('div', { className: 'font-medium text-foreground', children: 'Context' }),
            proposal.context && jsx('div', { children: proposal.context })
          ]
        }),
      proposal.reasons && proposal.reasons.length > 0 &&
        jsx('div', { className: 'text-(--ui-text-tertiary)', children: proposal.reasons.join(' · ') }),
      jsxs('div', {
        className: 'flex justify-end gap-1.5',
        children: [
          jsx(Button, { size: 'xs', variant: 'ghost', disabled: Boolean(busy), onClick: () => act('dismiss'), children: busy === 'dismiss' ? 'Dismissing…' : 'Dismiss' }),
          jsx(Button, {
            size: 'xs',
            variant: 'outline',
            disabled: Boolean(busy),
            onClick: () => $dialog.set({ key: `edit-${proposal.handover_id}-${Date.now()}`, sessionId: proposal.parent_session_id, proposal }),
            children: 'Edit'
          }),
          jsx(Button, { size: 'xs', disabled: Boolean(busy), onClick: () => act('start'), children: busy === 'start' ? 'Starting…' : 'Start' })
        ]
      })
    ]
  })
}

function ProposalStrip() {
  const sessionId = useValue(host.state.focusedStoredSessionId)
  const q = useQuery({
    queryKey: proposalsKey(sessionId),
    queryFn: () => rest(`/proposals?session_id=${encodeURIComponent(sessionId)}`),
    enabled: Boolean(sessionId),
    refetchInterval: POLL_MS
  })
  const items = (q.data && q.data.proposals) || []
  if (!sessionId || items.length === 0) return null
  return jsx('div', {
    className: 'flex flex-col pt-1.5',
    children: items.map(p => jsx(ProposalCard, { proposal: p }, p.handover_id))
  })
}

// ------------------------------------------------------------------ command

async function openSpawnDialog() {
  const sessionId = host.state.focusedStoredSessionId.get()
  if (!sessionId) {
    host.notify({ kind: 'info', message: 'Open a chat first — the new session reports back into it.' })
    return
  }
  try {
    const d = await rest(`/defaults?session_id=${encodeURIComponent(sessionId)}`)
    if (d && d.is_child) {
      host.notify({ kind: 'info', message: 'This is a spawned session — it cannot spawn further sessions (one level only).' })
      return
    }
  } catch (err) {
    host.notifyError(err, 'spawn-session backend unavailable (is the plugin in plugins.enabled?)')
    return
  }
  $dialog.set({ key: `new-${Date.now()}`, sessionId, proposal: null })
}

export default {
  id: ID,
  name: 'Spawn session',
  register(ctx) {
    rest = ctx.rest
    ctx.onDispose(() => $dialog.set(null))

    ctx.registerMany([
      {
        id: 'spawn',
        area: PALETTE_AREA,
        data: {
          id: 'spawn-session.spawn',
          label: 'Spawn session with report',
          keywords: ['spawn', 'session', 'report', 'handover', 'child', 'nested'],
          run: () => void openSpawnDialog()
        }
      },
      // Permanent mount point for the dialog (renders nothing visible itself).
      { id: 'dialog-host', area: STATUSBAR_AREAS.right, order: 990, render: () => jsx(SpawnDialogHost, {}) },
      { id: 'proposals', area: COMPOSER_AREAS.top, render: () => jsx(ProposalStrip, {}) }
    ])

    const refresh = () => queryClient.invalidateQueries({ queryKey: [ID, 'proposals'] })
    ctx.onEvent(`plugin.${ID}.child.proposed`, refresh)
    ctx.onEvent(`plugin.${ID}.child.dismissed`, refresh)
    // Agent-created (immediate) children open as a tab (SPEC Q2 / AT5.2).
    // User-initiated spawns are opened by the dialog itself.
    ctx.onEvent(`plugin.${ID}.child.created`, ev => {
      const p = (ev && ev.payload) || {}
      refresh()
      if (p.initiator === 'agent') openTab(p.child_session_id)
    })
  }
}
