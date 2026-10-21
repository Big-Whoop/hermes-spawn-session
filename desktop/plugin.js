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
 * - Header in B (D9): "Started by Hermes from <A title>" (link to A) with
 *   collapsible Task and Context blocks; `Detached` marker after D11 detach.
 * - Status cards in A (D9/D11): one per started child (running / reported /
 *   delivered / abandoned / detached) with Open, Abort and Detach buttons.
 * - "N open report(s)" notice in A (D8): undelivered reports or notices kept
 *   while A was closed; Deliver injects them into A on click.
 * - Sidebar (D9 / SPEC Q3): the desktop SDK cannot nest rows, so the fallback
 *   applies: the backend titles B `↳ <title>` (`↳ Detached: <title>` after
 *   detach) and a SESSION_ROW_AREAS.leading badge marks child rows with their
 *   parent in the tooltip. Recents order is not rewritten: the SDK can only
 *   replace the whole manual order and cannot read it, so a reorder would
 *   clobber the user's own order.
 *
 * Backend: dashboard/plugin_api.py via ctx.rest (namespace
 * /api/plugins/spawn-session). Live updates via host.onEvent with a polling
 * fallback (refetchInterval), as the SDK docs require.
 *
 * Testability (e2e/specs/desktop.ui.spec.ts): every element an acceptance test
 * clicks or asserts carries a stable `data-spawn-session-*` attribute:
 * containers `-dialog`, `-card`, `-status`, `-header`, `-open-reports`, `-row`;
 * inputs `-field` (title/task/context/model/effort); buttons `-action`
 * (start/cancel/dismiss/edit/open/abort/detach/detach-confirm/deliver/
 * open-parent/toggle-*); texts `-status-text`, `-reasons`, `-title`, `-model`,
 * `-detached`, `-blocked`. Keep them stable; the specs depend on them.
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
  SESSION_ROW_AREAS,
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
const childrenKey = sessionId => [ID, 'children', sessionId]
const childInfoKey = sessionId => [ID, 'child', sessionId]
const TREE_KEY = [ID, 'tree']

const refreshAll = () => queryClient.invalidateQueries({ queryKey: [ID] })

function errorText(err) {
  if (!err) return 'Unknown error'
  const raw = err.detail || err.message || String(err)
  return typeof raw === 'string' ? raw : JSON.stringify(raw)
}

function openSession(id, intent) {
  if (!id) return
  Promise.resolve(host.openSession(id, { intent })).catch(err =>
    host.notifyError(err, 'Could not open the session')
  )
}

