"""Helper functions for IO operations on QuestDB."""

import logging
from dataclasses import dataclass, field
from json import dumps
from time import monotonic
from typing import TYPE_CHECKING

from questdb.ingress import IngressError, Protocol, Sender
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from .const import (
    DEFAULT_FLUSH_INTERVAL_SECONDS,
    DEFAULT_MAX_BATCH_SIZE,
    DEFAULT_TABLE_NAME,
    RETRY_ATTEMPTS,
    RETRY_WAIT_SECONDS,
)

if TYPE_CHECKING:
    from queue import Queue

    from homeassistant.core import Event

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
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE
    flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS


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
    """Buffer a single row on the provided sender without flushing it.

    Flushing is the caller's responsibility, so that many rows can be
    buffered and sent to QuestDB together instead of one row per network
    round-trip.
    """
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


class QuestDBConnection:
    """Manage a single, long-lived QuestDB ``Sender`` connection.

    Instead of opening and closing a new connection for every event, a single
    connection is created lazily on the first buffered row and reused across
    many events. Rows are only flushed to QuestDB once ``max_batch_size`` rows
    have been buffered, or once ``flush_interval_seconds`` have elapsed since
    the last flush, whichever happens first. On a transient ``IngressError``
    the (possibly broken) connection is dropped and lazily recreated before
    the next retry attempt.
    """

    def __init__(self, config: QuestDBConfig) -> None:
        """Initialize the connection wrapper for the given configuration."""
        self._config = config
        self._sender: Sender | None = None
        self._pending_rows = 0
        self._last_flush_monotonic = monotonic()

    @property
    def config(self) -> QuestDBConfig:
        """Return the configuration this connection was created with."""
        return self._config

    def insert_event(self, event: Event) -> None:
        """Buffer ``event`` as a row, retrying with reconnection on failure."""
        self._insert_with_retry(event)

    def flush_if_due(self) -> None:
        """Flush buffered rows if the configured flush interval has elapsed.

        Intended to be called from the background thread's idle poll (i.e.
        when no new event arrived within ``flush_interval_seconds``), so that
        buffered rows are not held indefinitely in memory during quiet
        periods.

        Unlike :meth:`insert_event`, a failure here is not retried: there is
        no new event to re-buffer on a fresh connection, so the rows already
        buffered on a now-broken sender cannot be recovered. The failure is
        logged and the connection is dropped so the next event lazily
        reconnects.
        """
        if self._pending_rows and self._interval_elapsed():
            try:
                self._flush()
            except IngressError:
                _LOGGER.exception(
                    "Failed to flush buffered rows to QuestDB; the buffered "
                    "rows were lost and the connection will be re-established."
                )
                self._reconnect()

    def close(self) -> None:
        """Flush any buffered rows and close the underlying connection.

        Safe to call even if no event was ever processed (no connection was
        ever created). Best-effort: any error while flushing/closing is
        logged rather than raised, so that shutdown is never blocked.
        """
        if self._sender is None:
            return
        sender, self._sender = self._sender, None
        self._pending_rows = 0
        try:
            sender.close(flush=True)
        except IngressError:
            _LOGGER.exception(
                "Failed to flush buffered rows while closing the QuestDB connection."
            )

    def _ensure_sender(self) -> Sender:
        """Lazily create and establish the underlying sender connection."""
        if self._sender is None:
            sender = _create_sender(self._config)
            sender.establish()
            self._sender = sender
        return self._sender

    def _reconnect(self) -> None:
        """Drop the current (possibly broken) sender.

        The next use lazily creates a fresh one. Any rows buffered on the
        dropped sender are lost, matching the previous per-event behaviour
        where a failed connection meant the in-flight event's data was lost.
        """
        self._sender = None
        self._pending_rows = 0

    def _buffer_and_maybe_flush(self, event: Event) -> None:
        """Buffer ``event`` as a row, flushing once the batch size is hit."""
        sender = self._ensure_sender()
        _insert_row(sender, event, self._config.table_name)
        self._pending_rows += 1
        if self._pending_rows >= self._config.max_batch_size:
            self._flush()

    def _flush(self) -> None:
        """Flush the underlying sender and reset the batching state."""
        if self._sender is not None:
            self._sender.flush()
        self._pending_rows = 0
        self._last_flush_monotonic = monotonic()

    def _interval_elapsed(self) -> bool:
        """Return whether ``flush_interval_seconds`` have passed since flush."""
        elapsed = monotonic() - self._last_flush_monotonic
        return elapsed >= self._config.flush_interval_seconds

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_fixed(RETRY_WAIT_SECONDS),
        retry=retry_if_exception_type(IngressError),
    )
    def _insert_with_retry(self, event: Event) -> None:
        """Buffer a row, reconnecting before each retry attempt on failure."""
        try:
            self._buffer_and_maybe_flush(event)
        except IngressError:
            self._reconnect()
            raise


def insert_event_data_into_questdb(
    connection: QuestDBConnection, event: Event, queue: Queue
) -> None:
    """Insert given event data into QuestDB using the shared, persistent connection."""
    try:
        _LOGGER.debug("Inserting event: %s", event)
        connection.insert_event(event)
    except IngressError:
        _LOGGER.exception("Failed to insert event data into QuestDB.")
    queue.task_done()
