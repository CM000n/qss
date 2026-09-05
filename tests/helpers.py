"""Shared helpers for building Home Assistant events/states in tests."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import Event, State

STATE_CHANGED_EVENT_TYPE = "state_changed"


def make_state_changed_event(
    entity_id: str,
    new_state: str | None,
    *,
    attributes: dict | None = None,
    old_state: str | None = "previous",
) -> Event:
    """Build a ``state_changed`` event for the given entity and state.

    Passing ``new_state=None`` mimics an entity removal, matching the shape
    Home Assistant uses for such events.
    """
    new = None if new_state is None else State(entity_id, new_state, attributes or {})
    old = None if old_state is None else State(entity_id, old_state)
    return Event(
        STATE_CHANGED_EVENT_TYPE,
        {ATTR_ENTITY_ID: entity_id, "old_state": old, "new_state": new},
    )
