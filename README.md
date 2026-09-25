# Kuestion

Kuestion is a plugin-based AI chat application for scientists who want zero
configuration friction. Out of the box it gives you a chat window, a
bring-your-own-key model registry, and an AI harness that streams answers back
into the window — each one a plugin, and every one replaceable-in-principle
through the same typed event contract.

Plugins talk to each other **only** through typed events on a kernel event bus.
A broken plugin is flagged and explained in the UI; it never crashes the app.

## Requirements

- [uv](https://docs.astral.sh/uv/) (manages Python 3.14 and dependencies)
- A desktop environment with Qt 6 support (Linux, Windows, or macOS)

## Install and run

```sh
uv sync          # create the environment
uv run kuestion  # launch the app
```

To validate and load every plugin without entering the event loop (handy on a
headless machine or in CI):

```sh
uv run kuestion --check
```

The app prints one line per loaded plugin and one per failure when it starts.

## Your first conversation

1. Open **Settings → Models…**.
2. Fill in an entry and click **Save entry**:
   - **Name** — the label shown in the chat model picker.
   - **Base URL** — an OpenAI-compatible endpoint, e.g.
     `https://api.openai.com/v1`.
   - **Model id** — the provider's model name, e.g. `gpt-4o-mini`.
   - **API key** — your key.
   - **Headers** — optional extra HTTP headers.
3. Pick the entry in the model combo box above the chat input.
4. Type a message and press **Send**. The reply streams into the log, rendered as
   Markdown with LaTeX math. Inline math may use `$…$` or `\(…\)`, display math
   `$$…$$` or `\[…\]`; formulas are typeset by KaTeX in an embedded web view
   (fully offline — the assets are vendored, no browser engine download at
   runtime). Code blocks get a **Copy** button, and the log's colors come from
   the application's Qt palette, so it matches the rest of the UI in both light
   and dark themes.
5. To attach a file, include its path in the message text (e.g.
   `summarize /home/me/notes.txt`). Text files are read and included
   automatically.

Model entries — **including the API key, in plaintext** — are stored in
`~/.config/kuestion/models.json` with file mode `0600`.

## Plugins

The built-in plugins are `windowing` (the Qt shell, dockable panels and menus),
`keyregistry` (configured endpoints and request execution), `harness`
(conversation state and model brokering), and `chat` (the chat window).

**Adding a plugin is dropping a directory in place.** Kuestion discovers plugins
in two directories:

- `plugins/` — the built-ins shipped with the repository.
- `~/.config/kuestion/plugins/` — your own and third-party plugins. A plugin
  here overrides a built-in with the same directory name.

Both directories merge into a single import namespace: a plugin directory named
`my_plugin` imports as `plugins.my_plugin`, so the only name added to Python's
import path is `plugins` — your plugin never shadows an installed package.
Cross-plugin types are imported as e.g. `from plugins.keyregistry.events import
ModelRequest`.

Open **View → Plugins…** to see every plugin's status, read any load or handler
error (with traceback) one click away, and toggle plugins on and off. Disabling
a plugin also unloads the plugins that depend on it.

See **[docs/PLUGINS.md](docs/PLUGINS.md)** for the plugin author guide, and
[`examples/plugins/trim_history/`](examples/plugins/trim_history/) for a small working
example: a middleware plugin that trims conversation history before it reaches
the model.

## Development

```sh
uv run pytest
```

Tests are co-located with the code they cover (`kernel/tests/`,
`plugins/<name>/tests/`, `examples/plugins/<name>/tests/`).

## Trust model

Third-party plugins run with the full privileges of the application. There is
no sandbox in this version — only install plugins you trust.
