"""Unit tests for the threadsafe async event bus.

Fake plugins record deliveries into lock-protected lists; ``bus.wait_idle``
synchronises the tests without sleeping.
"""

import threading
from dataclasses import dataclass
from typing import Callable, TypeVar

import pytest

from kernel.bus import EventBus
from kernel.envelope import Event, reply_to
from kernel.events import KERNEL_ID, PluginHandlerError
from kernel.manifest import Manifest
from kernel.plugin import Plugin, consume, reemit
from kernel.registry import TypeRegistry


@dataclass
class Ping:
    value: int = 0


@dataclass
class Pong:
    value: int = 0


@dataclass
class ChildPing(Ping):
    pass


class Recording(Plugin):
    """Base fake plugin: thread-safe list of received events."""

    def __init__(self) -> None:
        self.received: list[Event] = []
        self._lock = threading.Lock()

    def record(self, event: Event) -> None:
        with self._lock:
            self.received.append(event)

    def payloads(self) -> list[object]:
        with self._lock:
            return [event.payload for event in self.received]

    def count(self) -> int:
        with self._lock:
            return len(self.received)


class PingConsumer(Recording):
    @consume(Ping)
    def on_ping(self, event: Event) -> None:
        self.record(event)


class PongConsumer(Recording):
    @consume(Pong)
    def on_pong(self, event: Event) -> None:
        self.record(event)


class ErrorConsumer(Recording):
    @consume(PluginHandlerError)
    def on_error(self, event: Event) -> None:
        self.record(event)


class RaisingPingConsumer(Recording):
    @consume(Ping)
    def on_ping(self, event: Event) -> None:
        raise RuntimeError("boom")


class AddOneMiddleware(Plugin):
    @reemit(Ping)
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value + 1)


class TimesTenToAMiddleware(Plugin):
    @reemit(Ping, target_id="kuestion.a")
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value * 10)


class TimesTenFirstMiddleware(Plugin):
    @reemit(Ping, priority=1)
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value * 10)


class AddOneLastMiddleware(Plugin):
    @reemit(Ping, priority=100)
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value + 1)


class EqualAddOneMiddleware(Plugin):
    @reemit(Ping, priority=50)
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value + 1)


class EqualTimesTenMiddleware(Plugin):
    @reemit(Ping, priority=50)
    def transform(self, event: Event) -> Ping:
        return Ping(event.payload.value * 10)


class WrongTypeToAMiddleware(Plugin):
    @reemit(Ping, target_id="kuestion.a")
    def transform(self, event: Event) -> Pong:
        return Pong(event.payload.value)


class NoneToAMiddleware(Plugin):
    @reemit(Ping, target_id="kuestion.a")
    def transform(self, event: Event) -> None:
        return None


class RaisingMiddleware(Plugin):
    @reemit(Ping, target_id="kuestion.a")
    def transform(self, event: Event) -> object:
        raise RuntimeError("middleware boom")


class EchoResponder(Recording):
    @consume(Ping)
    def on_ping(self, event: Event) -> None:
        self.record(event)
        self.bus.emit(reply_to(event, Pong(event.payload.value), sender_id=self.manifest.id))


PluginT = TypeVar("PluginT", bound=Plugin)


def make_bus(**kwargs: object) -> EventBus:
    bus = EventBus(TypeRegistry(), **kwargs)
    bus.start()
    return bus


def register(bus: EventBus, plugin: PluginT, plugin_id: str, main_thread: bool = False) -> PluginT:
    plugin.manifest = Manifest(id=plugin_id, entry="plugin:Dummy", main_thread=main_thread)
    bus.register(plugin)
    return plugin


def broadcast(payload: object, sender_id: str = "kuestion.sender") -> Event:
    return Event(event_type=type(payload), payload=payload, sender_id=sender_id)


def run_concurrently(bus: EventBus, work: Callable[[], None], thread_count: int) -> None:
    threads = [threading.Thread(target=work) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    bus.wait_idle()


@pytest.fixture
def bus() -> EventBus:
    bus = make_bus()
    yield bus
    bus.stop()


def test_broadcast_reaches_every_subscriber_of_the_type(bus: EventBus) -> None:
    first = register(bus, PingConsumer(), "kuestion.a")
    second = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert first.count() == 1
    assert second.count() == 1


def test_non_subscribers_receive_nothing(bus: EventBus) -> None:
    other = register(bus, PongConsumer(), "kuestion.c")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert other.count() == 0


def test_subclass_payload_matches_parent_subscription(bus: EventBus) -> None:
    consumer = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(ChildPing(7)))
    bus.wait_idle()

    assert consumer.payloads() == [ChildPing(7)]


