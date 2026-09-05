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
    _create_sender,
    _insert_row,
    _retry_data_insertion,
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


def test_insert_row_writes_expected_row_and_flushes() -> None:
    """The sender receives entity_id/state/attributes and is flushed."""
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
    sender.flush.assert_called_once()


def test_insert_row_uses_configured_table_name() -> None:
    """A custom table name should be forwarded to the sender as-is."""
    sender = MagicMock()
    event = make_state_changed_event("sensor.temperature", "21.5")

    _insert_row(sender, event, "custom_table")

    assert sender.row.call_args.args == ("custom_table",)


def test_retry_data_insertion_succeeds_on_first_try() -> None:
    """A working sender should insert the row without any retries."""
    sender = MagicMock()
    sender.__enter__.return_value = sender
    sender.__exit__.return_value = False
    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        _retry_data_insertion(NO_AUTH_CONFIG, event)

    sender.row.assert_called_once()
    sender.flush.assert_called_once()


def test_retry_data_insertion_retries_transient_errors_until_success() -> None:
    """Transient ``IngressError``s should be retried until the insert succeeds."""
    attempts = {"count": 0}

    class _FlakySender:
        """Fails the first two connection attempts, then succeeds."""

        def __enter__(self) -> MagicMock:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise IngressError(IngressErrorCode.SocketError, "connection refused")
            return MagicMock()

        def __exit__(self, *_exc_info: object) -> bool:
            return False

    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch(
        "custom_components.qss.io._create_sender",
        side_effect=lambda *a, **k: _FlakySender(),  # noqa: ARG005
    ):
        _retry_data_insertion(NO_AUTH_CONFIG, event)

    assert attempts["count"] == 3


def test_insert_event_data_into_questdb_marks_task_done_on_success() -> None:
    """The queue task must be marked done once the insert succeeds."""
    event_queue: queue.Queue = queue.Queue()
    event_queue.put("placeholder")
    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch("custom_components.qss.io._retry_data_insertion"):
        insert_event_data_into_questdb(NO_AUTH_CONFIG, event, event_queue)

    event_queue.join()  # Must not block: proves task_done() was called.


def test_insert_event_data_into_questdb_marks_task_done_on_persistent_failure() -> None:
    """The queue task must be marked done even if the insert ultimately fails."""
    event_queue: queue.Queue = queue.Queue()
    event_queue.put("placeholder")
    event = make_state_changed_event("sensor.temperature", "21.5")

    with patch(
        "custom_components.qss.io._retry_data_insertion",
        side_effect=IngressError(IngressErrorCode.SocketError, "unreachable"),
    ):
        insert_event_data_into_questdb(NO_AUTH_CONFIG, event, event_queue)

    event_queue.join()  # Must not block: proves task_done() was called.
