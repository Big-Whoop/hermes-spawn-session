# Lane 4 — Hermes STAGING instance on the user's k3s cluster (nixos-infra grounded)

Date: 2026-10-17 · Card t_a3d4b9be · Parent t_cd95f6bd · Collector t_6078e578
Scope: design evaluation only, plan options, NO infra change.
Tiers: Verified (V) = read in an authoritative source for this exact target · Plausible (P) = sound general behavior, not demonstrated on-target · Speculative (S) = untested mechanism.
Local repo state read: nixos-infra @ b96c290 (2026-10-17), custom-hermes-suite working tree, hermes-spawn-session working tree, DokuWiki KB.

## TL;DR

- The user's idea is feasible, but the cluster shape forces a specific design: everything with state lives on ONE node (wrk, `role=apps`) as static hostPath PVs (`storageClassName: ""`); there is no dynamic storage class in use, no GPU/display node in the cluster yet, and wrk is RAM-tight (live pod requests 2Gi / limit 6Gi "wrk has 6 GB until probe retires").
- A staging Deployment must NOT reuse the live `/opt/data` (single SQLite writer, RWO, Telegram long-poll) — it needs its own HERMES_HOME (emptyDir or a separate hostPath dir), its own config without a Telegram token, and its own namespace/route.
- Scale-to-0: in this Flux repo `replicas` is reconciled from Git, so `kubectl scale` alone is reverted; the documented knobs are a Git PR, `flux suspend`, or the per-object `kustomize.toolkit.fluxcd.io/reconcile: disabled` annotation. A Job (with `ttlSecondsAfterFinished`) is the cleaner fit for "run a test, then disappear" than a 0-replica Deployment. KEDA is not installed; adding it for one test instance is disproportionate.
- The dependency-consent step is the hardest automation point: Hermes docs say non-interactive installs fail closed (plugin left disabled), and upstream issue #124784 confirms the consent gate checks `isatty()`. A staging toolset must give the CLI a PTY (e.g. `script`/pexpect) or use `hermes plugins validate --install-deps` (CI gate flag that installs declared deps non-interactively) — the latter exactly reproduces the "undeclared dependency" failure class that motivated this research.
- Desktop half: the custom-hermes-suite image already ships `xvfb` + GTK/GBM libs (Camoufox layer), so a headless Electron run is plausible in the same image family; Playwright `_electron.launch` + `xvfb-run` is the documented/community pattern. The packaged Desktop app on Peter's PC is not reachable from the cluster; a staging Desktop must be a Linux build launched inside the pod.
- Ranking (plan options, details §6): (1) ephemeral k8s Job "hermes-plugin-e2e" in its own namespace on wrk with emptyDir HERMES_HOME — best fit; (2) 0-replica staging Deployment per user idea — works, more moving parts; (3) NixOS VM test — strong isolation but needs KVM on a builder (bld) and Hermes packaged for Nix; (4) ephemeral container in the agent sandbox — NOT available today (no docker daemon, no /dev/kvm in the sandbox, verified).

## 1. Source-universe checklist

