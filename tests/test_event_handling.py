"""Unit tests for ``custom_components.qss.event_handling``."""

from __future__ import annotations

import queue

from homeassistant.const import STATE_UNKNOWN

from custom_components.qss.event_handling import (
    QUEUE_POLL_TIMEOUT,
    finish_task_if_empty_event,
    get_event_from_queue,
    put_event_to_queue,
)
from tests.helpers import make_state_changed_event


def test_put_event_to_queue_adds_matching_event() -> None:
    """A qualifying state changed event should be queued as-is."""
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.temperature", "21.5")

    put_event_to_queue(event, lambda _entity_id: True, event_queue)

    assert event_queue.qsize() == 1
    assert event_queue.get_nowait() is event


def test_put_event_to_queue_filters_excluded_entity() -> None:
    """Events for entities rejected by the entity filter must not be queued."""
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.excluded", "21.5")

    put_event_to_queue(event, lambda _entity_id: False, event_queue)

    assert event_queue.empty()


def test_put_event_to_queue_ignores_unknown_state() -> None:
    """Events reporting ``STATE_UNKNOWN`` must not be queued."""
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.temperature", STATE_UNKNOWN)

    put_event_to_queue(event, lambda _entity_id: True, event_queue)

    assert event_queue.empty()


def test_put_event_to_queue_ignores_missing_new_state() -> None:
    """Events without a ``new_state`` (e.g. entity removal) must not be queued."""
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.temperature", None)

    put_event_to_queue(event, lambda _entity_id: True, event_queue)

    assert event_queue.empty()


def test_get_event_from_queue_returns_queued_event() -> None:
    """The oldest queued event should be returned first (FIFO)."""
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.temperature", "21.5")
    event_queue.put(event)

    assert get_event_from_queue(event_queue) is event


def test_get_event_from_queue_returns_timeout_sentinel_when_empty() -> None:
    """Polling an empty queue with a timeout should return the timeout sentinel."""
    event_queue: queue.Queue = queue.Queue()

    assert get_event_from_queue(event_queue, timeout=0.01) is QUEUE_POLL_TIMEOUT


def test_finish_task_if_empty_event_marks_task_done_for_none() -> None:
    """A ``None`` sentinel event should mark the queue task as done."""
    event_queue: queue.Queue = queue.Queue()
    event_queue.put(None)
    event_queue.get()

    finish_task_if_empty_event(None, event_queue)

    event_queue.join()  # Must not block: proves task_done() was called.


def test_finish_task_if_empty_event_ignores_real_events() -> None:
    """A real event must not trigger ``task_done`` on the queue.

    Calling ``task_done()`` without a matching ``get()`` raises ``ValueError``,
    so this call succeeding without error proves it was a no-op.
    """
    event_queue: queue.Queue = queue.Queue()
    event = make_state_changed_event("sensor.temperature", "21.5")

    finish_task_if_empty_event(event, event_queue)
