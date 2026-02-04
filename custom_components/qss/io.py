"""Helper functions for IO operations on QuestDB."""

import logging
from json import dumps
from queue import Queue

from homeassistant.core import Event
from questdb.ingress import IngressError, Sender
from tenacity import retry, stop_after_attempt, wait_fixed

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


def _should_retry_error(exception: Exception) -> bool:
    """Determine if an IngressError should be retried."""
    # Don't retry if the sender is closed
    if isinstance(exception, IngressError):
        error_msg = str(exception).lower()
        return "sender is closed" not in error_msg and "closed" not in error_msg
    return False


@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=_should_retry_error,
)
def _retry_data_insertion(sender: Sender, event: Event) -> None:
    """Use a retry for inserting event data into QuestDB."""
    try:
        _insert_row(sender, event)
    except IngressError as err:
        # If sender is closed, we can't retry
        error_msg = str(err).lower()
        if "closed" in error_msg:
            _LOGGER.exception("Sender is closed, cannot insert data")
            msg = "Sender is closed"
            raise RuntimeError(msg) from err
        raise


def insert_event_data_into_questdb(sender: Sender, event: Event, queue: Queue) -> None:  # noqa: ARG001
    """Insert given event data into QuestDB using reusable sender."""
    if sender is None:
        _LOGGER.warning("Sender is not available, skipping event.")
        return

    _retry_data_insertion(sender, event)
