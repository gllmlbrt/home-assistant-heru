"""Fan platform for HERU."""
import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN, HERU_FANS
from .entity import HeruEntity

_LOGGER = logging.getLogger(__name__)

# Fan step range: 1 (minimum) to 4 (maximum) for percentage mapping.
# Step 0 means off and is handled separately.
SPEED_RANGE = (1, 4)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Setup fan platform."""
    _LOGGER.debug("HERU.fan.py")
    coordinator = hass.data[DOMAIN]["coordinator"]

    fans = []
    for fan in HERU_FANS:
        fans.append(HeruFan(coordinator, fan, entry))
    async_add_devices(fans)


class HeruFan(HeruEntity, FanEntity):
    """HERU fan entity controlling ventilation speed (steps 0–4)."""

    def __init__(self, coordinator: CoordinatorEntity, idx, config_entry) -> None:
        _LOGGER.debug("HeruFan.__init__()")
        super().__init__(coordinator, idx, config_entry)
        self.coordinator = coordinator
        self.idx = idx
        self.modbus_address = self.idx["modbus_address"]
        self._attr_supported_features = FanEntityFeature.SET_SPEED
        self._attr_speed_count = len(range(SPEED_RANGE[0], SPEED_RANGE[1] + 1))
        self._update_from_coordinator()

    def _get_step(self) -> int | None:
        """Return the current fan step (0–4) from the coordinator."""
        value = self.coordinator.get_register(self.modbus_address)
        if value is None:
            return None
        return int(value)

    def _update_from_coordinator(self) -> None:
        """Sync entity state from coordinator data."""
        step = self._get_step()
        if step is None:
            self._attr_percentage = None
            self._attr_is_on = None
            return
        if step == 0:
            self._attr_percentage = 0
            self._attr_is_on = False
        else:
            self._attr_is_on = True
            self._attr_percentage = ranged_value_to_percentage(SPEED_RANGE, step)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("HeruFan._handle_coordinator_update()")
        self._update_from_coordinator()
        _LOGGER.debug("%s: step=%s percentage=%s", self._attr_name, self._get_step(), self._attr_percentage)
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the fan speed as a percentage (maps to step 0–4)."""
        if percentage == 0:
            step = 0
        else:
            step = math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))
        _LOGGER.debug("HeruFan.async_set_percentage: %s -> step %s", percentage, step)
        await self.coordinator.write_register_by_address(self.modbus_address, step)

    async def async_turn_on(self, percentage: int | None = None, **kwargs: Any) -> None:
        """Turn on the fan (set to step 1 if no percentage given)."""
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            current = self._get_step()
            # Restore to step 1 minimum if currently at 0
            target_step = current if (current is not None and current > 0) else 1
            await self.coordinator.write_register_by_address(self.modbus_address, target_step)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the fan (set step to 0)."""
        await self.coordinator.write_register_by_address(self.modbus_address, 0)
