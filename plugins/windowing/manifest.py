"""Contract surface for the ``windowing`` plugin.

Only this module and :mod:`windowing.events` are imported during validation;
``plugin.py`` is imported later, in dependency order.
"""

from kernel.events import (
    PluginHandlerError,
    PluginLoadFailed,
    PluginLoaded,
    PluginUnloaded,
)
from kernel.manifest import Consume, Manifest

from plugins.windowing.events import (
    ClosePanelRequested,
    DialogRequested,
    MenuItemActivated,
    MenuRequested,
    PanelRequested,
    PopupRequested,
)

MANIFEST = Manifest(
    id="kuestion.windowing",
    entry="plugin:WindowingPlugin",
    emits=(
        PanelRequested,
        PopupRequested,
        MenuRequested,
        MenuItemActivated,
        ClosePanelRequested,
        DialogRequested,
    ),
    consumes=(
        Consume(event_type=PanelRequested),
        Consume(event_type=PopupRequested),
        Consume(event_type=MenuRequested),
        Consume(event_type=DialogRequested),
        Consume(event_type=ClosePanelRequested),
        Consume(event_type=PluginLoaded),
        Consume(event_type=PluginUnloaded),
        Consume(event_type=PluginLoadFailed),
        Consume(event_type=PluginHandlerError),
    ),
    pip_deps=("PySide6",),
    main_thread=True,
)
