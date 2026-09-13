# KUESTION_PLAN.md

## Overview / Goal

**kuestion** is a Qt (KDE) desktop AI agent built on the principle that **everything is a plugin**.
The kernel is deliberately tiny: a **plugin loader** and an **event bus** — nothing else. There is
no service registry: *every* action in the system, including loader/restart operations, travels
through the bus as a keyed event, so every plugin can observe everything and any component can be
replaced without others noticing.

**Done means:** a working agent chat — launch `main.py`, get a Qt window; UI to manage extensions
(enable/disable/restart plugins at runtime); a chat box with a markdown-rendered transcript streaming
token-by-token from any OpenAI-compatible endpoint with a user-supplied URL + API key (BYOK); file
attachments become context entries.

## Background / Current State

The repo `/home/yoerivanzwol/dev/kuestion` was emptied on request; only `LICENSE` (MIT) and git
history remain. Environment facts:

- Python 3.14.7, pip 26.0.1, no `uv`
- PySide6 6.11.2 already installed system-wide (PyQt6 is not; PySide6 is chosen)
- User runs KDE; a Qt app is native there
- Nothing else exists yet — this plan is the starting point

## Decisions and Rationale

| Decision | Choice | Rationale (why, and what was rejected) |
|---|---|---|
| Qt binding | **PySide6 6.11** | Already installed, official Qt for Python, LGPL. PyQt6 rejected: GPL/commercial, not installed. |
| Plugin distribution | **Filesystem folders** (`plugins/<name>/` with `plugin.json` + `plugin.py`), loaded via `importlib` | Matches drop-in / restart-from-UI workflow. Entry-point packages (pip-installable plugins) rejected for v1 — can be added later without changing the contract. |
| Service registry | **Eliminated entirely** | A registry lets plugins bypass the bus, making actions closed and unobservable — incompatible with "everything is a plugin". All former service calls become keyed events. |
| Event bus | Pure-Python, synchronous, in-order per subscriber, wildcard keys (`llm.*`) | The bus is dumb: `{key, payload, source, id, ts}` events; no persistence, no guaranteed delivery. Subscriber exceptions are logged and isolated — never kill the bus or other subscribers. |
| Event field name | payload field uses **`key`** (not `topic`) | User decision. |
| Threading | Plugins load and handle events on the Qt main thread; a plugin doing blocking work (harness + BYOK) owns its own `QThread` and posts results back as bus events | Simplest correct model; the bus itself stays single-threaded. All-tools-threaded plugins rejected as needless complexity. |
| Harness ↔ chat layering | Chat decomposes message + files into context entries, emits `context.append` ×n then `context.send`. The **harness** subscribes to those, keeps internal context state, and on send spawns its worker thread. It emits `llm.delta` / `llm.done` / `llm.error`. The harness **never depends on chat** | User correction: earlier design had the harness reading files and registering a service, inverting the dependency. Chat reads files itself; the harness only ever sees ready-made context entries, so it can be driven headlessly by a test plugin. |
| BYOK transport | Dumb HTTP pipe: consumes `llm.request`, POSTs with `stream: true`, parses SSE, emits `llm.delta` / `llm.done` | BYOK holds no conversation state; the harness is the sole emitter of chat-visible `llm.*` events, so the transport swaps in invisibly (local model endpoint later). `stream: false` responses are wrapped as one delta + done. |
| Credentials | JSON at `~/.config/kuestion/byok.json`, mode 0600 | Zero dependencies, easy to inspect. Qt `QSettings` and OS keyring rejected for v1 (later swap). Keys never committed. |
| Streaming | Token-by-token SSE | The difference between "feels like an agent" and "feels like a form" for long answers. |
| Markdown view | `QTextBrowser.setMarkdown()` | `QWebView` was removed in Qt6. `QWebEngineView` (bundles Chromium) rejected for v1 as heavyweight; the renderer sits behind a small interface so it can be swapped later. |
| Restart semantics | Restart = unload + reload. Unload: emit `plugin.unloaded`, call `on_unload()`, revoke all of the plugin's subscriptions, destroy windows it opened, delete its module from `sys.modules`. Reload: fresh import + `on_load()` | Cleanup is guaranteed because the loader tracks everything created through the plugin's `context` — not trust-based. A restart whose reload throws leaves the plugin unloaded; the failure surfaces as `plugin.load_failed`. |
| Bootstrap | Root `main.py` boots the kernel, reads `config.json` (enabled plugin list); **windowing always loads first**; UI changes persist to `config.json` | Windowing is the shell; everything else is user-controlled. |
| App name / layout | Keep **kuestion**. Flat from root: `kernel/`, `kernel/tests/`, `plugins/<name>/`, `plugins/<name>/tests/`, `main.py`, `pyproject.toml`, `config.json`, `scripts/` | User preference — no `src/`, plugin code+tests live together per plugin. |
| Tooling | venv + `pip install -e .`; pytest + pytest-qt | Boring and reliable. |
| Workflow | TDD per the tdd skill: stubs/mocks → tests → RED → review (testreviewer) → GREEN → verify | Every phase below states its test coverage first. |