const openTab = childId => openSession(childId, 'tab')

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
          'data-spawn-session-blocked': defaults.data.is_child ? 'child' : 'surface',
          className: 'rounded-[4px] border border-(--ui-stroke-secondary) p-2 text-xs text-(--ui-text-secondary)',
          children: defaults.data.is_child
            ? 'This is a spawned session — it cannot spawn further sessions (one level only).'
            : 'Spawning is only available in Hermes Desktop sessions.'
        }),
      fieldLabel('Title'),
      jsx(Input, { 'data-spawn-session-field': 'title', value: title, maxLength: 80, placeholder: 'Short title for the new session', onChange: e => setTitle(e.target.value), autoFocus: true }),
      fieldLabel('Task'),
      jsx(Textarea, { 'data-spawn-session-field': 'task', value: task, rows: 5, placeholder: 'Detailed instructions for the new session', onChange: e => setTask(e.target.value) }),
      fieldLabel('Context'),
      jsx(Textarea, { 'data-spawn-session-field': 'context', value: context, rows: 3, placeholder: 'Short background (optional)', onChange: e => setContext(e.target.value) }),
      jsxs('div', {
        className: 'grid grid-cols-[1fr_8rem] gap-2',
        children: [
          jsxs('div', {
            className: 'flex flex-col gap-1',
            children: [
              fieldLabel('Model'),
              jsxs('select', {
                'data-spawn-session-field': 'model',
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
                'data-spawn-session-field': 'effort',
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
      error && jsx('div', { 'data-spawn-session-error': '', className: 'text-xs text-destructive', role: 'alert', children: error }),
      jsxs(DialogFooter, {
        children: [
          jsx(Button, { 'data-spawn-session-action': 'cancel', variant: 'ghost', onClick: onClose, disabled: busy, children: 'Cancel' }),
          jsx(Button, { 'data-spawn-session-action': 'start', onClick: submit, disabled: !canSubmit, children: busy ? 'Starting…' : 'Start' })
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
        'data-spawn-session-dialog': state.proposal ? 'edit' : 'new',
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
          jsx(Badge, { 'data-spawn-session-badge': 'proposed', variant: 'secondary', children: 'Proposed session' }),
          jsx('span', { 'data-spawn-session-title': '', className: 'min-w-0 flex-1 truncate font-medium text-foreground', title: proposal.title, children: proposal.title }),
          jsx('span', { 'data-spawn-session-model': proposal.model || '', className: 'shrink-0 text-(--ui-text-tertiary)', children: proposal.model || '' })
        ]
      }),
      jsx('button', {
        type: 'button',
        'data-spawn-session-action': 'toggle-details',
        'aria-expanded': open,
        className: 'text-left text-(--ui-text-secondary) hover:text-foreground',
        onClick: () => setOpen(v => !v),
        children: open ? 'Hide task and context' : 'Show task and context'
      }),
      open &&
        jsxs('div', {
          className: 'flex max-h-48 flex-col gap-1 overflow-auto whitespace-pre-wrap text-(--ui-text-secondary)',
          children: [
            jsx('div', { className: 'font-medium text-foreground', children: 'Task' }),
            jsx('div', { 'data-spawn-session-task': '', children: proposal.task }),
            proposal.context && jsx('div', { className: 'font-medium text-foreground', children: 'Context' }),
            proposal.context && jsx('div', { 'data-spawn-session-context': '', children: proposal.context })
          ]
        }),
      proposal.reasons && proposal.reasons.length > 0 &&
        jsx('div', {
          // AT2.3 (cost note) / AT3.2 (limit reached): why confirmation is needed.
          'data-spawn-session-reasons': proposal.reasons.length,
          className: 'text-(--ui-text-tertiary)',
          children: proposal.reasons.join(' · ')
        }),
      jsxs('div', {
        className: 'flex justify-end gap-1.5',
        children: [
          jsx(Button, { 'data-spawn-session-action': 'dismiss', size: 'xs', variant: 'ghost', disabled: Boolean(busy), onClick: () => act('dismiss'), children: busy === 'dismiss' ? 'Dismissing…' : 'Dismiss' }),
          jsx(Button, {
            'data-spawn-session-action': 'edit',
            size: 'xs',
            variant: 'outline',
            disabled: Boolean(busy),
            onClick: () => $dialog.set({ key: `edit-${proposal.handover_id}-${Date.now()}`, sessionId: proposal.parent_session_id, proposal }),
            children: 'Edit'
          }),
          jsx(Button, { 'data-spawn-session-action': 'start', size: 'xs', disabled: Boolean(busy), onClick: () => act('start'), children: busy === 'start' ? 'Starting…' : 'Start' })
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


// ------------------------------------------------------------------ B header (D9)

function Collapsible({ id, label, text }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return jsxs('div', {
    'data-spawn-session-collapsible': id,
    className: 'flex flex-col gap-1',
    children: [
      jsx('button', {
        type: 'button',
        'data-spawn-session-action': `toggle-${id}`,
        'aria-expanded': open,
        className: 'text-left font-medium text-(--ui-text-secondary) hover:text-foreground',
        onClick: () => setOpen(v => !v),
        children: `${open ? '▾' : '▸'} ${label}`
      }),
      open &&
        jsx('div', {
          'data-spawn-session-collapsible-body': id,
          className: 'max-h-48 overflow-auto whitespace-pre-wrap pl-3 text-(--ui-text-secondary)',
          children: text
        })
    ]
  })
}

function ChildHeader() {
  const sessionId = useValue(host.state.focusedStoredSessionId)
  const q = useQuery({
    queryKey: childInfoKey(sessionId),
    queryFn: () => rest(`/child?session_id=${encodeURIComponent(sessionId)}`),
    enabled: Boolean(sessionId),
    refetchInterval: POLL_MS
  })
  const info = q.data
  if (!sessionId || !info || !info.is_child) return null
  const parentLabel = info.parent_title || info.parent_session_id || 'parent session'
  return jsxs('div', {
    'data-spawn-session-header': info.handover_id,
    className: 'mx-2 mb-1.5 mt-1.5 flex flex-col gap-1.5 rounded-[4px] border border-(--ui-stroke-secondary) p-2 text-xs',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-1.5',
        children: [
          info.detached && jsx(Badge, { 'data-spawn-session-detached': '', variant: 'secondary', children: 'Detached' }),
          jsx('span', { className: 'text-(--ui-text-secondary)', children: 'Started by Hermes from' }),
          jsx('button', {
            type: 'button',
            'data-spawn-session-action': 'open-parent',
            'data-spawn-session-parent': info.parent_session_id || '',
            className: 'min-w-0 truncate font-medium text-foreground underline-offset-2 hover:underline',
            title: parentLabel,
            onClick: () => openSession(info.parent_session_id, 'in-place'),
            children: parentLabel
          }),
          jsx('span', { 'data-spawn-session-status-text': info.status, className: 'ml-auto shrink-0 text-(--ui-text-tertiary)', children: info.status })
        ]
      }),
      jsx(Collapsible, { id: 'task', label: 'Task', text: info.task }),
      jsx(Collapsible, { id: 'context', label: 'Context', text: info.context })
    ]
  })
}

// ------------------------------------------------------------------ A status cards (D8/D9/D11)

const ACTIVE = new Set(['running', 'reported', 'delivered'])

function StatusCard({ child }) {
  const [busy, setBusy] = useState(null)
  const [confirmDetach, setConfirmDetach] = useState(false)

  const act = async kind => {
    setBusy(kind)
    try {
      if (kind === 'abort') {
        await rest('/abort', { method: 'POST', body: { handover_id: child.handover_id } })
        host.notify({ kind: 'info', message: `Aborted “${child.title}”` })
      } else {
        await rest('/detach', { method: 'POST', body: { handover_id: child.handover_id, confirm: true } })
        host.notify({ kind: 'info', message: `Detached “${child.title}”` })
      }
      refreshAll()
    } catch (err) {
      host.notifyError(err, `Could not ${kind} the session`)
    } finally {
      setBusy(null)
      setConfirmDetach(false)
    }
  }

  const canAbort = child.status === 'running'
  const canDetach = ACTIVE.has(child.status)
  return jsxs('div', {
    'data-spawn-session-status': child.handover_id,
    className: 'mx-2 mb-1.5 flex flex-col gap-1.5 rounded-[4px] border border-(--ui-stroke-secondary) p-2 text-xs',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx(Badge, { 'data-spawn-session-status-text': child.status, variant: 'secondary', children: child.status }),
          jsx('span', { 'data-spawn-session-title': '', className: 'min-w-0 flex-1 truncate font-medium text-foreground', title: child.title, children: child.title }),
          child.reports > 0 &&
            jsx('span', { 'data-spawn-session-reports': child.reports, className: 'shrink-0 text-(--ui-text-tertiary)', children: `${child.reports} report${child.reports === 1 ? '' : 's'}` })
        ]
      }),
      confirmDetach &&
        jsx('div', {
          'data-spawn-session-detach-warning': '',
          className: 'text-(--ui-text-secondary)',
          children: 'Detach is irreversible: the session continues on its own and no report is sent back.'
        }),
      jsxs('div', {
        className: 'flex justify-end gap-1.5',
        children: [
          child.child_session_id &&
            jsx(Button, { 'data-spawn-session-action': 'open', size: 'xs', variant: 'ghost', disabled: Boolean(busy), onClick: () => openSession(child.child_session_id, 'tab'), children: 'Open' }),
          canAbort &&
            jsx(Button, { 'data-spawn-session-action': 'abort', size: 'xs', variant: 'ghost', disabled: Boolean(busy), onClick: () => act('abort'), children: busy === 'abort' ? 'Aborting…' : 'Abort' }),
          canDetach && !confirmDetach &&
            jsx(Button, { 'data-spawn-session-action': 'detach', size: 'xs', variant: 'outline', disabled: Boolean(busy), onClick: () => setConfirmDetach(true), children: 'Detach' }),
          confirmDetach &&
            jsx(Button, { 'data-spawn-session-action': 'detach-cancel', size: 'xs', variant: 'ghost', disabled: Boolean(busy), onClick: () => setConfirmDetach(false), children: 'Cancel' }),
          confirmDetach &&
            jsx(Button, { 'data-spawn-session-action': 'detach-confirm', size: 'xs', disabled: Boolean(busy), onClick: () => act('detach'), children: busy === 'detach' ? 'Detaching…' : 'Detach now' })
        ]
      })
    ]
  })
}

function OpenReportsNotice({ sessionId, count }) {
  const [busy, setBusy] = useState(false)
  const deliver = async () => {
    setBusy(true)
    try {
      const res = await rest('/deliver', { method: 'POST', body: { session_id: sessionId } })
      const n = ((res && res.queued) || 0) + ((res && res.notices) || 0)
      host.notify({
        kind: n ? 'success' : 'info',
        message: n ? `Delivered ${n} item${n === 1 ? '' : 's'} to this session` : 'Nothing could be delivered — is this session live?'
      })
      refreshAll()
    } catch (err) {
      host.notifyError(err, 'Could not deliver the open reports')
    } finally {
      setBusy(false)
    }
  }
  return jsxs('div', {
    'data-spawn-session-open-reports': count,
    className: 'mx-2 mb-1.5 flex items-center gap-2 rounded-[4px] border border-(--ui-accent) p-2 text-xs',
    children: [
      jsx('span', { 'data-spawn-session-open-reports-text': '', className: 'flex-1 font-medium text-foreground', children: `${count} open report${count === 1 ? '' : 's'}` }),
      jsx(Button, { 'data-spawn-session-action': 'deliver', size: 'xs', disabled: busy, onClick: deliver, children: busy ? 'Delivering…' : 'Deliver' })
    ]
  })
}

function ChildrenStrip() {
  const sessionId = useValue(host.state.focusedStoredSessionId)
  const q = useQuery({
    queryKey: childrenKey(sessionId),
    queryFn: () => rest(`/children?session_id=${encodeURIComponent(sessionId)}`),
    enabled: Boolean(sessionId),
    refetchInterval: POLL_MS
  })
  const data = q.data || {}
  // Finished children (abandoned / detached) are history: keep only active cards.
  const items = (data.children || []).filter(c => ACTIVE.has(c.status))
  const open = data.open_reports || 0
  if (!sessionId || (items.length === 0 && open === 0)) return null
  return jsxs('div', {
    className: 'flex flex-col pt-1.5',
    children: [
      open > 0 && jsx(OpenReportsNotice, { sessionId, count: open }),
      ...items.map(c => jsx(StatusCard, { child: c }, c.handover_id))
    ]
  })
}

// ------------------------------------------------------------------ sidebar row badge (D9 / Q3)

function RowBadge({ sessionId }) {
  const q = useQuery({ queryKey: TREE_KEY, queryFn: () => rest('/tree'), staleTime: POLL_MS, refetchInterval: POLL_MS })
  const entry = q.data && q.data.children && q.data.children[sessionId]
  if (!entry) return null
  return jsx('span', {
    'data-spawn-session-row': entry.handover_id,
    'data-spawn-session-row-status': entry.status,
    className: 'shrink-0 text-[0.6875rem] text-(--ui-text-tertiary)',
    title: `Spawned session (${entry.status})`,
    children: entry.status === 'detached' ? '⤳' : '↳'
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
  // Opt-in (decision Q3): the desktop half stays off until the user enables
  // it in Desktop Capabilities -> Plugins.
  defaultEnabled: false,
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
      { id: 'proposals', area: COMPOSER_AREAS.top, render: () => jsx(ProposalStrip, {}) },
      { id: 'child-header', area: COMPOSER_AREAS.top, order: -10, render: () => jsx(ChildHeader, {}) },
      { id: 'children', area: COMPOSER_AREAS.top, order: 10, render: () => jsx(ChildrenStrip, {}) },
      { id: 'row-badge', area: SESSION_ROW_AREAS.leading, data: { render: ({ sessionId }) => jsx(RowBadge, { sessionId }) } }
    ])

    const refresh = refreshAll
    ctx.onEvent(`plugin.${ID}.child.proposed`, refresh)
    ctx.onEvent(`plugin.${ID}.child.dismissed`, refresh)
    ctx.onEvent(`plugin.${ID}.child.status`, refresh)
    // Agent-created (immediate) children open as a tab (SPEC Q2 / AT5.2).
    // User-initiated spawns are opened by the dialog itself.
    ctx.onEvent(`plugin.${ID}.child.created`, ev => {
      const p = (ev && ev.payload) || {}
      refresh()
      if (p.initiator === 'agent') openTab(p.child_session_id)
    })
  }
}
