"""Support for recording details."""
import asyncio
import concurrent.futures
from json import dumps
import logging
import queue
import threading
from time import sleep
from typing import Any, Callable

from questdb import ingress as qdb
import voluptuous as vol

from homeassistant.const import (
    ATTR_ENTITY_ID,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    EVENT_STATE_CHANGED,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entityfilter import (
    INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA,
    convert_include_exclude_filter,
)
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "qss"
CONF_HOST = "host"
CONF_PORT = "port"
CONNECT_RETRY_WAIT = 3

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: INCLUDE_EXCLUDE_BASE_FILTER_SCHEMA.extend(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Required(CONF_PORT): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up QSS."""
    conf = config[DOMAIN]

    db_host = conf.get(CONF_HOST)
    db_port = conf.get(CONF_PORT)
    entity_filter = convert_include_exclude_filter(conf)

    instance = QuestDB(
        hass=hass,
        host=db_host,
        port=db_port,
        entity_filter=entity_filter,
    )
    instance.async_initialize()
    instance.start()

    return await instance.async_db_ready


class QuestDB(threading.Thread):  # pylint: disable = R0902
    """A threaded QSS class."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        entity_filter: Callable[[str], bool],
    ) -> None:
        """Initialize QSS."""
        threading.Thread.__init__(self, name="QSS")

        self.hass = hass
        self.host = host
        self.port = port
        self.entity_filter = entity_filter

        self.queue: Any = queue.Queue()
        self.async_db_ready = asyncio.Future()

        self.engine: Any = None
        self.run_info: Any = None
        self.get_session = None

    @callback
    def async_initialize(self):
        """Initialize QSS."""
        self.hass.bus.async_listen(EVENT_STATE_CHANGED, self.event_listener)

    def run(self):
        """Initialize QSS and Insert data."""

        shutdown_task = object()
        hass_started = concurrent.futures.Future()

        @callback
        def register():
            """Post connection initialize."""
            self.async_db_ready.set_result(True)

            def shutdown(event):  # pylint: disable = W0613
                """Shut down the ltss."""
                if not hass_started.done():
                    hass_started.set_result(shutdown_task)
                self.queue.put(None)
                self.join()

            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown)

            if self.hass.state == CoreState.running:
                hass_started.set_result(None)
            else:

                @callback
                def notify_hass_started(event):  # pylint: disable = W0613
                    """Notify that hass has started."""
                    hass_started.set_result(None)

                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_START, notify_hass_started
                )

        self.hass.add_job(register)
        result = hass_started.result()

        if result is shutdown_task:
            _LOGGER.error(
                "Shutdown Task initialised: %s",
                result,
            )
            return

        while True:
            event = self.queue.get()

            if event is None:
                _LOGGER.error(
                    "Event Data is None: %s",
                    event,
                )
                self.queue.task_done()
                return

            tries = 1
            updated = False
            while not updated and tries <= 10:
                if tries != 1:
                    sleep(CONNECT_RETRY_WAIT)

                try:
                    with qdb.Sender(self.host, self.port) as sender:
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
                                "attributes": dumps(
                                    attrs, sort_keys=True, indent=1, default=str
                                ),
                            },
                            at=event.time_fired,
                        )

                        sender.flush()
                    updated = True

                except qdb.IngressError as err:
                    _LOGGER.error(
                        "Error during data insert: %s",
                        err,
                    )
                    tries += 1

            if not updated:
                _LOGGER.error(
                    "Error in database update. Could not save "
                    "after %d tries. Giving up",
                    tries,
                )

            self.queue.task_done()

    @callback
    def event_listener(self, event):
        """Listen for new events and put them in the process queue."""
        # Filer on entity_id
        entity_id = event.data.get(ATTR_ENTITY_ID)
        state = event.data.get("new_state")

        if (
            entity_id is not None
            and state is not None
            and state.state != STATE_UNKNOWN
            and self.entity_filter(entity_id)
        ):
            self.queue.put(event)
