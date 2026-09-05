"""Unit tests for ``custom_components.qss.io``."""

from __future__ import annotations

import queue
from json import loads
from unittest.mock import MagicMock, patch

import pytest
from questdb.ingress import IngressError, IngressErrorCode, Protocol

from custom_components.qss.io import (
    QuestDBAuth,
    QuestDBConfig,
    QuestDBConnection,
    _create_sender,
    _insert_row,
    insert_event_data_into_questdb,
)
from tests.helpers import make_state_changed_event

NO_AUTH_CONFIG = QuestDBConfig(host="localhost", port=9009, table_name="qss")
WITH_AUTH_CONFIG = QuestDBConfig(
    host="localhost",
    port=9009,
    table_name="qss",
    auth=QuestDBAuth(
        kid="kid", d_key="d_key", x_key="x_key", y_key="y_key", ssl_check=False
    ),
)


def _config(**overrides: object) -> QuestDBConfig:
    """Build a ``QuestDBConfig`` with test-friendly defaults.

    ``max_batch_size`` and ``flush_interval_seconds`` default to large values
    so a test only triggers a flush when it explicitly wants to exercise that
    behaviour.
    """
    defaults: dict[str, object] = {
        "host": "localhost",
        "port": 9009,
        "table_name": "qss",
        "max_batch_size": 100,
        "flush_interval_seconds": 100,
    }
    defaults.update(overrides)
    return QuestDBConfig(**defaults)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove real delays between tenacity retries so tests run instantly."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _seconds: None)


def test_create_sender_without_auth_uses_plain_tcp() -> None:
    """No configured kid results in an unauthenticated, plain TCP sender."""
    with patch("custom_components.qss.io.Sender") as sender_cls:
        _create_sender(NO_AUTH_CONFIG)

    sender_cls.assert_called_once_with(Protocol.Tcp, "localhost", 9009)


def test_create_sender_with_auth_uses_tcps_with_credentials() -> None:
    """A configured kid results in an authenticated, encrypted TCPS sender."""
    with patch("custom_components.qss.io.Sender") as sender_cls:
        _create_sender(WITH_AUTH_CONFIG)

    sender_cls.assert_called_once_with(
        Protocol.Tcps,
        "localhost",
        9009,
        username="kid",
        token="d_key",
        token_x="x_key",
        token_y="y_key",
        tls_verify=False,
    )


def test_insert_row_writes_expected_row_without_flushing() -> None:
    """The sender receives entity_id/state/attributes but is not flushed."""
    sender = MagicMock()
    event = make_state_changed_event(
        "sensor.temperature", "21.5", attributes={"unit_of_measurement": "°C"}
    )

    _insert_row(sender, event, "qss")

    sender.row.assert_called_once()
    _, kwargs = sender.row.call_args
    assert sender.row.call_args.args == ("qss",)
    assert kwargs["symbols"] == {"entity_id": "sensor.temperature"}
    assert kwargs["columns"]["state"] == "21.5"
    assert loads(kwargs["columns"]["attributes"]) == {"unit_of_measurement": "°C"}
    assert kwargs["at"] == event.time_fired
    sender.flush.assert_not_called()


def test_insert_row_uses_configured_table_name() -> None:
    """A custom table name should be forwarded to the sender as-is."""
    sender = MagicMock()
    event = make_state_changed_event("sensor.temperature", "21.5")

    _insert_row(sender, event, "custom_table")

    assert sender.row.call_args.args == ("custom_table",)


def test_connection_config_property_returns_configured_config() -> None:
    """The ``config`` property should return the config passed to the constructor."""
    config = _config()

    connection = QuestDBConnection(config)

    assert connection.config is config


def test_connection_creates_sender_lazily() -> None:
    """No connection should be created until the first event is inserted."""
    with patch("custom_components.qss.io._create_sender") as create_sender:
        QuestDBConnection(_config())
        create_sender.assert_not_called()


def test_connection_reuses_sender_across_multiple_events() -> None:
    """A single established sender must be reused across many events."""
    sender = MagicMock()
    events = [make_state_changed_event("sensor.temperature", str(i)) for i in range(3)]

    with patch(
        "custom_components.qss.io._create_sender", return_value=sender
    ) as create_sender:
        connection = QuestDBConnection(_config())
        for event in events:
            connection.insert_event(event)

    create_sender.assert_called_once_with(connection.config)
    sender.establish.assert_called_once()
    assert sender.row.call_count == 3
    sender.flush.assert_not_called()


def test_connection_flushes_once_batch_size_is_reached() -> None:
    """Reaching ``max_batch_size`` rows must trigger exactly one flush."""
    sender = MagicMock()
    events = [make_state_changed_event("sensor.temperature", str(i)) for i in range(2)]

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        connection = QuestDBConnection(_config(max_batch_size=2))
        connection.insert_event(events[0])
        sender.flush.assert_not_called()
        connection.insert_event(events[1])

    sender.flush.assert_called_once()