def test_directed_event_reaches_only_the_target(bus: EventBus) -> None:
    target = register(bus, PingConsumer(), "kuestion.a")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(Event(event_type=Ping, payload=Ping(1), sender_id="kuestion.sender", target_id="kuestion.b"))
    bus.wait_idle()

    assert target.count() == 0
    assert other.count() == 1


def test_directed_event_to_unknown_target_is_dead_lettered(bus: EventBus) -> None:
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(Event(event_type=Ping, payload=Ping(1), sender_id="kuestion.sender", target_id="kuestion.ghost"))
    bus.wait_idle()

    assert observer.payloads() == [PluginHandlerError("kuestion.ghost", "Ping", "no such plugin", "")]


def test_global_middleware_transforms_for_every_consumer_independently(bus: EventBus) -> None:
    register(bus, AddOneMiddleware(), "kuestion.mw.add")
    register(bus, TimesTenToAMiddleware(), "kuestion.mw.ten")
    first = register(bus, PingConsumer(), "kuestion.a")
    second = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert first.payloads() == [Ping(20)]
    assert second.payloads() == [Ping(2)]


def test_middleware_scoped_to_target_transforms_only_that_target(bus: EventBus) -> None:
    register(bus, TimesTenToAMiddleware(), "kuestion.mw.ten")
    target = register(bus, PingConsumer(), "kuestion.a")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(2)))
    bus.wait_idle()

    assert target.payloads() == [Ping(20)]
    assert other.payloads() == [Ping(2)]


def test_middleware_priority_lower_value_runs_first(bus: EventBus) -> None:
    register(bus, AddOneLastMiddleware(), "kuestion.mw.add")
    register(bus, TimesTenFirstMiddleware(), "kuestion.mw.ten")
    consumer = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert consumer.payloads() == [Ping(11)]


def test_equal_priority_middleware_keeps_registration_order(bus: EventBus) -> None:
    register(bus, EqualAddOneMiddleware(), "kuestion.mw.add")
    register(bus, EqualTimesTenMiddleware(), "kuestion.mw.ten")
    consumer = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert consumer.payloads() == [Ping(20)]


def test_wrong_type_middleware_skips_its_target(bus: EventBus) -> None:
    register(bus, WrongTypeToAMiddleware(), "kuestion.mw.wrong")
    target = register(bus, PingConsumer(), "kuestion.a")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert target.count() == 0
    assert other.payloads() == [Ping(3)]


def test_wrong_type_middleware_reports_an_error(bus: EventBus) -> None:
    register(bus, WrongTypeToAMiddleware(), "kuestion.mw.wrong")
    register(bus, PingConsumer(), "kuestion.a")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert observer.count() == 1


def test_none_middleware_skips_recipient_without_error(bus: EventBus) -> None:
    register(bus, NoneToAMiddleware(), "kuestion.mw.none")
    target = register(bus, PingConsumer(), "kuestion.a")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert target.count() == 0
    assert observer.count() == 0


def test_none_middleware_leaves_other_recipients_untouched(bus: EventBus) -> None:
    register(bus, NoneToAMiddleware(), "kuestion.mw.none")
    register(bus, PingConsumer(), "kuestion.a")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert other.count() == 1


def test_middleware_exception_skips_its_target(bus: EventBus) -> None:
    register(bus, RaisingMiddleware(), "kuestion.mw.raising")
    target = register(bus, PingConsumer(), "kuestion.a")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert target.count() == 0
    assert other.count() == 1


def test_middleware_exception_reports_an_error(bus: EventBus) -> None:
    register(bus, RaisingMiddleware(), "kuestion.mw.raising")
    register(bus, PingConsumer(), "kuestion.a")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(3)))
    bus.wait_idle()

    assert observer.count() == 1


def test_handler_exception_is_reported_and_other_recipients_unaffected(bus: EventBus) -> None:
    register(bus, RaisingPingConsumer(), "kuestion.boom")
    other = register(bus, PingConsumer(), "kuestion.b")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert other.count() == 1
    assert observer.count() == 1


def test_bus_keeps_delivering_after_a_handler_exception(bus: EventBus) -> None:
    register(bus, RaisingPingConsumer(), "kuestion.boom")
    other = register(bus, PingConsumer(), "kuestion.b")

    bus.emit(broadcast(Ping(1)))
    bus.emit(broadcast(Ping(2)))
    bus.wait_idle()

    assert other.payloads() == [Ping(1), Ping(2)]


def test_handler_error_names_the_failing_plugin(bus: EventBus) -> None:
    register(bus, RaisingPingConsumer(), "kuestion.boom")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert observer.payloads()[0].plugin_id == "kuestion.boom"


def test_kernel_errors_are_sent_by_the_kernel(bus: EventBus) -> None:
    register(bus, RaisingPingConsumer(), "kuestion.boom")
    observer = register(bus, ErrorConsumer(), "kuestion.observer")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert observer.received[0].sender_id == KERNEL_ID


