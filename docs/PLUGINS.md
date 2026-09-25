# Kuestion Plugin Author Guide

Everything in Kuestion is a plugin: the chat window, the AI harness, the key
registry, even the Qt windowing shell. This guide covers how to write one.

The kernel is deliberately small and fixed — it provides only a **loader**, a
**type registry**, an **active-plugin tracker**, and a **threadsafe async event
bus**. Plugins never call each other directly; they communicate exclusively by
sending typed events. The only things one plugin imports from another are its
**event types** and its **plugin id**.

---

## 1. Discovery and layout

Kuestion scans two directories for plugins:

| Directory | Purpose |
| --- | --- |
| `plugins/` (repository root) | built-in plugins |
| `~/.config/kuestion/plugins/` | your and third-party plugins |

A plugin is a **directory** containing (at minimum) `manifest.py` and
`plugin.py`. Both search directories become **portions of a single implicit
namespace package named `plugins`**, so a plugin directory named `my_plugin`
imports as `plugins.my_plugin`; the only name added to Python's import path is
`plugins`. Concretely, built-in and user plugins merge:

- `plugins/keyregistry/` → `plugins.keyregistry`
- `~/.config/kuestion/plugins/my_plugin/` → `plugins.my_plugin`

The manifest `id` (`kuestion.keyregistry`) is the logical bus identity and is
deliberately **not** the module path. Later directories win when two plugins
share a directory name (a user plugin overrides a built-in of the same name),
both on disk and when Python resolves `plugins.<name>`.

```
~/.config/kuestion/plugins/
└── my_plugin/
    ├── __init__.py
    ├── manifest.py      # contract surface: the MANIFEST constant
    ├── events.py        # event types this plugin declares (optional)
    ├── plugin.py        # the entry module holding your Plugin subclass
    ├── src/             # implementation modules (imported after validation)
    │   ├── __init__.py
    │   └── logic.py
    └── tests/           # unit tests for your plugin
        └── __init__.py
```

`manifest.py` and `events.py` form the **contract surface**. The loader imports
them during validation, before any implementation code runs. Keep them free of
side effects and of imports from `src/` and `plugin.py`.

---

## 2. The manifest

`manifest.py` exposes a `MANIFEST` constant built from the
`kernel.manifest.Manifest` dataclass:

```python
from kernel.manifest import Consume, Manifest, ReEmit
from plugins.my_plugin.events import Ping, Pong

MANIFEST = Manifest(
    id="myorg.my_plugin",              # dotted lower_snake identifier
    entry="plugin:MyPlugin",           # "module:ClassName" under this package
    emits=(Ping,),                     # event types this plugin declares
    consumes=(Consume(event_type=Pong),),
    reemits=(ReEmit(event_type=Ping, target_id="other.plugin", priority=50),),
    requires=("kuestion.windowing",),  # plugin ids that must load first
    pip_deps=("httpx",),               # importable pip packages this needs
    main_thread=False,                 # run handlers on the Qt main thread
)
```

| Field | Meaning |
| --- | --- |
| `id` | Globally unique plugin id; used as `sender_id`/`target_id` on the bus. |
| `entry` | `module:ClassName` (relative to the plugin package) to instantiate. |
| `emits` | Event types **declared** by this plugin (they register in the type registry). |
| `consumes` | `Consume` entries for every `@consume`-decorated handler. |
| `reemits` | `ReEmit` entries for every `@reemit`-decorated handler. |
| `requires` | Plugin ids this plugin depends on; determines load order. |
| `pip_deps` | Third-party packages that must be importable, checked before load. |
| `main_thread` | If `True`, the plugin's handlers run on the main/Qt thread. |

`Consume(event_type=...)` and `ReEmit(event_type=..., target_id=None,
priority=100)` describe subscriptions. `ReEmit.target_id=None` means "all
consumers of the type"; a plugin id scopes the middleware to that recipient.

> **Reserved:** `Consume.directed_only` is accepted by validation but currently
> has no effect; use a directed subscription guarded by `target_id` checks for
> now.

### Declaring vs. importing event types

Event types have a single owner. If your plugin needs a type another plugin
already declares, **import it** from that plugin's `events.py` — never
redeclare it. Redeclaring a type raises a duplicate-type load failure:

```python
# good: reuse the owner's type (note the ``plugins.`` namespace)
from plugins.keyregistry.events import ModelRequest
```

