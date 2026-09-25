"""Threadsafe async event bus.

Delivery model (Phase 4 kernel spec):

* a dedicated **event thread** drains one central queue;
* every non-main-thread plugin owns a **handler thread** and its own queue;
* a broadcast event is delivered to every plugin with a matching subscription,
  each getting its **own** middleware chain (global + targeted re-emitters,
  ordered by priority then registration order) and an independent payload;
* directed events go to exactly one plugin (unknown target = dead letter);
* handler and middleware exceptions are reported as ``PluginHandlerError``
  events and never kill the bus.

``emit`` is safe from any thread and never blocks the emitter.

Read-only **observer tap**: callers may register an ``Event`` observer that
sees every dispatched event (broadcast, directed, and dead-lettered) before
routing. Observers never change recipient sets, middleware chains, or
delivery order, must be fast and must not emit (re-entrancy), and their
exceptions are logged and swallowed so a broken observer cannot break dispatch.
"""

from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace

from kernel.envelope import Event
from kernel.events import KERNEL_ID, PluginHandlerError
from kernel.plugin import Plugin
from kernel.registry import TypeRegistry

logger = logging.getLogger(__name__)

#: Schedules a zero-argument callable to run on the main thread. The kernel
#: stays Qt-agnostic; the windowing plugin supplies the real bridge.
MainThreadScheduler = Callable[[Callable[[], None]], None]

_STOP = object()


@dataclass(frozen=True)
class _ConsumeEntry:
    event_type: type
    order: int
    handler: Callable[..., None]


@dataclass(frozen=True)
class _ReEmitEntry:
    event_type: type
    target_id: str | None
    priority: int
    order: int
    plugin_id: str
    handler: Callable[..., object]


