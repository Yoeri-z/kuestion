"""Contract surface for the ``chat`` plugin."""

from plugins.chat.events import ChatMessage, ChatStreamChunk, ChatTurnComplete, ModelListChanged
from kernel.manifest import Consume, Manifest
from plugins.windowing.events import PanelRequested
from plugins.harness.events import ModelListRequest

MANIFEST = Manifest(
    id="kuestion.chat",
    entry="plugin:ChatPlugin",
    emits=(ChatMessage, PanelRequested, ModelListRequest),
    consumes=(
        Consume(event_type=ChatStreamChunk),
        Consume(event_type=ChatTurnComplete),
        Consume(event_type=ModelListChanged),
    ),
    requires=("kuestion.windowing", "kuestion.harness"),
)