## The Full Design Tree

```
kuestion
├── Kernel (kernel/ — always the first thing loaded; includes tests in kernel/tests/)
│   ├── Event bus   (kernel/bus.py + kernel/events.py)
│   │   ├── Event shape: {key: str, payload: dict, source: str, id: str, ts: float}
│   │   ├── Delivery: synchronous, in-order per subscriber, on the main thread
│   │   ├── Wildcard keys ("llm.*")
│   │   └── Isolation: subscriber exception → logged, other subscribers unaffected;
│   │       invalid key/payload → logged, no crash
│   └── Plugin loader (kernel/loader.py + kernel/context.py + kernel/manifest.py)
│       ├── Discovery: scan plugin dirs for plugin.json manifests
│       │   └── Manifest: {id, name, version, entrypoint, dependencies[],
│       │       emits[], consumes[]}
│       ├── Event interface lives in the manifest: each plugin declares the
│       │   event keys it emits and consumes. The loader checks against the
│       │   declarations: warns on undeclared emit/subscribe, and warns when a
│       │   consumed key matches no loaded plugin's emits (likely missing dep).
│       │   The windowing extension manager shows this interface so plugins
│       │   are self-documenting.
│       ├── Contract: entrypoint exposes a class with on_load(context) / on_unload()
│       ├── Context object = the ONLY outside door a plugin gets:
│       │   emit(key, payload) · subscribe(key, handler) · log · auto-tracked resources
│       ├── Lifecycle: load · unload · restart; result announced as bus meta-events:
│       │   plugin.loaded · plugin.unloaded · plugin.load_failed
│       ├── Restart arrives as a bus event (window.restart_plugin) — the loader itself
│       │   is event-driven, keeping the meta-loop observable
│       ├── Guaranteed cleanup: loader tracks subscriptions + windows created via context
│       ├── Duplicate plugin id rejected; missing dependency surfaced, not silently ignored
│       └── Order: config.json lists plugins; they load in listed order
├── Core plugins (plugins/<name>/ with tests/ beside the code)
│   ├── windowing — ALWAYS loaded first; owns the shell
│   │   ├── Main window that hosts other plugins' widgets
│   │   ├── Extension manager: list plugins (from bus meta-events) with their
│   │   │   declared event interfaces (emits/consumes), enable/disable,
│   │   │   restart (emit window.restart_plugin), persist config.json
│   │   └── emits: window.restart_plugin · consumes: plugin.*
│   ├── chat — the desktop chat window
│   │   ├── QTextBrowser markdown transcript + chat box + file-attach button
│   │   ├── On submit: decompose message + files → context.append ×n → context.send
│   │   ├── File attach: reads text/code files itself (harness never sees file IO),
│   │   │   non-text files rejected with an inline error entry
│   │   ├── emits: context.append, context.send · consumes: llm.delta, llm.done, llm.error
│   │   └── Renders llm.delta incrementally; llm.error surfaces in the transcript
│   ├── harness — pure-code AI orchestrator, zero UI, zero Qt widget code
│   │   ├── Internal context state; subscribes context.append / context.send
│   │   ├── On send: context → messages[] → emits llm.request → worker QThread
│   │   └── emits: llm.request, llm.delta, llm.done, llm.error (sole emitter of
│   │       chat-visible llm.*) · consumes: context.append, context.send
│   └── byok — dumb HTTP pipe, no state, "bring your own key"
│       ├── consumes: llm.request · emits: llm.delta, llm.done, llm.error
│       ├── POSTs chat/completions to a user-configured OpenAI-compatible URL with
│       │   the key from ~/.config/kuestion/byok.json
│       ├── SSE streaming → llm.delta per received delta; [DONE] → llm.done;
│       │   HTTP/network errors and malformed SSE → llm.error
│       └── OpenAI-compatible chat-completions only in v1
├── Event metadata (the only kernel-emitted events, declared by the loader)
│   ├── plugin.loaded / plugin.unloaded / plugin.load_failed {id, error?}
│   └── wildcard "plugin.*" matchable by any observer
├── Event payload shapes: documented and tested by each emitting plugin
│   └── The kernel checks keys, not payloads; the emitting plugin owns and
│       documents its payload shapes (e.g. chat documents context.append,
│       harness documents llm.request).
├── Bootstrap & config
│   ├── main.py: create bus → create loader → load windowing → load enabled plugins
│   │   per config.json, in listed order
│   └── config.json: {"enabled": ["windowing", ...]} — edited by the windowing UI
└── Testing: pytest + pytest-qt; QT_QPA_PLATFORM=offscreen in conftest
```

