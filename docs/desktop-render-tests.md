# Desktop render tests (jsdom + real @hermes/plugin-sdk)

Spike result for research Option E: can `desktop/plugin.js` be rendered and
asserted without Electron, using the real `@hermes/plugin-sdk`?

## Verdict: works

`desktop/plugin.js` loads inside a hermes-agent v0.22.2 checkout under the
upstream vitest `ui` project (jsdom). `@hermes/plugin-sdk` resolves through
upstream's own Vite alias to `apps/desktop/src/sdk/index.ts`. `register(ctx)`
gets the host's real `createPluginContext('spawn-session')`; only `ctx.rest`
is replaced with a recording stub. The contributions land in the real
registry, the real `COMPOSER_AREAS.top` slots are rendered, and the real
`Button`/`Badge`, `host.state.focusedStoredSessionId` (driven through
`$selectedStoredSessionId`) and `queryClient` are used.

The two example tests (`e2e/render/spawn-session.render.test.tsx`) check:

1. Status card: the title, status badge and "2 reports" text are rendered,
   `/children?session_id=…` is fetched, and clicking Abort calls
   `ctx.rest('/abort', { method: 'POST', body: { handover_id } })`.
2. Proposal card: the title, "Proposed session" badge, model and reasons are
   rendered. Start calls `/confirm` and Dismiss calls `/dismiss`, each with
   the handover id.

Negative check: changing `/abort` to `/abortX` in the copied plugin makes
test 1 fail, and test 2 still passes.

## What it catches and what it doesn't

Catches:
- SDK export drift. A renamed or removed export such as `COMPOSER_AREAS`,
  `useValue` or `Button` breaks the import against the real SDK.
- Render errors.
- Wrong REST path or body sent from a button.
- Wrong area ids.

Does not catch:
- The Electron runtime loader (`window.__HERMES_PLUGIN_SDK__` mapping,
  opt-in enablement).
- The real backend.
- Layout and CSS.

Those stay with the Playwright desktop specs (k8s Job) and the backend specs.

## Commands

    cd e2e && npm run test:render
    # equivalent: bash e2e/render/run_render_tests.sh

Env:
- `HERMES_AGENT_CHECKOUT`: where the checkout lives. Default:
  `$TMPDIR/hermes-agent-v0222`.
- `HERMES_AGENT_REF`: the tag to clone. Default: `v0.22.2`.

The script:
1. Shallow-clones hermes-agent at the tag if the checkout is missing.
2. Runs `npm ci --include=dev --workspace apps/desktop --include-workspace-root=false --ignore-scripts` if `node_modules/.bin/vitest` is missing.
3. Copies `desktop/plugin.js` and `e2e/render/*.render.test.tsx` into
   `apps/desktop/src/__spawn_session__/`. That directory is removed on exit.
4. Runs `NODE_ENV=development node_modules/.bin/vitest run --project ui src/__spawn_session__`.

The checkout is a throwaway clone under the scratch dir and is never under
`/opt/hermes`. The only write into it is the temporary test directory.

## Pitfalls found

- This pod exports `NODE_ENV=production`, so npm silently omits
  devDependencies (vitest, jsdom). The fix is `--include=dev`. `npx vitest`
  then fetches an unrelated vitest 5.x and fails on `vitest/config`, so the
  script calls the checkout's own binary instead.
- The plugin's `useQuery` needs a `QueryClientProvider`. The desktop app
  mounts the SDK `queryClient` at its root, and the test does the same.
- Node 26 prints an `ExperimentalWarning` about `localStorage`. It is harmless
  because upstream's `vitest.setup.ts` installs a Storage.

## Cost (measured in this pod, Node 26.7.0, npm 12.0.2)

| Item | Value |
| --- | --- |
| Checkout (shallow clone v0.22.2) | 338 MB on disk, about 1 min |
| `npm ci` (desktop workspace incl. dev) | 1167 packages, 1.1 GB `node_modules`, about 2 min |
| Test run (cold, 2 tests) | about 70 s wall: about 46 s transform, 61 s import, 1.6 s tests |
| New deps in this repo | none (everything comes from the upstream lockfile) |

Most of the run time is spent transforming the SDK's import graph through the
React Compiler babel pass. The tests themselves take under 2 s.

## Recommendation: fast_gate stage 8?

Not as a mandatory stage in its current form. With a warm checkout it adds
about 70 s, and a cold start costs about 3 GB and 4 min. It also needs network
for the first clone and install. It fits better as:

- an optional stage gated on a warm checkout: run it when
  `HERMES_AGENT_CHECKOUT` exists, otherwise skip with a notice; or
- a step in the hermes-e2e k8s Job, which already builds the same checkout.

The decision belongs to whoever owns `scripts/fast_gate.sh`. This spike does
not change it.
