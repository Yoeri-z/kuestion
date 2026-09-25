"""Qt-free model of the dock workspace.

Tracks which panels exist, their titles, and their dock area, and enforces that
at most one panel is the central widget. The windowing plugin renders this model
into ``QDockWidget``s; the model itself imports no Qt and is unit-testable
without a window.
"""

from __future__ import annotations

from dataclasses import dataclass

AREAS = ("left", "right", "top", "bottom")
DEFAULT_AREA = "right"


@dataclass(frozen=True)
class PanelEntry:
    """One registered panel."""

    panel_id: str
    title: str
    area: str = DEFAULT_AREA
    center: bool = False
    owner: str | None = None


class WorkspaceModel:
    """Tracks panels; the first centered request claims the central widget."""

    def __init__(self) -> None:
        self._panels: dict[str, PanelEntry] = {}

    def add(
        self,
        panel_id: str,
        title: str,
        *,
        area: str = DEFAULT_AREA,
        center: bool = False,
        owner: str | None = None,
    ) -> PanelEntry:
        if area not in AREAS:
            raise ValueError(f"unknown dock area: {area!r}")
        if center and self.central_id() not in (None, panel_id):
            center = False
        entry = PanelEntry(panel_id, title, area, center, owner)
        self._panels[panel_id] = entry
        return entry

    def remove(self, panel_id: str) -> None:
        self._panels.pop(panel_id, None)

    def remove_owned_by(self, owner: str) -> None:
        for panel_id in self.owned_by(owner):
            self._panels.pop(panel_id, None)

    def owned_by(self, owner: str) -> list[str]:
        return [panel_id for panel_id, entry in self._panels.items() if entry.owner == owner]

    def get(self, panel_id: str) -> PanelEntry | None:
        return self._panels.get(panel_id)

    def central_id(self) -> str | None:
        for entry in self._panels.values():
            if entry.center:
                return entry.panel_id
        return None

    def panels(self) -> list[PanelEntry]:
        return [self._panels[panel_id] for panel_id in sorted(self._panels)]