Dependency arrows (all event-mediated, zero direct plugin-to-plugin imports):

```
windowing ──window.* events──▶ loader(kernel)          boot-time only
chat ──ctx.append/ctx.send──▶ harness ──llm.request──▶ byok
chat ◀──llm.delta/done/error── harness ◀── http/SSE ── byok (all over the bus)
Replace chat with a headless emitter → the harness must not notice. (test asserted)
```

## Phase-Based Implementation Plan

Workflow every phase: scaffold stubs → write tests → commit RED → testreviewer review →
implement → GREEN → full suite. No skipping steps; no skipped tests.

### Phase 1 — Self-contained project scaffold
- `pyproject.toml`: name `kuestion`, dependency `PySide6`, dev deps `pytest`, `pytest-qt`;
  pytest config in pyproject.
- `main.py`, empty `main.py` tree, `config.json` placeholder, `README.md` stub.
- `.venv` + `pip install -e .`; `.gitignore` covers `.venv/`, `__pycache__/`, `*.egg-info/`,
  `.pytest_cache/`, `config.json` (user-local; defaults live in `configs/defaults.json`,
  committed).

### Phase 2 — Event bus (`kernel/bus.py`, `kernel/events.py`) — no Qt dependency
- Tests (`kernel/tests/test_bus.py`): subscribe/emit happy path; wildcard matching
  (`llm.*`, literal key beats wildcard); synchronous in-order delivery; subscriber
  exception isolation (later subscribers still receive the event; error logged); event
  payload validation (key must be str, payload dict); `source`, `id`, `ts` populated;
  unsubscribe works.
- Implement `EventBus` + `Event` dataclass until green.

### Phase 3 — Loader + context (`kernel/loader.py`, `kernel/context.py`, `kernel/manifest.py`)
- Tests (`kernel/tests/test_loader.py`, `test_context.py`, `test_manifest.py`):
  - Manifest: parse + validate required fields incl. `emits` / `consumes` event
    lists; bad manifest → descriptive error
  - Discovery: scans configured plugin dirs, ignores dirs without manifest
  - Load: in listed order, calls `on_load(context)`, emits `plugin.loaded`;
    duplicate id rejected; missing dependency → error (not silently skipped)
  - Event interface enforcement (bus keys, not payloads): emit of a key not in
    the plugin's `emits` → still delivered (bus stays dumb) but warning logged;
    subscribe to a key not in `consumes` → warning logged; consumed key matched
    by no loaded plugin's emits → inter-plugin warning
  - Unload: subscriptions revoked (emit after unload goes nowhere), `on_unload()`
    called, plugin-opened windows destroyed (tracked via context), module removed
    from `sys.modules`, partial-unload of a plugin without windows must not crash
  - Restart: unload + fresh import (new module object); reload raising an exception
    → plugin stays unloaded, `plugin.load_failed` carries the error
  - Restart requested via `window.restart_plugin` bus event (meta-loop is event-driven)
- Write root `AGENTS.md`: the plugin-authoring contract, concise and
  token-light without losing detail. Sections: kernel architecture in ~5
  bullet lines; `plugin.json` schema (incl. emits/consumes) + minimal
  manifest example; plugin class contract (`on_load(context)`/`on_unload()`);
  context API one-liner each (`emit`, `subscribe`, `log`, auto-tracked
  resources); rules (never block the main thread, no blocking handlers, no
  plugin-to-plugin imports, communicate only via bus events, cleanup via
  context tracking); event naming convention (`<domain>.<action>`, wildcards);
  testing conventions (pytest(-qt), `tests/` beside code, offscreen env).
- Implement until green.

