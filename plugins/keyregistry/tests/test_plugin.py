"""Unit tests for the key registry plugin handlers against a fake bus."""

from __future__ import annotations

from pathlib import Path

from kernel.envelope import Event
from kernel.manifest import Manifest

from plugins.keyregistry.events import ModelListChanged, ModelListRequest
from plugins.keyregistry.plugin import KeyRegistryPlugin
from plugins.keyregistry.src.config import ModelEntry

REQUESTER_ID = "kuestion.chat"


class FakeBus:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def emit(self, event: Event) -> None:
        self.events.append(event)


def make_plugin(tmp_path: Path) -> KeyRegistryPlugin:
    plugin = KeyRegistryPlugin(registry_path=tmp_path / "models.json")
    plugin.manifest = Manifest(id="kuestion.keyregistry", entry="plugin:KeyRegistryPlugin")
    plugin.bus = FakeBus()
    return plugin


def model_list_request() -> Event:
    return Event(
        event_type=ModelListRequest,
        payload=ModelListRequest(),
        sender_id=REQUESTER_ID,
        target_id="kuestion.keyregistry",
    )


def test_model_list_request_replies_with_configured_names(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)
    plugin.add_entry(ModelEntry(name="mymodel", base_url="http://x", model_id="gpt-x", api_key="k"))

    plugin._on_model_list_request(model_list_request())

    reply = plugin.bus.events[0]
    assert reply.event_type is ModelListChanged
    assert reply.payload.names == ["mymodel"]


def test_model_list_reply_is_directed_back_at_the_requester(tmp_path: Path) -> None:
    plugin = make_plugin(tmp_path)

    plugin._on_model_list_request(model_list_request())

    assert plugin.bus.events[0].target_id == REQUESTER_ID
