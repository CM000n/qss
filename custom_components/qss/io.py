"""Helper functions for IO operations on QuestDB."""

import logging
from dataclasses import dataclass, field
from json import dumps
from queue import Queue

from homeassistant.core import Event
from questdb.ingress import IngressError, Protocol, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .const import DEFAULT_TABLE_NAME, RETRY_ATTEMPTS, RETRY_WAIT_SECONDS

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuestDBAuth:
    """Authentication settings for connecting to QuestDB."""

    kid: str = ""
    d_key: str = ""
    x_key: str = ""
    y_key: str = ""
    ssl_check: bool = True


@dataclass(frozen=True)
class QuestDBConfig:
    """Connection settings used to insert data into QuestDB."""

    host: str
    port: int
    table_name: str = DEFAULT_TABLE_NAME
    auth: QuestDBAuth = field(default_factory=QuestDBAuth)


def _create_sender(config: QuestDBConfig) -> Sender:
    """Create a QuestDB Sender based on authentication settings."""
    auth = config.auth
    if auth.kid:  # Authenticated
        return Sender(
            Protocol.Tcps,
            config.host,
            config.port,
            username=auth.kid,
            token=auth.d_key,
            token_x=auth.x_key,
            token_y=auth.y_key,
            tls_verify=auth.ssl_check,
        )
    return Sender(Protocol.Tcp, config.host, config.port)


def _insert_row(sender: Sender, event: Event, table_name: str) -> None:
    """Insert a single row using the provided sender."""
    entity_id = event.data["entity_id"]
    state = event.data.get("new_state")
    attrs = dict(state.attributes)
    sender.row(
        table_name,
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
def _retry_data_insertion(config: QuestDBConfig, event: Event) -> None:
    """Use a retry for inserting event data into QuestDB."""
    with _create_sender(config) as sender:
        _insert_row(sender, event, config.table_name)


def insert_event_data_into_questdb(
    config: QuestDBConfig, event: Event, queue: Queue
) -> None:
    """Insert given event data into QuestDB using a context-managed sender."""
    try:
        _LOGGER.debug("Inserting event: %s", event)
        _retry_data_insertion(config, event)
    except IngressError:
        _LOGGER.exception("Failed to insert event data into QuestDB.")
    queue.task_done()
