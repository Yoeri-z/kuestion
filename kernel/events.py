"""Kernel-declared lifecycle event types.

The kernel acts as the declaring "plugin" for these types; its plugin id is
:data:`KERNEL_ID`.
"""

from dataclasses import dataclass

KERNEL_ID = "kuestion.kernel"


@dataclass
class PluginLoaded:
    plugin_id: str


@dataclass
class PluginUnloaded:
    plugin_id: str


@dataclass
class PluginLoadFailed:
    plugin_id: str
    error: str
    stage: str  # "discover" | "manifest" | "deps" | "types" | "entry" | "pip"


@dataclass
class PluginHandlerError:
    plugin_id: str
    event_type_name: str
    error: str
    traceback: str
