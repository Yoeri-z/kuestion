"""Contract surface for the example ``trim_history`` middleware plugin.

Only this module is imported during validation. It imports the ``ModelRequest``
type it re-emits from its owner (``keyregistry``) rather than redeclaring it, so
the type registry stays free of duplicates.
"""

from kernel.manifest import Manifest, ReEmit
from plugins.keyregistry.events import ModelRequest

#: The middleware applies only to the key registry. The chat window keeps the
#: full conversation; only the outbound ``ModelRequest`` is trimmed.
TARGET_ID = "kuestion.keyregistry"

#: Lower priority runs first (before any default ``priority=100`` middleware).
PRIORITY = 10

MANIFEST = Manifest(
    id="kuestion.example.trim_history",
    entry="plugin:TrimHistoryPlugin",
    reemits=(ReEmit(event_type=ModelRequest, target_id=TARGET_ID, priority=PRIORITY),),
    requires=(TARGET_ID,),
)
