"""Sensors: baseline / remainder / attributed diagnostics + per-appliance entities."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfApparentPower, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import NilmCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: NilmCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        NilmBaselineSensor(coord),
        NilmRemainderSensor(coord),
        NilmAttributedSensor(coord),
        NilmEventCountSensor(coord),
    ]
    for cid, c in coord.model.clusters.items():
        if c.established:
            entities += [NilmAppliancePower(coord, cid), NilmApplianceEnergy(coord, cid)]
    async_add_entities(entities)

    @callback
    def _new_cluster(cid: int) -> None:
        async_add_entities(
            [NilmAppliancePower(coord, cid), NilmApplianceEnergy(coord, cid)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coord.signal_new_cluster, _new_cluster))


class NilmBaseEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coord: NilmCoordinator) -> None:
        self.coord = coord
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coord.entry.entry_id)},
            name="NILM Load Disaggregation",
            manufacturer="nilm-ha",
            model=coord.source,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self.coord.signal_update, self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class NilmBaselineSensor(NilmBaseEntity):
    _attr_device_class = SensorDeviceClass.APPARENT_POWER
    _attr_native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NilmCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.entry.entry_id}_baseline"
        self._attr_name = "Baseline power"

    @property
    def native_value(self) -> float | None:
        return self.coord.model.baseline


class NilmRemainderSensor(NilmBaseEntity):
    _attr_device_class = SensorDeviceClass.APPARENT_POWER
    _attr_native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NilmCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.entry.entry_id}_remainder"
        self._attr_name = "Unattributed power"

    @property
    def native_value(self) -> float | None:
        return self.coord.remainder


class NilmAttributedSensor(NilmBaseEntity):
    _attr_device_class = SensorDeviceClass.APPARENT_POWER
    _attr_native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NilmCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.entry.entry_id}_attributed"
        self._attr_name = "Attributed power"

    @property
    def native_value(self) -> float:
        return self.coord.model.attributed_power


class NilmEventCountSensor(NilmBaseEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coord: NilmCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.entry.entry_id}_events"
        self._attr_name = "Detected events"

    @property
    def native_value(self) -> int:
        return self.coord.n_events

    @property
    def extra_state_attributes(self) -> dict | None:
        return {"last_event": self.coord.last_event}


class NilmClusterEntity(NilmBaseEntity):
    def __init__(self, coord: NilmCoordinator, cid: int) -> None:
        super().__init__(coord)
        self.cid = cid

    @property
    def cluster(self):
        return self.coord.model.clusters.get(self.cid)


class NilmAppliancePower(NilmClusterEntity):
    _attr_device_class = SensorDeviceClass.APPARENT_POWER
    _attr_native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NilmCoordinator, cid: int) -> None:
        super().__init__(coord, cid)
        self._attr_unique_id = f"{coord.entry.entry_id}_c{cid}_power"
        self._attr_name = f"Appliance {cid} power"

    @property
    def native_value(self) -> float | None:
        c = self.cluster
        if c is None:
            return None
        return round(c.dp, 1) if c.is_on else 0.0

    @property
    def extra_state_attributes(self) -> dict | None:
        c = self.cluster
        if c is None:
            return None
        return {
            "step_va": round(c.dp, 1),
            "events": c.n,
            "cycles": c.cycles,
            "spike_ratio": round(c.spike_ratio, 2),
            "power_factor_estimate": c.pf,
            "last_cycle_minutes": round(c.last_duration_s / 60, 1),
        }


class NilmApplianceEnergy(NilmClusterEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, coord: NilmCoordinator, cid: int) -> None:
        super().__init__(coord, cid)
        self._attr_unique_id = f"{coord.entry.entry_id}_c{cid}_energy"
        self._attr_name = f"Appliance {cid} energy"

    @property
    def native_value(self) -> float | None:
        c = self.cluster
        return round(c.energy_kwh, 4) if c else None