### Phase 4 — Windowing plugin (`plugins/windowing/`) — first Qt code
- Tests (`plugins/windowing/tests/`, pytest-qt, offscreen):
  - Main window opens; extension manager lists loaded plugins (fed by bus meta-events)
  - Enable/disable + restart buttons emit the right `window.*` / reload events and
    persist to `config.json`
  - Unload destroys the window cleanly
- Implement manifest + `plugin.py` (main window, extension-manager dock/panel, config write).

### Phase 5 — BYOK plugin (`plugins/byok/`)
- Tests (`plugins/byok/tests/`) — pure/non-Qt where possible, no network:
  - Config: valid file parses; missing file → config-validation error event, no crash;
    wrong permissions flagged; malformed JSON → error
  - SSE parsing: recorded transcripts used as fixtures; each SSE delta → one `llm.delta`;
    `data: [DONE]` → `llm.done`; HTTP error + malformed SSE → `llm.error`;
    `stream: false` replayed as one delta + done
- Implement manifest, config loader, SSE/NY HTTP client on a `QThread`
  (requests or httpx, whichever stays dependency-light against PySide6; decide at
  implementation time, stdlib `http.client` also viable).

### Phase 6 — AI harness plugin (`plugins/harness/`) — pure code, no Qt
- Tests (`plugins/harness/tests/`):
  - `context.append` accumulation → correct `llm.request` `messages[]` structure
  - `context.send` triggers a request (file entries inlined as text blocks)
  - Deltas/done/error relayed onto the bus as `llm.*` with matching `request_id`
  - In-flight guard: second `context.send` mid-request → rejected with warning event,
    request stays intact
  - Harness runs handlers on the main thread but generation on its own thread
    (assert by construction, no Qt widget imports in the module)

### Phase 7 — Chat plugin (`plugins/chat/`)
- Tests (`plugins/chat/tests/`, pytest-qt):
  - Submit → n × `context.append` then `context.send`
  - Attach: file entries with kind `file`, content read by chat; non-text rejected inline
  - Transcript renders markdown; streaming deltas append incrementally
  - `llm.error` shown in the transcript (never silent)
- Implement manifest + chat window + submit flow.

### Phase 8 — Wire-up and end-to-end
1. `main.py`: create bus → loader → load windowing → enabled plugins in listed order;
   graceful shutdown (unload all on exit).
2. Repo-wide suite green; `scripts/verify.py` smoke check that the full plugin set
   loads and unloads cleanly against a temp config.
3. Manual verification on KDE (`python main.py`):
   - Extension manager shows the four plugins and their declared event interfaces;
    restart of `chat` reloads it live
   - Mock OpenAI endpoint (local lightweight stub) streams into the transcript
   - Attach a text file → appears in the request context; bad key → error in transcript
4. `README.md`: architecture overview, plugin contract (manifest including
   emits/consumes), event flow diagram. There is deliberately no central event
   vocabulary file — the per-plugin manifests are the source of truth.

## Verification

- `pytest` from repo root: all green, no skips; full coverage of kernel parts; per-plugin
  coverage of load/unload/event flows.
- `QT_QPA_PLATFORM=offscreen conftest.py` so tests run on a headless CI box.
- `python main.py` on KDE: single window; extension manager lists plugins; restart of any
  core plugin (e.g. window reload) works live; disable persists across an app restart.
- BYOK smoke: local mock OpenAI endpoint (or recorded SSE); keys live only in
  `~/.config/kuestion/`.

## Non-Goals / Risks

- **Non-goals (v1):** persistence (a future plugin can consume `context.append` events),
  pip-installable plugin packages, system prompts / model options / tool calling beyond
  plain chat completions, markdown themes beyond QTextBrowser defaults, `QWebEngineView`
  upgrade, keyring-protected credentials, non-Linux/KDE support
- **Threading ban** (bus): no subscriber may block; the harness and BYOK run generation/HTTP
  on their own threads. Violation manifests as a frozen UI — asserted in docs and reviews.
- **Declared event keys are the contract** between plugins (payload shapes are owned
  and documented by the emitting plugin): changing a manifest's `emits`/`consumes`
  requires updating that plugin's tests and docs — the loader only cross-warns on
  mismatches, it cannot enforce payloads.
- **Python 3.14 + PySide6 6.11** are current and installed; importlib restart edge cases
  are mitigated by the loader removing modules on unload + keeping the kernel
  import-stable.
- **BYOK key handling:** `.config/kuestion/byok.json` is 0600 user-private; keys must never
  be logged via the bus (payloads of `llm.request` must contain the URL, not the key).
