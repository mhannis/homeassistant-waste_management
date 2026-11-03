"""Pickup dates with durable last-known data and adaptive refresh."""
from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
import logging
from functools import partial

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from waste_management import WMClient
from .const import CONF_ACCOUNT, CONF_SERVICES, CONF_OFFSET_DAYS, DOMAIN

_LOGGER = logging.getLogger(__name__)
RETRY_SECONDS = 3600
REQUEST_TIMEOUT = 90


def parse_pickup(value):
    """Only accept timezone-aware timestamps, never fabricate a pickup."""
    if isinstance(value, str):
        value = dt_util.parse_datetime(value)
    return value if isinstance(value, datetime) and value.tzinfo is not None else None


def next_daily_refresh(now):
    """Next local day at 00:05, respecting timezone/DST."""
    local = dt_util.as_local(now)
    return datetime.combine(local.date() + timedelta(days=1), time(0, 5), local.tzinfo)


async def async_setup_entry(hass, config, add_entities):
    data = config.data
    registry = er.async_get(hass)
    names = {}
    for service_id in data[CONF_SERVICES]:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{data[CONF_ACCOUNT]}_{service_id}")
        entry = registry.async_get(entity_id) if entity_id else None
        if entry and (entry.original_name or entry.name):
            names[service_id] = entry.original_name or entry.name
    # Existing entities must load and restore even if WM's login/service API is down.
    if len(names) != len(data[CONF_SERVICES]):
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                client = WMClient(data[CONF_USERNAME], data[CONF_PASSWORD], get_async_client(hass))
                await client.async_authenticate()
                await client.async_okta_authorize()
                for service in await client.async_get_services(data[CONF_ACCOUNT]):
                    names[service.id] = service.name
        except Exception as ex:
            _LOGGER.warning("Waste Management service discovery failed: %s", type(ex).__name__)
    add_entities([
        WasteManagementSensorEntity(hass, names.get(sid, "Waste pickup"),
                                    data[CONF_USERNAME], data[CONF_PASSWORD],
                                    data[CONF_ACCOUNT], sid, data.get(CONF_OFFSET_DAYS, 0))
        for sid in data[CONF_SERVICES]
    ], False)


class WasteManagementSensorEntity(SensorEntity, RestoreEntity):
    _attr_should_poll = False
    _attr_device_class = "timestamp"
    _attr_icon = "mdi:trash-can"
    _attr_has_entity_name = True

    def __init__(self, hass, name, username, password, account_id, service_id, offset=None):
        self.hass = hass
        self.username, self.password = username, password
        self.account_id, self.service_id = account_id, service_id
        self.offset = offset if offset is not None else 0
        self._attr_name = name
        self._attr_unique_id = f"{account_id}_{service_id}"
        self._attr_native_value = None
        self._attr_available = False
        self._last_success = None
        self._last_attempt = None
        self._last_error = None
        self._stale = True
        self._next_refresh = None
        self._cancel_refresh = None
        self._update_lock = asyncio.Lock()

    @property
    def extra_state_attributes(self):
        return {
            "data_stale": self._stale,
            "last_successful_refresh": self._last_success.isoformat() if self._last_success else None,
            "last_attempt": self._last_attempt.isoformat() if self._last_attempt else None,
            "next_refresh": self._next_refresh.isoformat() if self._next_refresh else None,
            "last_error": self._last_error,
            "pickup_date_passed": bool(self._attr_native_value and
                dt_util.as_local(self._attr_native_value).date() < dt_util.now().date()),
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        previous = await self.async_get_last_state()
        if previous:
            self._attr_native_value = parse_pickup(previous.state)
            self._last_success = parse_pickup(previous.attributes.get("last_successful_refresh"))
            self._last_attempt = parse_pickup(previous.attributes.get("last_attempt"))
            self._stale = previous.attributes.get("data_stale", True)
            self._last_error = previous.attributes.get("last_error")
        # Upgrade migration: older versions saved 'unavailable' instead of retaining dates.
        # Use HA's read-only recorder API once, only if there is no restored success.
        if self._attr_native_value is None and self._last_success is None and "recorder" in self.hass.config.components:
            try:
                from homeassistant.components.recorder.history import get_significant_states
                from homeassistant.helpers.recorder import get_instance
                history = await get_instance(self.hass).async_add_executor_job(partial(
                    get_significant_states, self.hass, dt_util.utcnow() - timedelta(days=14),
                    entity_ids=[self.entity_id]))
                for state in reversed(history.get(self.entity_id, [])):
                    value = parse_pickup(state.state)
                    if value:
                        self._attr_native_value = value
                        # Historical state changes do not prove the last live refresh time.
                        self._stale = True
                        break
            except Exception as ex:
                _LOGGER.warning("Waste Management history recovery failed: %s", type(ex).__name__)
        self._attr_available = self._attr_native_value is not None or self._last_success is not None
        if self._last_success and dt_util.as_local(self._last_success).date() == dt_util.now().date():
            self._schedule(next_daily_refresh(dt_util.utcnow()))
        else:
            retry = parse_pickup(previous.attributes.get("next_refresh")) if previous else None
            self._schedule(retry if retry and dt_util.utcnow() < retry <= dt_util.utcnow() + timedelta(hours=1)
                           else dt_util.utcnow() + timedelta(seconds=1))

    def _schedule(self, when):
        if self._cancel_refresh:
            self._cancel_refresh()
        self._next_refresh = when
        self._cancel_refresh = async_call_later(
            self.hass, max(0, (when - dt_util.utcnow()).total_seconds()), self.timer_callback)

    async def async_will_remove_from_hass(self):
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        await super().async_will_remove_from_hass()

    async def timer_callback(self, _now):
        self._cancel_refresh = None
        await self.async_update_ha_state(True)

    async def async_update(self):
        async with self._update_lock:
            self._last_attempt = dt_util.utcnow()
            stage = "authentication"
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    client = WMClient(self.username, self.password, get_async_client(self.hass))
                    await client.async_authenticate()
                    stage = "authorization"
                    await client.async_okta_authorize()
                    stage = "pickup schedule"
                    pickups = await client.async_get_service_pickup(self.account_id, self.service_id)
                    if not isinstance(pickups, (list, tuple)) or not pickups:
                        raise ValueError("Empty pickup schedule")
                    parsed = [parse_pickup(value) for value in pickups]
                    if any(value is None for value in parsed):
                        raise ValueError("Invalid pickup timestamp")
                    # Keep an overdue date if that is all the API has, rather than invent a future one.
                    future = [value for value in parsed if dt_util.as_local(value).date() >= dt_util.now().date()]
                    pickup = min(future) if future else max(parsed)
                    self._attr_native_value = pickup + timedelta(days=self.offset)
                self._last_success = dt_util.utcnow()
                self._stale = False
                self._last_error = None
                self._attr_available = True
                self._schedule(next_daily_refresh(self._last_success))
            except Exception as ex:
                status = getattr(getattr(ex, "response", None), "status_code", None)
                self._last_error = f"{stage}: {type(ex).__name__}" + (f" (HTTP {status})" if status else "")
                _LOGGER.warning("Waste Management %s; retaining last known pickup", self._last_error)
                self._stale = True
                self._attr_available = self._attr_native_value is not None
                self._schedule(dt_util.utcnow() + timedelta(seconds=RETRY_SECONDS))