def test_connection_flush_if_due_flushes_after_interval_elapses() -> None:
    """A buffered row must be flushed once the flush interval has elapsed."""
    sender = MagicMock()
    event = make_state_changed_event("sensor.temperature", "21.5")

    with (
        patch("custom_components.qss.io._create_sender", return_value=sender),
        patch("custom_components.qss.io.monotonic", side_effect=[0.0, 10.0, 10.0]),
    ):
        connection = QuestDBConnection(_config(flush_interval_seconds=5))
        connection.insert_event(event)
        sender.flush.assert_not_called()
        connection.flush_if_due()

    sender.flush.assert_called_once()


def test_connection_flush_if_due_does_nothing_before_interval_elapses() -> None:
    """No flush should happen before the configured interval has elapsed."""
    sender = MagicMock()
    event = make_state_changed_event("sensor.temperature", "21.5")

    with (
        patch("custom_components.qss.io._create_sender", return_value=sender),
        patch("custom_components.qss.io.monotonic", side_effect=[0.0, 2.0]),
    ):
        connection = QuestDBConnection(_config(flush_interval_seconds=5))
        connection.insert_event(event)
        connection.flush_if_due()

    sender.flush.assert_not_called()


def test_connection_flush_if_due_does_nothing_without_pending_rows() -> None:
    """Calling ``flush_if_due`` with nothing buffered must not create a connection."""
    with patch("custom_components.qss.io._create_sender") as create_sender:
        connection = QuestDBConnection(_config())
        connection.flush_if_due()

    create_sender.assert_not_called()


def test_connection_flush_if_due_reconnects_after_ingress_error() -> None:
    """A flush failure must be logged, and the connection reset, not raised."""
    sender = MagicMock()
    sender.flush.side_effect = IngressError(IngressErrorCode.SocketError, "broken pipe")
    event = make_state_changed_event("sensor.temperature", "21.5")

    with (
        patch("custom_components.qss.io._create_sender", return_value=sender),
        patch("custom_components.qss.io.monotonic", side_effect=[0.0, 10.0]),
    ):
        connection = QuestDBConnection(_config(flush_interval_seconds=5))
        connection.insert_event(event)
        connection.flush_if_due()  # Must not raise.

    assert connection._sender is None  # noqa: SLF001


def test_connection_insert_event_retries_and_reconnects_on_transient_errors() -> None:
    """A broken connection must be dropped and recreated until the insert succeeds."""
    attempts = {"count": 0}
    good_sender = MagicMock()

    def _create_sender_side_effect(_config: QuestDBConfig) -> MagicMock:
        attempts["count"] += 1
        if attempts["count"] < 3:
            bad_sender = MagicMock()
            bad_sender.establish.side_effect = IngressError(
                IngressErrorCode.SocketError, "connection refused"
            )
            return bad_sender
        return good_sender

    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch(
        "custom_components.qss.io._create_sender",
        side_effect=_create_sender_side_effect,
    ):
        connection = QuestDBConnection(_config())
        connection.insert_event(event)

    assert attempts["count"] == 3
    good_sender.row.assert_called_once()


def test_connection_close_flushes_and_closes_sender() -> None:
    """Closing the connection must flush buffered rows and close the sender."""
    sender = MagicMock()
    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        connection = QuestDBConnection(_config())
        connection.insert_event(event)
        connection.close()

    sender.close.assert_called_once_with(flush=True)


def test_connection_close_is_noop_when_never_connected() -> None:
    """Closing a connection that never buffered anything must be a no-op."""
    with patch("custom_components.qss.io._create_sender") as create_sender:
        connection = QuestDBConnection(_config())
        connection.close()  # Must not raise.

    create_sender.assert_not_called()


def test_connection_close_logs_and_swallows_ingress_error() -> None:
    """A failure while closing must be logged, not raised."""
    sender = MagicMock()
    sender.close.side_effect = IngressError(IngressErrorCode.SocketError, "broken pipe")
    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        connection = QuestDBConnection(_config())
        connection.insert_event(event)
        connection.close()  # Must not raise.

    sender.close.assert_called_once_with(flush=True)


def test_insert_event_data_into_questdb_marks_task_done_on_success() -> None:
    """The queue task must be marked done once the insert succeeds."""
    event_queue: queue.Queue = queue.Queue()
    event_queue.put("placeholder")
    event = make_state_changed_event("sensor.temperature", "21.5")
    connection = MagicMock()

    insert_event_data_into_questdb(connection, event, event_queue)

    connection.insert_event.assert_called_once_with(event)
    event_queue.join()  # Must not block: proves task_done() was called.


def test_insert_event_data_into_questdb_marks_task_done_on_persistent_failure() -> None:
    """The queue task must be marked done even if the insert ultimately fails."""
    event_queue: queue.Queue = queue.Queue()
    event_queue.put("placeholder")
    event = make_state_changed_event("sensor.temperature", "21.5")
    connection = MagicMock()
    connection.insert_event.side_effect = IngressError(
        IngressErrorCode.SocketError, "unreachable"
    )

    insert_event_data_into_questdb(connection, event, event_queue)

    event_queue.join()  # Must not block: proves task_done() was called.
