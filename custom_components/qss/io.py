"""Helper functions for IO operations on QuestDB."""
import logging
from json import dumps
from queue import Queue

from homeassistant.core import Event
from questdb.ingress import IngressError, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .const import RETRY_ATTEMPTS, RETRY_WAIT_SECONDS

_LOGGER = logging.getLogger(__name__)


def _insert_row_with_auth(host: str, port: int, auth: tuple, event: Event, split_attributes: bool) -> None:
    with Sender(host, port, auth=auth, tls=True) as sender:
        entity_id = event.data["entity_id"]
        state = event.data.get("new_state")
        columns = {"state": state.state}
        if split_attributes:
            columns.update(state.attributes)
        else:
            columns["attrs"] = dumps(dict(state.attributes), sort_keys=True, default=str)
        sender.row(
            "qss",
            symbols={
                "entity_id": entity_id,
            },
            columns=columns,
            at=event.time_fired,
        )

        sender.flush()


def _insert_row_without_auth(host: str, port: int, event: Event, split_attributes: bool) -> None:
    with Sender(host, port) as sender:
        entity_id = event.data["entity_id"]
        state = event.data.get("new_state")
        columns = {"state": state.state}
        if split_attributes:
            columns.update(state.attributes)
        else:
            columns["attrs"] = dumps(dict(state.attributes), sort_keys=True, default=str)
        sender.row(
            "qss",
            symbols={
                "entity_id": entity_id,
            },
            columns=columns,
            at=event.time_fired,
        )

        sender.flush()


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type(IngressError),
)
def _retry_data_insertion(host: str, port: int, auth: tuple, event: Event, split_attributes: bool) -> None:
    """Use a retry for inserting event data into QuestDB."""
    if all(auth):
        _insert_row_with_auth(host, port, auth, event, split_attributes)
    else:
        _insert_row_without_auth(host, port, event, split_attributes)


def insert_event_data_into_questdb(host: str, port: int, auth: tuple, event: Event, queue: Queue, split_attributes: bool) -> None:
    """Insert given event data into QuestDB."""
    _retry_data_insertion(host, port, auth, event, split_attributes)
    queue.task_done()
