"""Helper functions for event handling and data insertion."""

from queue import Empty
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN

if TYPE_CHECKING:
    from collections.abc import Callable
    from queue import Queue

    from homeassistant.core import Event

QUEUE_POLL_TIMEOUT = object()
"""Sentinel returned by :func:`get_event_from_queue` when a poll times out.

Distinct from the ``None`` value that is put onto the queue to signal
shutdown, so callers can tell "no event arrived within ``timeout`` seconds"
apart from "the queue is being shut down".
"""


def put_event_to_queue(
    event: Event, entity_filter: Callable[[str], bool], queue: Queue
) -> None:
    """Get events with new states and put them in the process queue."""
    entity_id = event.data.get(ATTR_ENTITY_ID)
    state = event.data.get("new_state")
    if state is not None and all(
        [entity_id, state, state.state != STATE_UNKNOWN, entity_filter(entity_id)]
    ):
        queue.put(event)


def get_event_from_queue(
    queue: Queue, timeout: float | None = None
) -> Event | object | None:
    """Return event from process queue.

    If ``timeout`` is given and neither a real event nor the shutdown
    sentinel (``None``) arrives within that time, ``QUEUE_POLL_TIMEOUT`` is
    returned instead, so callers can perform periodic housekeeping (such as
    time-based flushing) without blocking indefinitely.
    """
    try:
        return queue.get(timeout=timeout)
    except Empty:
        return QUEUE_POLL_TIMEOUT


def finish_task_if_empty_event(event: Event, queue: Queue) -> None:
    """Finish process queue task in case of no events."""
    if event is None:
        queue.task_done()
