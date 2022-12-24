"""Helper functions for IO operations on QuestDB."""
from json import dumps
import logging
from queue import Queue

from questdb.ingress import IngressError, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from homeassistant.core import Event

from .const import RETRY_ATTEMPTS, RETRY_WAIT_SECONDS

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


@retry(
    retry=retry_if_exception_type(IngressError),
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
)
def _retry_data_insertion(host: str, port: int, event: Event) -> None:
    """Usign a retry for inserting event data into QuestDB."""
    _insert_row(host, port, event)
    raise RuntimeError(
        _LOGGER.error(
            "Error in database update. Could not save after %s retries. Giving up",
            RETRY_ATTEMPTS,
        )
    )


def insert_event_data_into_questdb(
    host: str, port: int, event: Event, queue: Queue
) -> None:
    """Inserting given event data into QuestDB."""
    _retry_data_insertion(host, port, event)
    queue.task_done()
