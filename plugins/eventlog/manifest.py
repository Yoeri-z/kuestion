"""Contract surface for the ``eventlog`` plugin.

The event-log plugin has no event types of its own: it observes the bus through
the kernel's read-only observer tap and displays itself through the existing
``windowing`` :class:`~plugins.windowing.events.DialogRequested` contract.
"""

from kernel.manifest import Manifest
from plugins.windowing.events import DialogRequested

MANIFEST = Manifest(
    id="kuestion.eventlog",
    entry="plugin:EventLogPlugin",
    emits=(DialogRequested,),
    requires=("kuestion.windowing",),
)
