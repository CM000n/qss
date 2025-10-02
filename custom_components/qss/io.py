"""Helper functions for IO operations on QuestDB."""

import logging
from json import dumps
from queue import Queue

from homeassistant.core import Event
from questdb.ingress import IngressError, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .const import RETRY_ATTEMPTS, RETRY_WAIT_SECONDS

_LOGGER = logging.getLogger(__name__)


def _insert_row(sender: Sender, event: Event) -> None:
    """Insert a single row using the provided sender."""
    entity_id = event.data["entity_id"]
    state = event.data.get("new_state")
    attrs = dict(state.attributes)
    sender.row(
        "qss",
        symbols={"entity_id": entity_id},
        columns={
            "state": state.state,
            "attributes": dumps(attrs, sort_keys=True, default=str),
        },
        at=event.time_fired,
    )

    sender.flush()


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type(IngressError),
)
def _retry_data_insertion(sender: Sender, event: Event) -> None:
    """Use a retry for inserting event data into QuestDB."""
    _insert_row(sender, event)


def insert_event_data_into_questdb(
    sender: Sender, event: Event, queue: Queue
) -> None:
    """Insert given event data into QuestDB using reusable sender."""
    try:
        _LOGGER.debug("Inserting event: %s", event)
        _retry_data_insertion(sender, event)
    except IngressError:
        _LOGGER.exception("Failed to insert event data into QuestDB")
    queue.task_done()
