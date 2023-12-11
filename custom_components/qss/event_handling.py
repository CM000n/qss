"""Helper functions for event handling and data insertion."""
from queue import Queue
from typing import Callable

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import Event


def put_event_to_queue(
    event: Event, entity_filter: Callable[[str], bool], queue: Queue
) -> None:
    """Get events with new states and put them in the process queue."""
    entity_id = event.data.get(ATTR_ENTITY_ID)
    state = event.data.get("new_state")
    if all([
        entity_id,
        state,
        state.state != STATE_UNKNOWN,
        entity_filter(entity_id)
    ]):
        queue.put(event)


def get_event_from_queue(queue: Queue) -> Event:
    """Return event from process queue."""
    return queue.get()


def finish_task_if_empty_event(event: Event, queue: Queue) -> None:
    """Finish process queue task in case of no events."""
    if event is None:
        queue.task_done()
