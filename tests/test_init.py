"""Integration tests for the QSS integration setup (``custom_components.qss``)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.entityfilter import convert_include_exclude_filter
from homeassistant.setup import async_setup_component

from custom_components.qss import CONFIG_SCHEMA, QuestDB
from custom_components.qss.const import (
    DEFAULT_FLUSH_INTERVAL_SECONDS,
    DEFAULT_MAX_BATCH_SIZE,
    DOMAIN,
)
from custom_components.qss.io import QuestDBConfig

MINIMAL_CONFIG = {DOMAIN: {"host": "localhost", "port": 9009}}


@pytest.fixture
def mock_insert() -> Callable:
    """Patch the QuestDB IO layer so tests never open a real network connection.

    Returns a mock recording every call and a ``threading.Event`` that is set
    each time the (background-threaded) integration processes a state change,
    so async tests can wait for it deterministically.
    """
    processed = threading.Event()
    calls: list[tuple] = []

    def _fake_insert(connection, event, event_queue) -> None:  # noqa: ANN001
        calls.append((connection, event))
        event_queue.task_done()
        processed.set()

    with patch(
        "custom_components.qss.insert_event_data_into_questdb", side_effect=_fake_insert
    ) as mock:
        mock.calls = calls
        mock.processed = processed
        yield mock


async def test_async_setup_returns_true_for_valid_config(
    hass: HomeAssistant,
    mock_insert: Callable,  # noqa: ARG001
) -> None:
    """Setting up qss with a minimal, valid configuration should succeed."""
    assert await async_setup_component(hass, DOMAIN, MINIMAL_CONFIG)
    await hass.async_block_till_done()


async def test_async_setup_fails_without_required_host(hass: HomeAssistant) -> None:
    """Setup must fail (return False) if the required host is missing."""
    assert not await async_setup_component(hass, DOMAIN, {DOMAIN: {"port": 9009}})


async def test_included_entity_state_change_is_forwarded(
    hass: HomeAssistant, mock_insert: Callable
) -> None:
    """A state change for an included entity should reach the IO layer."""
    config = {
        DOMAIN: {"host": "localhost", "port": 9009, "include": {"domains": ["sensor"]}}
    }
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.temperature", "21.5")
    await hass.async_block_till_done()

    assert mock_insert.processed.wait(timeout=5)
    assert len(mock_insert.calls) == 1
    connection, event = mock_insert.calls[0]
    assert event.data["entity_id"] == "sensor.temperature"
    assert connection.config.table_name == "qss"


async def test_excluded_domain_state_change_is_not_forwarded(
    hass: HomeAssistant, mock_insert: Callable
) -> None:
    """A state change for a domain that is not included must be dropped."""
    config = {
        DOMAIN: {"host": "localhost", "port": 9009, "include": {"domains": ["sensor"]}}
    }
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    hass.states.async_set("light.living_room", "on")
    await hass.async_block_till_done()

    assert not mock_insert.processed.wait(timeout=0.5)
    assert mock_insert.calls == []


async def test_custom_table_name_is_forwarded_to_io_layer(
    hass: HomeAssistant, mock_insert: Callable
) -> None:
    """A configured custom table name should be passed through to the IO layer."""
    config = {
        DOMAIN: {
            "host": "localhost",
            "port": 9009,
            "table_name": "my_custom_table",
            "include": {"domains": ["sensor"]},
        }
    }
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.temperature", "21.5")
    await hass.async_block_till_done()

    assert mock_insert.processed.wait(timeout=5)
    connection, _ = mock_insert.calls[0]
    assert connection.config.table_name == "my_custom_table"


async def test_thread_exits_cleanly_when_hass_stops_before_starting(
    hass: HomeAssistant,
) -> None:
    """If HA shuts down before finishing startup, the QSS thread must exit cleanly.

    This exercises the early-shutdown branch of ``QuestDB.run`` where
    ``EVENT_HOMEASSISTANT_STOP`` fires before ``EVENT_HOMEASSISTANT_START``.
    """
    hass.set_state(CoreState.not_running)
    instance = QuestDB(
        hass=hass,
        entity_filter=convert_include_exclude_filter(
            CONFIG_SCHEMA(MINIMAL_CONFIG)[DOMAIN]
        ),
        config=QuestDBConfig(host="localhost", port=9009, table_name="qss"),
    )
    instance.async_initialize()
    instance.start()

    assert await instance.qss_ready

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()

    instance.join(timeout=5)
    assert not instance.is_alive()


async def test_flush_on_shutdown_flushes_and_closes_sender(hass: HomeAssistant) -> None:
    """Buffered rows must be flushed and the connection closed on shutdown.

    Uses a very large ``flush_interval_seconds`` so the only flush that can
    happen is the one triggered by the shutdown path, not the idle poll.
    """
    sender = MagicMock()
    config = {
        DOMAIN: {
            "host": "localhost",
            "port": 9009,
            "flush_interval_seconds": 3600,
            "include": {"domains": ["sensor"]},
        }
    }

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        hass.states.async_set("sensor.temperature", "21.5")
        await hass.async_block_till_done()

        # Give the background thread a brief moment to pick up the queued
        # event before triggering shutdown.
        for _ in range(50):
            if sender.row.called:
                break
            await asyncio.sleep(0.1)
        assert sender.row.called
        sender.flush.assert_not_called()

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()

    sender.close.assert_called_once_with(flush=True)


async def test_idle_poll_flushes_buffered_rows_via_flush_interval(
    hass: HomeAssistant,
) -> None:
    """When idle, the background thread must flush buffered rows itself.

    Exercises the ``QUEUE_POLL_TIMEOUT`` branch of ``QuestDB.run`` by using a
    very small ``flush_interval_seconds`` and a large ``max_batch_size`` so
    the only way to flush is via the idle poll timeout, not the batch-size
    threshold.
    """
    sender = MagicMock()
    config = {
        DOMAIN: {
            "host": "localhost",
            "port": 9009,
            "flush_interval_seconds": 1,
            "max_batch_size": 1000,
            "include": {"domains": ["sensor"]},
        }
    }

    with patch("custom_components.qss.io._create_sender", return_value=sender):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        hass.states.async_set("sensor.temperature", "21.5")
        await hass.async_block_till_done()

        for _ in range(50):
            if sender.row.called:
                break
            await asyncio.sleep(0.1)
        assert sender.row.called
        sender.flush.assert_not_called()

        for _ in range(50):
            if sender.flush.called:
                break
            await asyncio.sleep(0.1)

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()

    sender.flush.assert_called_once()


def test_config_schema_requires_host_and_port() -> None:
    """A configuration missing the required host/port must be rejected."""
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({DOMAIN: {"port": 9009}})
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({DOMAIN: {"host": "localhost"}})


def test_config_schema_applies_authentication_defaults() -> None:
    """Omitting the authentication block should fall back to empty defaults."""
    config = CONFIG_SCHEMA(MINIMAL_CONFIG)

    assert config[DOMAIN]["authentication"] == {
        "ssl_check": True,
        "kid": "",
        "d_key": "",
        "x_key": "",
        "y_key": "",
    }


def test_config_schema_defaults_table_name_to_qss() -> None:
    """Omitting the table name should default to the ``qss`` table."""
    config = CONFIG_SCHEMA(MINIMAL_CONFIG)

    assert config[DOMAIN]["table_name"] == "qss"


def test_config_schema_accepts_custom_table_name() -> None:
    """A configured custom table name should be preserved as-is."""
    config = CONFIG_SCHEMA(
        {DOMAIN: {"host": "localhost", "port": 9009, "table_name": "my_table"}}
    )

    assert config[DOMAIN]["table_name"] == "my_table"


def test_config_schema_accepts_full_configuration() -> None:
    """A fully specified configuration should validate and normalize cleanly."""
    config = CONFIG_SCHEMA(
        {
            DOMAIN: {
                "host": "192.168.178.3",
                "port": 9009,
                "authentication": {
                    "ssl_check": False,
                    "kid": "my_kid",
                    "d_key": "my_d_key",
                    "x_key": "my_x_key",
                    "y_key": "my_y_key",
                },
                "include": {"domains": ["sensor"]},
                "exclude": {"entities": ["sensor.noisy"]},
            }
        }
    )

    assert config[DOMAIN]["host"] == "192.168.178.3"
    assert config[DOMAIN]["port"] == 9009
    assert config[DOMAIN]["authentication"]["kid"] == "my_kid"


def test_config_schema_defaults_batching_settings() -> None:
    """Omitting the batching settings should fall back to their defaults."""
    config = CONFIG_SCHEMA(MINIMAL_CONFIG)

    assert config[DOMAIN]["max_batch_size"] == DEFAULT_MAX_BATCH_SIZE
    assert config[DOMAIN]["flush_interval_seconds"] == DEFAULT_FLUSH_INTERVAL_SECONDS


def test_config_schema_accepts_custom_batching_settings() -> None:
    """Configured batching settings should be preserved as-is."""
    config = CONFIG_SCHEMA(
        {
            DOMAIN: {
                "host": "localhost",
                "port": 9009,
                "max_batch_size": 50,
                "flush_interval_seconds": 30,
            }
        }
    )

    assert config[DOMAIN]["max_batch_size"] == 50
    assert config[DOMAIN]["flush_interval_seconds"] == 30