Validation imports `manifest.py` and `events.py` only. A plugin's own declared
types are registered in order; imported types are skipped (the owner registered
them). A type declared by two plugins fails the second one.

---

## 3. The event envelope

Every message on the bus is an `Event`:

```python
@dataclass(frozen=True)
class Event:
    event_type: type            # the payload class, e.g. ModelRequest
    payload: object             # an instance of event_type
    sender_id: str              # the emitting plugin's id
    target_id: str | None       # None = broadcast; otherwise directed
    correlation_id: str | None  # ties a response to its request
    timestamp: float
```

- **Broadcast** events (`target_id is None`) go to every plugin whose
  subscription matches the event type (or a superclass).
- **Directed** events go to exactly one plugin. An unknown target is
  dead-lettered as a `PluginHandlerError`.
- Responses are just directed emits back at `event.sender_id`. Use
  `kernel.envelope.reply_to(event, payload, sender_id=...)` to reuse the
  correlation id.

Always construct events through the bus:

```python
self.bus.emit(Event(
    event_type=Ping,
    payload=Ping("hi"),
    sender_id=self.manifest.id,
    target_id="other.plugin",
    correlation_id=correlation,
))
```

---

## 4. The `Plugin` base class

```python
from kernel.plugin import Plugin, consume, reemit

class MyPlugin(Plugin):
    def on_load(self) -> None: ...

    def on_unload(self) -> None: ...

    @consume(Ping)
    def _on_ping(self, event) -> None:
        ...
```

- `manifest` and `bus` are injected by the loader after construction; do not set
  them in `__init__`.
- `on_load` runs after the plugin is registered with the bus; `on_unload` runs
  before it is unregistered. Use them to acquire/release resources (threads,
  observer taps, UI).
- Handlers receive the whole `Event`, so they can read `sender_id`,
  `target_id`, and `correlation_id`.

### Subscription kinds

| Kind | Decorator | Behavior |
| --- | --- | --- |
| **Consume** | `@consume(Type)` | Handle a matching event. Errors are reported, never fatal. |
| **Re-emit** (middleware) | `@reemit(Type, target_id=None, priority=100)` | Transform an event before delivery and return the replacement payload. |

A re-emit handler **must return the same event type (or a subclass)**, or
`None` to skip this recipient. Returning a different type, raising, or
returning nothing from a consumer is reported as a `PluginHandlerError`.

### Middleware semantics

- Middleware is **per-consumer**: the bus does not transform an event once — each
  consumer receives its own delivery, passed through only the middleware scoped
  to it (global-for-type + target-specific). A middleware scoped to plugin X
  never affects plugin Y.
- Ordering within a chain is by **priority** (lower runs first), then
  registration order.
- Chains run **before** the recipient's consume handlers, on the event thread.
- Since each plugin gets its own bus thread, a slow handler in one plugin cannot
  stall another.

---

## 5. Threading rules

- `emit()` is safe from any thread and never blocks the emitter.
- A plugin with `main_thread=False` (the default) owns a dedicated handler
  thread; its handlers run there, never on the event thread.
- A plugin with `main_thread=True` has its handlers scheduled onto the Qt main
  thread via the windowing bridge. **Qt widgets may only be constructed or
  touched on the main thread.**
- Blocking work (network, disk) must not run on the bus or the main thread.
  Spawn a worker thread and re-emit the result — see how `keyregistry` serves
  `ModelRequest` on a worker.
- Payloads crossing the bus must be **thread-safe data**. A widget you want to
  display is described with a `WidgetSpec` (see below), not sent directly.

---

## 6. Displaying UI through the windowing plugin

Never import `windowing`'s implementation. Import its **event types** and ask
the windowing plugin to show your UI. Pass a `WidgetSpec` describing how to
build it on the main thread — either a declarative `spec` dict or a `factory`
callable:

```python
from plugins.windowing.events import DialogRequested, PanelRequested, WidgetSpec

self.bus.emit(Event(
    event_type=PanelRequested,
    payload=PanelRequested(
        panel_id="my-panel",
        title="My Panel",
        widget_spec=WidgetSpec(factory=self._make_widget),  # called on the main thread
        area="right",     # "left" | "right" | "top" | "bottom"
        center=False,     # True makes it the central workspace widget
    ),
    sender_id=self.manifest.id,
))
```

