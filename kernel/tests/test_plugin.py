"""Unit tests for the Plugin base class and its subscription decorators."""

from dataclasses import dataclass

from kernel.plugin import Plugin, ReEmitHandler, consume, reemit


@dataclass
class Ping:
    value: int = 0


@dataclass
class Pong:
    value: int = 0


class RecordingPlugin(Plugin):
    @consume(Ping)
    def handle_ping(self, event: object) -> None:
        pass

    @consume(Ping)
    def also_handle_ping(self, event: object) -> None:
        pass

    @consume(Pong)
    def handle_pong(self, event: object) -> None:
        pass

    @reemit(Pong, target_id="kuestion.other", priority=5)
    def transform_pong(self, event: object) -> object:
        return event


class EmptyPlugin(Plugin):
    pass


def test_consume_decorator_registers_handlers_by_type() -> None:
    plugin = RecordingPlugin()

    subscriptions = plugin.subscriptions()

    assert subscriptions.consumes[Ping] == [plugin.handle_ping, plugin.also_handle_ping]


def test_consume_decorator_keeps_distinct_types_separate() -> None:
    plugin = RecordingPlugin()

    subscriptions = plugin.subscriptions()

    assert subscriptions.consumes[Pong] == [plugin.handle_pong]


def test_reemit_decorator_records_type_target_and_priority() -> None:
    plugin = RecordingPlugin()

    subscriptions = plugin.subscriptions()

    assert subscriptions.reemits[(Pong, "kuestion.other")] == [ReEmitHandler(plugin.transform_pong, 5)]


def test_plugin_without_handlers_has_empty_subscriptions() -> None:
    subscriptions = EmptyPlugin().subscriptions()

    assert subscriptions.consumes == {}
    assert subscriptions.reemits == {}
