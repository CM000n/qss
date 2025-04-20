"""Helper functions for IO operations on QuestDB."""

import logging
from json import dumps
from queue import Queue

from homeassistant.core import Event
from questdb.ingress import IngressError, Protocol, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .const import RETRY_ATTEMPTS, RETRY_WAIT_SECONDS

_LOGGER = logging.getLogger(__name__)


def _insert_row_with_auth(host: str, port: int, auth: tuple, event: Event) -> None:
    with Sender(
        Protocol.Tcps,
        host,
        port,
        username=auth[0],
        token=auth[1],
        token_x=auth[2],
        token_y=auth[3],
        tls_verify=auth[4],
    ) as sender:
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


def _insert_row_without_auth(host: str, port: int, event: Event) -> None:
    with Sender(Protocol.Tcp, host, port) as sender:
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
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type(IngressError),
)
def _retry_data_insertion(host: str, port: int, auth: tuple, event: Event) -> None:
    """Use a retry for inserting event data into QuestDB."""
    if auth[0]:
        _insert_row_with_auth(host, port, auth, event)
    else:
        _insert_row_without_auth(host, port, event)


def insert_event_data_into_questdb(host: str, port: int, auth: tuple, event: Event, queue: Queue) -> None:
    try:
        """Insert given event data into QuestDB."""
        _LOGGER.debug("%s %s %s %s", host, port, auth, event)
        _retry_data_insertion(host, port, auth, event)
    except IngressError as e:
        _LOGGER.error(e)
    queue.task_done()
