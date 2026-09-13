"""Root pytest configuration.

Run all Qt tests headless (CI / offscreen). Kept at repo root so it
applies to kernel/tests and every plugins/<name>/tests directory.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