| Event | Effect |
| --- | --- |
| `PanelRequested` | Open a dockable panel (or the centered workspace widget). |
| `DialogRequested` | Register a menu item that opens a non-modal dialog. |
| `PopupRequested` | Show a widget in its own top-level window. |
| `MenuRequested` | Register a plain menu action. |
| `MenuItemActivated` | Emitted by windowing when a registered action fires. |
| `ClosePanelRequested` | Close a panel by id. |

A `WidgetSpec` with `factory` must be a zero-argument callable returning a
`QWidget`; it is invoked on the main thread at delivery. A `WidgetSpec` with
`spec` is a recursive dict using the built-in kinds `label`, `button`,
`lineedit`, `vbox`, and `hbox`.

`DialogRequested` needs a `menu_path` (slash-separated, e.g. `"Settings/Models…"`
or `"View/Event Log…"`), an `action_id`, a `title`, and the `widget_spec`.

---

## 7. Lifecycle, failures, and toggling

- **Validation happens before any implementation runs.** A `manifest.py` that
  fails to import, a malformed manifest, a missing requirement, a type
  duplicate, or a missing pip dependency all produce a `plugin.load_failed`
  event — the app still boots.
- **Handler and middleware exceptions** are caught by the bus and published as
  `plugin.handler_error` (plugin id, event type, traceback). The event is
  considered consumed; other plugins keep working.
- **Hot enable/disable:** the `View → Plugins…` dialog toggles a plugin (and its
  dependents). Disabling calls `on_unload`, drops subscriptions, and unregisters
  the handler thread; re-enabling constructs a fresh instance and calls
  `on_load`. Python modules stay in `sys.modules`, so imported event types remain
  alive — stale state is the plugin's responsibility to clear in `on_unload`.
- **`pip_deps` are not auto-installed.** A missing package is reported with an
  install hint.

---

## 8. Worked example: a middleware plugin

[`examples/plugins/trim_history/`](../examples/plugins/trim_history/) trims the
conversation history in every `ModelRequest` before it reaches the model,
without disturbing the chat window's own view.

`manifest.py` — imports the type it re-emits from its owner (`keyregistry`):

```python
from kernel.manifest import Manifest, ReEmit
from plugins.keyregistry.events import ModelRequest

TARGET_ID = "kuestion.keyregistry"
PRIORITY = 10

MANIFEST = Manifest(
    id="kuestion.example.trim_history",
    entry="plugin:TrimHistoryPlugin",
    reemits=(ReEmit(event_type=ModelRequest, target_id=TARGET_ID, priority=PRIORITY),),
    requires=(TARGET_ID,),
)
```

`plugin.py` — one middleware method:

```python
class TrimHistoryPlugin(Plugin):
    @reemit(ModelRequest, target_id=TARGET_ID, priority=PRIORITY)
    def trim(self, event):
        request = event.payload
        return replace(request, messages=trim_history(request.messages))
```

Because the re-emit is **scoped to `kuestion.keyregistry`**, the middleware
never touches any other `ModelRequest` delivery. (The chat window does not
consume `ModelRequest` anyway, but the scoping is what makes the intent
explicit and safe.) To try it, copy the directory into your user plugin folder:

```sh
cp -r examples/plugins/trim_history ~/.config/kuestion/plugins/
uv run kuestion --check   # confirms it loads
```

---

## 9. Testing your plugin

- Keep logic in Qt-free, bus-free modules under `src/` and unit-test them
  directly.
- Test handlers by writing a tiny fake bus that records emitted events (see
  `plugins/harness/tests/test_plugin.py`).
- For bus behavior (ordering, scoping, priority), use the real `EventBus` with
  fake plugins, mirroring `kernel/tests/test_bus.py`.
- Do not unit-test UI rendering; smoke-test widgets off-screen instead.

Run the whole suite with `uv run pytest`.

---

## 10. Trust and compatibility notes

- Third-party plugins execute with the full privileges of the application; there
  is no sandbox.
- The kernel's contract surface (`kernel.envelope`, `kernel.events`,
  `kernel.manifest`, `kernel.plugin`) is the stable API. Plugin internals
  (`src/`) are private.
- The built-in chat log renders Markdown and LaTeX in an embedded
  `QWebEngineView` (Chromium, shipped with `pyside6-addons`). It runs a local
  shell page only — vendored KaTeX assets, remote URL access disabled, no
  network, and no model-provided JavaScript (`markdown.py` parses with raw HTML
  disabled).