| Source type | Status |
|---|---|
| nixos-infra clusters/ (Flux, apps, platform, storage) | covered |
| nixos-infra hosts/ (wrk, cpl, llmb) | covered |
| nixos-infra modules/ | covered (iscsi-initiator only relevant module) |
| nixos-infra tests/ | covered (shell QEMU tests, no nixosTest/runNixOSTest) |
| custom-hermes-suite (Dockerfile, versions.env) | covered |
| DokuWiki KB (infra-topology, nixos-infra-naming) | covered |
| Hermes official docs (plugins page) | covered (read whole incl. middle via cache file) |
| Hermes GitHub issues | covered (#124784; #122134 referenced, not opened) |
| Flux docs (Kustomization suspend/annotations) | covered |
| KEDA HTTP add-on docs | covered |
| Kubernetes docs (Job TTL) | covered |
| k3s docs (storage) | covered |
| NixOS manual (test driver) | covered |
| Playwright Electron docs + homelab/CI write-ups | covered |
| Live cluster state (kubectl) | skipped — sandbox has no kubectl/SA token (by design) |

## 2. Findings — cluster ground truth (local repos, read-only)

F1. Live hermes-suite runs as a single-replica `Recreate` Deployment pinned to nodes labelled `role=apps` (= wrk). — V
Source: nixos-infra/clusters/cpl/apps/hermes-suite/deployment.yaml (local repo)
> `replicas: 1` / `strategy: type: Recreate` / `nodeSelector: role: apps`

F2. Both live volumes are static hostPath PV/PVCs with `storageClassName: ""` and nodeAffinity wrk; there is no dynamic storage class in use for Hermes. — V
Source: clusters/cpl/apps/hermes-suite/storage.yaml
> `hostPath: path: /mnt/iscsi/hermes-data type: Directory` … `storageClassName: ""` … `values: [wrk]`
Same pattern for cliproxyapi/firecrawl/loki (`grep storageClassName` across clusters/ — every hit is `""` or `"-"`).

F3. `/opt/data` is ext4 on an iSCSI zvol mounted by wrk itself; single-writer SQLite, two instances must never share it. — V
Source: clusters/cpl/apps/hermes-suite/deployment.yaml + README.md
> "SQLite state dir, two instances must never share /opt/data, and the pod must not poll Telegram next to the running probe instance."
Implication: staging needs its own HERMES_HOME; reusing the live PVC is excluded.

F4. `/workspace` is the shared NAS NFS export (writable for all uids via all_squash 3000) — a staging pod can mount it read-only to get the plugin checkout without copying. — V (mount facts) / P (read-only reuse for staging)
Source: storage.yaml
> "The EXISTING NAS workspace (A1) … 2775 uid 3000:100 (all_squash) — writable for everyone"
Note: a second PV object pointing at the same hostPath is needed (PV ↔ PVC is 1:1 and the live PVC is in ns hermes-suite); hostPath allows that. — P

F5. Flux reconciles the replica count; a `kubectl scale` alone is reverted; the repo documents PR or `flux suspend` + scale as the switch. — V
Source: clusters/cpl/apps/hermes-suite/README.md
> "Flux reconciles the replica count, so a plain `kubectl scale` is reverted on the next reconcile."

F6. Flux docs: a whole Kustomization can be paused with `.spec.suspend`, and a single object with the annotation `kustomize.toolkit.fluxcd.io/reconcile: disabled` (no apply, no prune). — V
Source: https://fluxcd.io/flux/components/kustomize/kustomizations/#suspending-and-resuming (official docs, read whole via cache file)
> "To pause the reconciliation of a specific Kubernetes resource managed by a Flux Kustomization, you can annotate or label the resource in-cluster with: kustomize.toolkit.fluxcd.io/reconcile: disabled … the controller will no longer apply changes, nor will it prune the resource."
Workaround vocabulary: omitting `replicas:` from the manifest is the usual GitOps trick so scale changes survive — P (general SSA field-ownership behavior; Flux `ssa: Merge` note: "works only for adding new fields that don't overlap with the desired state").

F7. All apps sit in ONE Flux Kustomization `apps` (path ./clusters/cpl/apps, prune: true, interval 10m); suspending it to scale staging would also freeze live hermes-suite, cliproxyapi, firecrawl. — V (structure) / P (side effect)
Source: clusters/cpl/apps.yaml + clusters/cpl/apps/kustomization.yaml
> `name: apps … path: ./clusters/cpl/apps … prune: true` ; resources: whoami, eso-probe, cliproxyapi, firecrawl, hermes-suite
Implication: a staging instance should get its OWN Flux Kustomization (e.g. `apps-staging`, `suspend: true` by default) or rely on the per-object annotation, never suspend `apps`.

F8. wrk is a k3s agent VM with only `--node-label=role=apps`; no GPU, no display stack, no taints configured; cpl is `role=utility`. — V
Source: hosts/wrk/configuration.nix, hosts/cpl/configuration.nix
> `extraFlags = [ "--node-label=role=apps" ];`

F9. The GPU host llmb is only an OS placeholder ("k3s+NVIDIA-Stack folgt der Phase-7-Karte"); no GPU node exists in the cluster today. — V
Source: hosts/llmb/configuration.nix
> "GPU-LLM-Host (Phase 7, OQ6: k3s-GPU-Agent). k3s+NVIDIA-Stack folgt der Phase-7-Karte; hier nur das OS-Grundgerüst."
Implication: a headless Electron must use software rendering (Mesa llvmpipe via `libgl1-mesa-dri` already in the image) — P.

F10. wrk is memory-constrained: live pod requests 2Gi / limit 6Gi with the comment "wrk has 6 GB until probe retires"; KB frame for wrk was 2 vCPU. — V (repo comment) / P (current exact RAM; stale KB value "1–2 GB" contradicts the 6 GB comment — newer repo value wins, KB nixos-infra-naming is stale)
Source: deployment.yaml; /workspace/knowledge/dokuwiki/data/pages/concepts/nixos-infra-naming.txt
> "memory requests 2Gi / limits 6Gi — wrk has 6 GB until probe retires"
Implication: a staging Hermes (gateway+dashboard+Electron+Xvfb, ~1.5–3 GB) next to live is tight; it can only run when scheduled after Phase-4c-Exit RAM move, or with tight limits, or on cpl (needs nodeSelector change; cpl has no Hermes PVs). — P

F11. Images come from Nexus `truenas.lan.fahsel.ch:8083/ascensionoid/custom-hermes-suite:<HERMES_SUITE_TAG>`, mirrored anonymously via wrk's registries.yaml — a staging pod can reuse the exact live tag with no pull secret. — V
Source: deployment.yaml + hosts/wrk/configuration.nix registries.yaml
> "no imagePullSecret needed" ; image `…custom-hermes-suite:0.22.2-s6-master-fwknop1`

F12. The image's ENTRYPOINT is s6-overlay; k8s `command:` must never be set (it replaced s6 in the failed 2026-10-15 cutover), only `args:`. — V
Source: clusters/cpl/apps/hermes-suite/README.md
> "k8s `command:` replaces the ENTRYPOINT … the dashboard s6-rc service (9119) never started … use `args:` (= CMD), never `command:`."
Implication for a Job: a test runner must either keep s6 (args = test script, gateway/dashboard as s6 services) or deliberately bypass s6 and start `hermes gateway run` itself — choose explicitly.

F13. The suite image already contains Xvfb, GTK3, GBM, X11 libs and fonts (installed for Camoufox). — V
Source: custom-hermes-suite/Dockerfile l.140–147
> `libgtk-3-0 … libx11-xcb1 … libegl1 libgl1-mesa-dri libgbm1 xvfb fonts-liberation fonts-noto-color-emoji`
Implication: the live image already has most Electron runtime deps; a test image only adds the Hermes Desktop Linux build + Node/Playwright (+ optional x11vnc/noVNC). — P

F14. Base image is `docker.io/nousresearch/hermes-agent:v0.22.2`; version pinned in versions.env; build via build-and-push.sh. — V
Source: Dockerfile l.37, versions.env (`AGENT_VERSION=v0.22.2`)

F15. Secrets: only dashboard Basic Auth comes from Infisical via ESO; the agent's own `.env` (Telegram token, API keys) lives on the data volume. — V
Source: clusters/cpl/apps/hermes-suite/externalsecret.yaml
> "NOT here on purpose: the agent's own /opt/data/.env (Telegram token, API keys, ...) is runtime state on the data volume"
Implication: a staging HERMES_HOME starts with no LLM key and no Telegram token — good for isolation (no long-poll clash), but LLM access must be provided: a new Infisical folder `/hermes-staging` + ExternalSecret, pointing at CPA (`cpa.homelab.fahsel.ch`, cliproxyapi httproute) or the local llama-swap. — P

F16. Ingress = Gateway API `internal` (Traefik) listener `*.homelab.fahsel.ch`, attachment allowed only for namespaces labelled `gateway.fahsel.ch/access: internal`; ExternalDNS publishes route hostnames. — V
Source: clusters/cpl/platform/gateway.yaml, hermes-suite/namespace.yaml + httproute.yaml
> namespace label `gateway.fahsel.ch/access: internal` ; listener `hostname: "*.homelab.fahsel.ch"`
Implication: a staging dashboard/noVNC route (e.g. `hermes-staging.homelab.fahsel.ch`) only needs a labelled namespace + HTTPRoute; no new DNS work. For a Job run, no route is needed at all (results go to logs/artifacts). — P

F17. nixos-infra tests/ are bash QEMU scripts (recovery-qemu.sh etc.), not NixOS `nixosTest`/`runNixOSTest` derivations; no test-driver tests exist in the repo. — V
Source: tests/*.sh (grep for nixosTest|runNixOSTest|testers: no hits); tests/recovery-qemu.sh header ("Boots the selfboot-ISO in a QEMU VM … SLIRP user-mode networking")

## 3. Findings — Hermes plugin install/consent/restart (official docs + issues)

F18. Hermes docs: Python dependency installation is a separate consent step; `--enable` does not bypass it; non-interactive installs leave the plugin installed but disabled; restart Hermes when a new environment is not yet active. — V
Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#dependency-preparation-and-preservation (official docs, read whole)
> "Python dependency installation has a separate consent/admission step. `plugins install --enable` does not bypass that step. A declined or non-interactive dependency install can leave the plugin installed but disabled. … Restart Hermes when a new selected environment is not yet active in the running process."

F19. Hermes docs: "Non-interactive sessions fail closed" for declared capabilities too. — V
Source: same page
> "installing or updating without a TTY completes the install, but declared capabilities are _not_ granted. Run `hermes plugins enable <id>` interactively to grant them later."

F20. Upstream issue #124784 (open, P3): the dependency-consent gate checks `sys.stdin.isatty() and sys.stdout.isatty()`; Desktop "Install from Git" can never install a plugin with Python deps; CLI on a real terminal works; #122134 covers the same gate in CI/SSH/pexpect contexts. Open PR #126497 linked. — V
Source: https://github.com/NousResearch/hermes-agent/issues/124784 (GitHub issue)
> "The dependency consent gate `_consent_python_deps` … checks `sys.stdin.isatty() and sys.stdout.isatty()` … The only workaround is the terminal (`hermes plugins install <url> --enable`, or `hermes plugins enable <name>`, answering `y`)."
Implication for staging automation: (a) wrap the CLI in a PTY (`script -qc "hermes plugins enable spawn-session" /dev/null` with `yes`, or pexpect answering y) — P (issue says pexpect is in #122134's scope, i.e. reported problematic; must be tested); (b) GUI install path cannot be e2e-tested for dep-bearing plugins until #126497 lands — V (per issue).

F21. Hermes CLI (v0.22.2 in this sandbox) has `hermes plugins validate --install-deps [--json]` ("exactly as `plugins install` would — the catalog CI gate") and `hermes plugins doctor --ci` ("Validate a plugin with the real runtime contracts"). — V (live CLI `--help`, sandbox install)
> "--install-deps  Install the plugin's declared Python dependencies (pyproject/python_dependencies) into this venv before the capability probe, exactly as `plugins install` would — the catalog CI gate"
Implication: this is the non-interactive path to catch the "undeclared dependency" failure — run it in a CLEAN venv/image (staging pod), never in the dev venv where the dep is already present. — P

F22. Plugins can be isolated per profile in a separate process (`plugins.isolation: host`) and the enabled set for dep preparation is the union over the default home and every profile. — V
Source: Hermes plugins docs (§ isolation, § dependency preparation)
> "The enabled set is the union over the default home **and every profile** under `profiles/`"
Implication: a "staging profile" inside the LIVE container is NOT isolated for dependencies — enabling the plugin there would change the live environment. Staging must be a separate HERMES_HOME + separate venv (separate container). — P (inference from the union rule)

F23. The plugin under test declares deps in pyproject `[project].dependencies` (takes precedence over plugin.yaml) and has tests/test_dependencies.py guarding host-provided modules. — V
Source: hermes-spawn-session/pyproject.toml header comment

## 4. Findings — scale-to-0 / ephemeral patterns (official docs)

F24. KEDA HTTP add-on (v0.16 latest) does HTTP scale-to-zero through an interceptor reverse proxy that holds requests during cold start; HTTPScaledObject is deprecated in favor of InterceptorRoute (with `coldStart`, `timeouts`). — V
Source: https://keda.sh/http-add-on/0.16/ and /reference/interceptorroute/ (official docs)
> "An interceptor that sits in front of your application as a reverse proxy, routing requests and tracking concurrency." ; "`HTTPScaledObject (Deprecated)`"
Fit: KEDA is not installed (no keda in clusters/, grep), Hermes cold start is slow (startupProbe up to 10 min), and test runs are batch, not HTTP-triggered — poor fit. — P

F25. Kubernetes Jobs support `ttlSecondsAfterFinished` for automatic cleanup of finished (Complete/Failed) Jobs. — V
Source: https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/ (official docs)
> "clean up finished Jobs (either `Complete` or `Failed`) automatically by specifying the `.spec.ttlSecondsAfterFinished` field"
Fit: "replicas=0 normally" is naturally a Job/CronJob that simply does not exist between runs; a suspended CronJob (`spec.suspend: true`) as template + `kubectl create job --from=cronjob/…` is the common trigger trick. — P (CronJob suspend/create-from is standard kubectl, not re-read this lane)

F26. k3s ships Rancher local-path-provisioner; PVs bind the pod permanently to the node, default path /var/lib/rancher/k3s/storage. — V
Source: https://docs.k3s.io/storage (official docs)
> "this does result in permanently binding the pod to the node hosting the volume"
Fit: unused by this fleet (all static hostPath); for an ephemeral run emptyDir is simpler than local-path. — P

## 5. Findings — headless Desktop / VM test driver

F27. Playwright supports Electron (experimental, v21+) via `_electron.launch`, with screenshot/click/evaluate; launch timeouts if the `nodeCliInspect` fuse is disabled. — V
Source: https://playwright.dev/docs/api/class-electron (official docs)
> "Ensure that `nodeCliInspect` (FuseV1Options.EnableNodeCliInspectArguments) fuse is **not** set to `false`."
Open: whether the packaged Hermes Desktop build keeps that fuse enabled — unknown (lane 2 owns). If disabled, fall back to a source/dev build with CDP 9222 (environment context says CDP exists only for dev-server builds). — S

F28. Community practice: Electron E2E in Docker = image with xvfb + libgbm1/libxss1/libnss3/libgtk-3 and an entrypoint that starts Xvfb before Playwright. — P (community blog, 2021)
Source: https://blog.dangl.me/archive/running-fully-automated-e2e-tests-in-electron-in-a-docker-container-with-playwright/
> "Its really just making sure that a virtual display is available before the actual command is run"
CircleCI blog (search snippet only, not read whole): "xvfb-run provides the display the app requires while your Playwright tests run." — P

F29. NixOS test driver: `pkgs.testers.runNixOSTest` works outside nixpkgs; machines expose `wait_for_x()`, `screenshot()`, `send_chars()`, OCR (`enableOCR`, `wait_for_text`), `virtualisation.memorySize`. — V
Source: https://nixos.org/manual/nixos/stable/#sec-nixos-tests (NixOS 26.05 manual, cache file l.17793–18186)
> "Outside the `nixpkgs` repository, you can use the `runNixOSTest` function from `pkgs.testers`" ; "screenshot(filename) Take a picture of the display of the virtual machine"
Fit: needs KVM on the builder (bld is the fleet builder) and Hermes + Desktop packaged for Nix, or podman inside the VM pulling the suite image — heavy. — P

F30. The agent sandbox cannot host an ephemeral container or VM today: docker CLI present but no daemon/socket, no /dev/kvm; Xvfb binary IS present; 4 CPUs / 13 GB visible. — V (live probe 2026-10-17)
> `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` ; `ls: cannot access '/dev/kvm'`
Implication: "ephemeral container in the agent sandbox" is out; but an in-sandbox "isolated HERMES_HOME + fresh venv + Xvfb" run is possible WITHOUT containers (weaker isolation: same OS, shared /opt/data volume — must use a scratch HERMES_HOME). — P

## 6. Plan options (no infra change made)

Option A — Ephemeral Job "hermes-plugin-e2e" (RECOMMENDED)
- Mechanism: new namespace `hermes-staging` (own Flux Kustomization `apps-staging`, or plain manifests applied by Peter); a suspended CronJob template using the live image tag (F11), emptyDir HERMES_HOME (F3/F22), `/workspace` read-only via a second hostPath PV (F4), LLM key from a new ESO secret (F15), nodeSelector role=apps, tight limits (F10), `ttlSecondsAfterFinished` (F25).
- Run script: `hermes plugins validate --install-deps --json` on the plugin dir (F21) → `hermes plugins install <path/git> ` + PTY-wrapped `hermes plugins enable` answering y (F20) → start gateway+dashboard (s6 via args, or direct — F12) → pytest live checks against plugin_api → `xvfb-run` + Playwright Electron against a Linux Desktop build pointed at localhost:9119 (F13/F27) → artifacts (JUnit, screenshots) to `/workspace/.../e2e-runs/<ts>/`.
- Trigger: Peter `kubectl create job --from=cronjob/hermes-plugin-e2e` (agent has no kubectl). Possible later: a scoped ServiceAccount that only may create Jobs in hermes-staging — needs Peter's decision.
- Confidence: storage/scheduling/image V; consent PTY trick S until tested; Electron in pod P.
- Trade-offs: no idle footprint, no Flux replica fights, fresh state each run (exactly catches undeclared deps). No interactive debugging unless noVNC added.

Option B — Staging Deployment replicas=0 (user's idea)
- Mechanism: copy of hermes-suite manifests as `hermes-staging` with own PV (new dir, e.g. `/mnt/iscsi/hermes-data/../staging` or new LUN), no Telegram token, Basic Auth secret, HTTPRoute `hermes-staging.homelab.fahsel.ch` (F16), optional noVNC sidecar (x11vnc+websockify) on the Xvfb display, `replicas` omitted or annotated `reconcile: disabled` so scaling sticks (F6), own Flux Kustomization (F7).
- Pros: Peter can watch/drive the GUI via noVNC; persistent state for multi-step debugging. Cons: state drift between runs (hides missing-dep bugs unless HERMES_HOME is wiped), RAM on wrk when up next to live (F10), more objects to keep in sync with live, Desktop still has to run inside the pod.
- Confidence: P overall.

Option C — NixOS VM test (`runNixOSTest`) on bld
- Strong isolation, screenshots/OCR built in (F29), but nothing exists in tests/ yet (F17), needs Hermes in the VM (podman + suite image) and KVM on bld. Highest effort; good for host-level regressions, overkill for plugin tests. — P

Option D — In-sandbox isolated run (no k8s)
- Scratch HERMES_HOME + fresh `uv venv` + `hermes plugins validate --install-deps` + Xvfb (present, F30). Cheap, agent can run it alone without Peter. Weak isolation (same process space/OS, must not touch /opt/data); no docker/KVM (F30). Good as the per-commit gate; A as the pre-release gate. — P

Option E — KEDA HTTP scale-to-zero — rejected: not installed, batch workload, 10-min cold start (F24).

Recommendation: D as the fast, agent-runnable gate (catches the undeclared-dependency class with `validate --install-deps` in a clean venv) + A for full backend+Desktop e2e on the cluster. B only if Peter wants a watchable GUI; then combine with A's wipe-on-start.

Untested on target: PTY consent workaround on v0.22.2; Hermes Desktop Linux build launch under Playwright (fuse); RAM headroom on wrk today; whether the suite image can run gateway without s6 in a Job.

## 7. Searched, found nothing (evidence of absence)

- `grep -rn keda clusters/` (local repo) — no KEDA installed.
- `grep -rn nixosTest|runNixOSTest|testers flake.nix tests/` — no NixOS test-driver tests.
- `grep -rn nvidia|gpu hosts/wrk hosts/cpl` — no GPU on cluster nodes (llmb placeholder only).
- `grep storageclass/local-path clusters/` — no dynamic StorageClass consumer; all `storageClassName: ""`.
- Hermes plugins docs: no `--yes`/`--accept-deps`/non-interactive consent flag found for `install`/`enable` (regex `--install-deps|--yes|--accept` matched nothing on the docs page; `--install-deps` exists only on `validate`, per CLI help).
- Hermes docs: no official "staging instance" or "plugin e2e in CI" guide found (web_search "Hermes Agent plugins dependency install consent ... docs" returned plugins/developer pages only).
- Existing staging namespace/manifests in nixos-infra: none.
