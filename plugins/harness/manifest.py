"""Contract surface for the ``harness`` plugin."""

from plugins.harness.events import (
    AttachmentParsed,
    ChatMessage,
    ChatStreamChunk,
    ChatTurnComplete,
    ModelRequest,
    ModelResponse,
    ModelStreamChunk,
)
from kernel.manifest import Consume, Manifest

MANIFEST = Manifest(
    id="kuestion.harness",
    entry="plugin:HarnessPlugin",
    emits=(
        AttachmentParsed,
        ChatStreamChunk,
        ChatTurnComplete,
        ModelRequest,
    ),
    consumes=(
        Consume(event_type=ChatMessage),
        Consume(event_type=AttachmentParsed),
        Consume(event_type=ModelStreamChunk),
        Consume(event_type=ModelResponse),
    ),
    requires=("kuestion.keyregistry",),
)
