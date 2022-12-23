"""Helper functions for IO operations on QuestDB."""
from json import dumps
import logging
from queue import Queue
from time import sleep

from questdb.ingress import IngressError, Sender

from homeassistant.core import Event

from .const import RETRY_WAIT_SECONDS

_LOGGER = logging.getLogger(__name__)


def _insert_row(host: str, port: int, event: Event) -> None:
    with Sender(host, port) as sender:
        entity_id = event.data["entity_id"]
        state = event.data.get("new_state")
        attrs = dict(state.attributes)
        sender.row(
            "qss",
            symbols={
                "entity_id": entity_id,
            },
            columns={
                "state": state.state,
                "attributes": dumps(attrs, sort_keys=True, default=str),
            },
            at=event.time_fired,
        )

        sender.flush()


def insert_event_data_into_questdb(
    host: str, port: int, event: Event, queue: Queue
) -> None:
    """Inserting given event data into QuestDB."""
    tries = 1
    updated = False
    while not updated and tries <= 10:
        if tries != 1:
            sleep(RETRY_WAIT_SECONDS)
        try:
            _insert_row(host, port, event)
            updated = True
        except IngressError as err:
            _LOGGER.error(
                "Error during data insert: %s",
                err,
            )
            tries += 1

    if not updated:
        _LOGGER.error(
            "Error in database update. Could not save after %s tries. Giving up",
            tries,
        )

    queue.task_done()