class EventBus:
    """Async producer/consumer bus with per-plugin handler threads."""

    def __init__(
        self,
        registry: TypeRegistry,
        on_main_thread: MainThreadScheduler | None = None,
    ) -> None:
        self._registry = registry
        self._on_main_thread = on_main_thread
        self._consume: dict[str, list[_ConsumeEntry]] = {}
        self._reemit: list[_ReEmitEntry] = []
        self._observers: list[Callable[[Event], None]] = []
        self._main_thread: set[str] = set()
        self._registered: set[str] = set()
        self._queues: dict[str, queue.Queue] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.RLock()
        self._order = itertools.count()

        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stopped = False

        self._work = 0
        self._work_cv = threading.Condition()

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Spawn the dedicated event thread (idempotent)."""
        with self._lock:
            if self._thread is not None or self._stopped:
                return
            self._thread = threading.Thread(target=self._run, name="kuestion-event", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Drain then join the event thread and all handler threads (idempotent)."""
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            thread = self._thread
            queues = list(self._queues.values())
            threads = list(self._threads.values())

        self._queue.put(_STOP)
        if thread is not None:
            thread.join(timeout)
        for worker_queue in queues:
            worker_queue.put(_STOP)
        for worker_thread in threads:
            worker_thread.join(timeout)

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Block until the central queue, every handler queue and any scheduled
        main-thread deliveries are empty. Raises ``TimeoutError`` on timeout."""
        deadline = time.monotonic() + timeout
        with self._work_cv:
            while self._work > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("event bus did not become idle")
                self._work_cv.wait(remaining)

    # -- registration ------------------------------------------------------

    def register(self, plugin: Plugin) -> None:
        """Wire a plugin's subscriptions and start its handler thread."""
        plugin.bus = self
        subscriptions = plugin.subscriptions()
        plugin_id = plugin.manifest.id

        with self._lock:
            self._registered.add(plugin_id)
            entries = self._consume.setdefault(plugin_id, [])
            for event_type, handlers in subscriptions.consumes.items():
                for handler in handlers:
                    entries.append(_ConsumeEntry(event_type, next(self._order), handler))
            for (event_type, target_id), re_handlers in subscriptions.reemits.items():
                for re_handler in re_handlers:
                    self._reemit.append(
                        _ReEmitEntry(
                            event_type=event_type,
                            target_id=target_id,
                            priority=re_handler.priority,
                            order=next(self._order),
                            plugin_id=plugin_id,
                            handler=re_handler.handler,
                        )
                    )

            if plugin.manifest.main_thread:
                self._main_thread.add(plugin_id)
                return

            worker_queue: queue.Queue = queue.Queue()
            worker = threading.Thread(
                target=self._run_plugin,
                args=(plugin_id, worker_queue),
                name=f"kuestion-{plugin_id}",
                daemon=True,
            )
            self._queues[plugin_id] = worker_queue
            self._threads[plugin_id] = worker
            worker.start()

    def unregister(self, plugin_id: str) -> None:
        """Drop a plugin's subscriptions and stop its handler thread, draining
        its queue first."""
        with self._lock:
            self._registered.discard(plugin_id)
            self._consume.pop(plugin_id, None)
            self._reemit = [entry for entry in self._reemit if entry.plugin_id != plugin_id]
            self._main_thread.discard(plugin_id)
            worker_queue = self._queues.pop(plugin_id, None)
            worker = self._threads.pop(plugin_id, None)

        if worker_queue is not None:
            worker_queue.put(_STOP)
        if worker is not None:
            worker.join(5.0)

    # -- observer tap ------------------------------------------------------

    def add_observer(self, observer: Callable[[Event], None]) -> None:
        """Register a read-only observer of every dispatched event."""
        with self._lock:
            self._observers.append(observer)

    def remove_observer(self, observer: Callable[[Event], None]) -> None:
        """Stop observing events (no-op if the observer is not registered)."""
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    # -- emitting ----------------------------------------------------------

    def emit(self, event: Event) -> None:
        """Publish an event from any thread without blocking the emitter."""
        self._add_work()
        self._queue.put(event)

    # -- event thread ------------------------------------------------------

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            try:
                self._dispatch(item)
            finally:
                self._done_work()

    def _dispatch(self, event: Event) -> None:
        self._notify_observers(event)
        if event.target_id is not None:
            with self._lock:
                known = event.target_id in self._registered
            if not known:
                self._emit_dead_letter(event)
                return
            self._deliver(event, event.target_id)
            return

        with self._lock:
            recipients = [
                plugin_id
                for plugin_id in self._registered
                if self._has_subscription(plugin_id, event.event_type)
            ]
        for plugin_id in recipients:
            self._deliver(event, plugin_id)

    def _notify_observers(self, event: Event) -> None:
        with self._lock:
            observers = list(self._observers)
        for observer in observers:
            try:
                observer(event)
            except Exception:  # noqa: BLE001 - observers are best-effort
                logger.warning("event observer failed", exc_info=True)

    def _has_subscription(self, plugin_id: str, event_type: type) -> bool:
        if any(issubclass(event_type, entry.event_type) for entry in self._consume.get(plugin_id, ())):
            return True
        return any(
            entry.plugin_id == plugin_id and issubclass(event_type, entry.event_type)
            for entry in self._reemit
        )

    # -- per-recipient delivery -------------------------------------------

    def _deliver(self, event: Event, recipient: str) -> None:
        with self._lock:
            chain = sorted(
                (
                    entry
                    for entry in self._reemit
                    if issubclass(event.event_type, entry.event_type)
                    and (entry.target_id is None or entry.target_id == recipient)
                ),
                key=lambda entry: (entry.priority, entry.order),
            )
            handlers = [
                entry.handler
                for entry in self._consume.get(recipient, ())
                if issubclass(event.event_type, entry.event_type)
            ]
            is_main = recipient in self._main_thread

        for entry in chain:
            try:
                result = entry.handler(event)
            except Exception as exc:  # noqa: BLE001 - boundary: report, never crash the bus
                self._emit_handler_error(entry.plugin_id, event, exc)
                return
            if result is None:
                return
            if not isinstance(result, event.event_type):
                self._emit_handler_error(
                    entry.plugin_id,
                    event,
                    TypeError(
                        f"re-emit handler returned {type(result).__name__}, "
                        f"expected {event.event_type.__name__} or a subclass"
                    ),
                )
                return
            event = replace(event, event_type=type(result), payload=result)

        if is_main and self._on_main_thread is not None:
            self._schedule_main(lambda: self._invoke(recipient, handlers, event))
            return
        if is_main:
            self._invoke(recipient, handlers, event)
            return

        with self._lock:
            worker_queue = self._queues.get(recipient)
            if worker_queue is None:
                return
            self._add_work()
            worker_queue.put((recipient, handlers, event))

    def _schedule_main(self, fn: Callable[[], None]) -> None:
        self._add_work()

        def wrapper() -> None:
            try:
                fn()
            finally:
                self._done_work()

        self._on_main_thread(wrapper)  # type: ignore[misc]

    # -- plugin threads ----------------------------------------------------

    def _run_plugin(self, plugin_id: str, worker_queue: queue.Queue) -> None:
        while True:
            item = worker_queue.get()
            if item is _STOP:
                return
            recipient, handlers, event = item
            try:
                self._invoke(recipient, handlers, event)
            finally:
                self._done_work()

    def _invoke(self, plugin_id: str, handlers: list[Callable[..., None]], event: Event) -> None:
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 - boundary: report, never crash the bus
                self._emit_handler_error(plugin_id, event, exc)

    # -- kernel notices ----------------------------------------------------

    def _emit_dead_letter(self, event: Event) -> None:
        payload = PluginHandlerError(event.target_id, event.event_type.__name__, "no such plugin", "")
        self._add_work()
        self._queue.put(Event(event_type=PluginHandlerError, payload=payload, sender_id=KERNEL_ID))

    def _emit_handler_error(self, plugin_id: str, event: Event, exc: Exception) -> None:
        payload = PluginHandlerError(
            plugin_id=plugin_id,
            event_type_name=event.event_type.__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        self._add_work()
        self._queue.put(Event(event_type=PluginHandlerError, payload=payload, sender_id=KERNEL_ID))

    # -- work accounting ---------------------------------------------------

    def _add_work(self) -> None:
        with self._work_cv:
            self._work += 1

    def _done_work(self) -> None:
        with self._work_cv:
            self._work -= 1
            if self._work == 0:
                self._work_cv.notify_all()
