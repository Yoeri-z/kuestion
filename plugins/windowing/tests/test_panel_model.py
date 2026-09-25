"""Unit tests for the Qt-free Plugins panel model."""

from __future__ import annotations

from plugins.windowing.src.panel_model import PluginPanelModel


def test_loaded_plugin_is_recorded_as_loaded() -> None:
    model = PluginPanelModel()

    model.mark_loaded("kuestion.windowing")

    entry = model.get("kuestion.windowing")
    assert entry is not None
    assert entry.status == "loaded"


def test_failed_plugin_records_error_and_stage() -> None:
    model = PluginPanelModel()

    model.mark_failed("kuestion.chat", "boom", "entry")

    entry = model.get("kuestion.chat")
    assert entry is not None
    assert (entry.status, entry.error, entry.stage) == ("failed", "boom", "entry")


def test_unloaded_plugin_becomes_disabled() -> None:
    model = PluginPanelModel()
    model.mark_loaded("kuestion.chat")

    model.mark_unloaded("kuestion.chat")

    assert model.get("kuestion.chat").status == "disabled"


def test_handler_error_is_recorded_for_loaded_plugin() -> None:
    model = PluginPanelModel()
    model.mark_loaded("kuestion.chat")

    model.mark_handler_error("kuestion.chat", "ValueError: nope")

    entry = model.get("kuestion.chat")
    assert entry.status == "error"
    assert entry.error == "ValueError: nope"


def test_entries_are_sorted_by_plugin_id() -> None:
    model = PluginPanelModel()
    model.mark_loaded("kuestion.windowing")
    model.mark_loaded("kuestion.chat")

    assert [entry.plugin_id for entry in model.entries()] == [
        "kuestion.chat",
        "kuestion.windowing",
    ]


def test_loaded_plugin_next_action_is_disable() -> None:
    model = PluginPanelModel()
    model.mark_loaded("kuestion.chat")

    assert model.next_action("kuestion.chat") == "disable"


def test_disabled_plugin_next_action_is_enable() -> None:
    model = PluginPanelModel()
    model.mark_loaded("kuestion.chat")

    model.mark_unloaded("kuestion.chat")

    assert model.next_action("kuestion.chat") == "enable"


def test_failed_plugin_has_no_next_action() -> None:
    model = PluginPanelModel()
    model.mark_failed("kuestion.chat", "boom", "entry")

    assert model.next_action("kuestion.chat") is None


def test_unknown_plugin_has_no_next_action() -> None:
    assert PluginPanelModel().next_action("nope") is None
