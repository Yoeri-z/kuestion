"""Contract surface for the ``keyregistry`` plugin."""

from kernel.manifest import Consume, Manifest
from plugins.windowing.events import DialogRequested

from plugins.keyregistry.events import (
    ModelListChanged,
    ModelListRequest,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
)

MANIFEST = Manifest(
    id="kuestion.keyregistry",
    entry="plugin:KeyRegistryPlugin",
    emits=(ModelResponse, ModelStreamChunk, ModelListChanged, DialogRequested),
    consumes=(Consume(event_type=ModelRequest), Consume(event_type=ModelListRequest)),
    requires=("kuestion.windowing",),
    pip_deps=("httpx",),
)