def test_emit_is_threadsafe_and_delivers_each_event_exactly_once(bus: EventBus) -> None:
    consumer = register(bus, PingConsumer(), "kuestion.a")
    emit_count = 200
    thread_count = 4

    def emit_batch() -> None:
        for index in range(emit_count):
            bus.emit(broadcast(Ping(index)))

    run_concurrently(bus, emit_batch, thread_count)

    received = [payload.value for payload in consumer.payloads()]

    assert sorted(received) == sorted(list(range(emit_count)) * thread_count)


def test_reply_round_trip_preserves_correlation_id(bus: EventBus) -> None:
    requester = register(bus, PongConsumer(), "kuestion.requester")
    register(bus, EchoResponder(), "kuestion.responder")

    bus.emit(
        Event(
            event_type=Ping,
            payload=Ping(9),
            sender_id="kuestion.requester",
            target_id="kuestion.responder",
            correlation_id="abc",
        )
    )
    bus.wait_idle()

    assert requester.payloads() == [Pong(9)]
    assert requester.received[0].correlation_id == "abc"


def test_reply_generates_a_correlation_id_when_absent(bus: EventBus) -> None:
    requester = register(bus, PongConsumer(), "kuestion.requester")
    register(bus, EchoResponder(), "kuestion.responder")

    bus.emit(
        Event(
            event_type=Ping,
            payload=Ping(9),
            sender_id="kuestion.requester",
            target_id="kuestion.responder",
        )
    )
    bus.wait_idle()

    assert requester.received[0].correlation_id is not None


def test_unregister_stops_further_deliveries(bus: EventBus) -> None:
    consumer = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()
    bus.unregister("kuestion.a")
    bus.emit(broadcast(Ping(2)))
    bus.wait_idle()

    assert consumer.count() == 1


def test_unregistering_one_plugin_leaves_others_working(bus: EventBus) -> None:
    first = register(bus, PingConsumer(), "kuestion.a")
    second = register(bus, PingConsumer(), "kuestion.b")

    bus.unregister("kuestion.a")
    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert first.count() == 0
    assert second.count() == 1


def test_main_thread_plugin_is_delivered_through_the_callback() -> None:
    scheduled: list[object] = []

    def on_main(call: object) -> None:
        scheduled.append(call)
        call()

    bus = make_bus(on_main_thread=on_main)
    consumer = register(bus, PingConsumer(), "kuestion.a", main_thread=True)

    bus.emit(broadcast(Ping(5)))
    bus.wait_idle()
    bus.stop()

    assert consumer.payloads() == [Ping(5)]
    assert len(scheduled) == 1


def test_stop_is_idempotent() -> None:
    bus = make_bus()

    bus.stop()
    bus.stop()

    assert bus.wait_idle(timeout=0.1) is None


# -- observer tap ----------------------------------------------------------


def make_observer() -> tuple[list[Event], Callable[[Event], None]]:
    seen: list[Event] = []
    lock = threading.Lock()

    def observer(event: Event) -> None:
        with lock:
            seen.append(event)

    return seen, observer


def test_observer_receives_broadcast_events(bus: EventBus) -> None:
    seen, observer = make_observer()
    bus.add_observer(observer)
    register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert [event.payload for event in seen] == [Ping(1)]


def test_observer_receives_directed_events_the_target_also_gets(bus: EventBus) -> None:
    seen, observer = make_observer()
    bus.add_observer(observer)
    target = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(
        Event(event_type=Ping, payload=Ping(1), sender_id="kuestion.sender", target_id="kuestion.a")
    )
    bus.wait_idle()

    assert [event.payload for event in seen] == [Ping(1)]
    assert target.count() == 1


def test_observer_receives_dead_lettered_events(bus: EventBus) -> None:
    seen, observer = make_observer()
    bus.add_observer(observer)

    bus.emit(
        Event(
            event_type=Ping,
            payload=Ping(1),
            sender_id="kuestion.sender",
            target_id="kuestion.ghost",
        )
    )
    bus.wait_idle()

    assert [event.event_type for event in seen] == [Ping, PluginHandlerError]


def test_raising_observer_does_not_drop_deliveries(bus: EventBus) -> None:
    def bad_observer(event: Event) -> None:
        raise RuntimeError("observer boom")

    bus.add_observer(bad_observer)
    consumer = register(bus, PingConsumer(), "kuestion.a")

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()

    assert consumer.count() == 1


def test_remove_observer_stops_further_observations(bus: EventBus) -> None:
    seen, observer = make_observer()
    bus.add_observer(observer)

    bus.emit(broadcast(Ping(1)))
    bus.wait_idle()
    bus.remove_observer(observer)
    bus.emit(broadcast(Ping(2)))
    bus.wait_idle()

    assert [event.payload for event in seen] == [Ping(1)]
