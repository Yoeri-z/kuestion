"""Unit tests for the event envelope and reply helper."""

from dataclasses import dataclass

from kernel.envelope import Event, reply_to


@dataclass
class Request:
    text: str


@dataclass
class Response:
    text: str


def make_event(**overrides: object) -> Event:
    base = {
        "event_type": Request,
        "payload": Request("hello"),
        "sender_id": "kuestion.chat",
    }
    return Event(**(base | overrides))


def test_target_and_correlation_default_to_none() -> None:
    event = make_event()

    assert event.target_id is None
    assert event.correlation_id is None


def test_explicit_fields_are_preserved() -> None:
    event = make_event(target_id="kuestion.harness", correlation_id="abc")

    assert event.target_id == "kuestion.harness"
    assert event.correlation_id == "abc"


def test_timestamp_is_a_float() -> None:
    assert isinstance(make_event().timestamp, float)


def test_reply_is_directed_at_the_original_sender() -> None:
    reply = reply_to(make_event(sender_id="kuestion.chat"), Response("hi"), sender_id="kuestion.harness")

    assert reply.target_id == "kuestion.chat"
    assert reply.sender_id == "kuestion.harness"


def test_reply_targets_the_sender_of_a_directed_original() -> None:
    original = make_event(sender_id="kuestion.chat", target_id="kuestion.harness")

    reply = reply_to(original, Response("hi"), sender_id="kuestion.harness")

    assert reply.target_id == "kuestion.chat"


def test_reply_reuses_an_existing_correlation_id() -> None:
    reply = reply_to(
        make_event(correlation_id="abc"),
        Response("hi"),
        sender_id="kuestion.harness",
    )

    assert reply.correlation_id == "abc"


def test_reply_generates_a_uuid4_hex_when_correlation_absent() -> None:
    reply = reply_to(make_event(), Response("hi"), sender_id="kuestion.harness")

    assert len(reply.correlation_id) == 32


def test_reply_event_type_and_payload_come_from_the_payload() -> None:
    payload = Response("hi")

    reply = reply_to(make_event(), payload, sender_id="kuestion.harness")

    assert reply.event_type is Response
    assert reply.payload is payload
