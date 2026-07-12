"""Runtime coordinator: source listener -> resampler -> detector -> online model."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event as HaEvent, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .const import (
    CONF_H,
    CONF_KAPPA,
    CONF_PERIOD,
    CONF_SOURCE,
    CONF_T_SS,
    DEFAULT_H,
    DEFAULT_KAPPA,
    DEFAULT_PERIOD,
    DEFAULT_T_SS,
    SAVE_INTERVAL_MIN,
)
from .detector import EdgeDetector
from .online import OnlineNilm

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


class NilmCoordinator:
    """Owns the signal chain and the appliance model for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        d = entry.data
        self.source: str = d[CONF_SOURCE]
        self.period = float(d.get(CONF_PERIOD, DEFAULT_PERIOD))
        self.detector = EdgeDetector(
            period=self.period,
            t_ss=float(d.get(CONF_T_SS, DEFAULT_T_SS)),
            kappa=float(d.get(CONF_KAPPA, DEFAULT_KAPPA)),
            h=float(d.get(CONF_H, DEFAULT_H)),
        )
        self.model = OnlineNilm()
        self.last_value: float | None = None
        self.n_events = 0
        self.last_event: dict | None = None
        self.signal_update = f"nilm_update_{entry.entry_id}"
        self.signal_new_cluster = f"nilm_new_cluster_{entry.entry_id}"
        self._store: Store = Store(hass, STORAGE_VERSION, f"nilm.{entry.entry_id}")
        self._unsubs: list = []
        self._dirty = False

    # ---------- lifecycle ----------
    async def async_load(self) -> None:
        if data := await self._store.async_load():
            self.model = OnlineNilm.from_dict(data)
            _LOGGER.debug("Restored %d clusters", len(self.model.clusters))

    async def async_save(self, *_) -> None:
        if self._dirty:
            await self._store.async_save(self.model.to_dict())
            self._dirty = False

    @callback
    def start(self) -> None:
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.source], self._on_state))
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._tick, timedelta(seconds=self.period)))
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self.async_save, timedelta(minutes=SAVE_INTERVAL_MIN)))

    @callback
    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # ---------- signal chain ----------
    @callback
    def _on_state(self, event: HaEvent) -> None:
        st = event.data.get("new_state")
        if st is None or st.state in ("unknown", "unavailable"):
            return
        try:
            self.last_value = float(st.state)
        except ValueError:
            pass

    @callback
    def _tick(self, now) -> None:
        if self.last_value is None:
            return
        t = now.timestamp()
        self.model.observe_power(self.last_value, t)
        ev = self.detector.push(t, self.last_value)   # zero-order hold sample
        if ev:
            self.n_events += 1
            self.last_event = {
                "dp_va": round(ev.dp, 1),
                "spike_va": round(ev.spike, 1),
                "rise_s": round(ev.rise_s, 1),
                "at": now.isoformat(),
            }
            _, newly_established = self.model.feed(ev)
            self._dirty = True
            for cid in newly_established:
                async_dispatcher_send(self.hass, self.signal_new_cluster, cid)
        async_dispatcher_send(self.hass, self.signal_update)

    # ---------- values for sensors ----------
    @property
    def remainder(self) -> float | None:
        if self.last_value is None:
            return None
        base = self.model.baseline or 0.0
        return max(0.0, self.last_value - base - self.model.attributed_power)
