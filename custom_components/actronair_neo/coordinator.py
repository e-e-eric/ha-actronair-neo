# ActronAir Neo Coordinator

from datetime import timedelta
from typing import Any, Dict, Optional, Union
import logging

from homeassistant.core import HomeAssistant # type: ignore
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed # type: ignore
from homeassistant.exceptions import ConfigEntryAuthFailed # type: ignore
from homeassistant.components.climate.const import HVACMode # type: ignore

from .api import ActronApi, AuthenticationError, ApiError
from .const import DOMAIN, MAX_ZONES

_LOGGER = logging.getLogger(__name__)

class ActronDataCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ActronAir Neo data."""

    def __init__(self, hass: HomeAssistant, api: ActronApi, device_id: str, update_interval: int, enable_zone_control: bool):
        """Initialize the data coordinator.
        
        Args:
            hass: HomeAssistant instance
            api: ActronApi instance for API communication
            device_id: Unique identifier for the device
            update_interval: Update interval in seconds
            enable_zone_control: Whether zone control is enabled
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api
        self.device_id = device_id
        self.enable_zone_control = enable_zone_control
        self.last_data = None
        self._continuous_fan = False

    @property
    def continuous_fan(self) -> bool:
        """Get continuous fan state."""
        return self._continuous_fan

    @continuous_fan.setter
    def continuous_fan(self, value: bool):
        """Set continuous fan state."""
        self._continuous_fan = value

    async def set_enable_zone_control(self, enable: bool):
        """Update the enable_zone_control status."""
        self.enable_zone_control = enable
        await self.async_request_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            if not self.api.is_api_healthy():
                _LOGGER.warning("API is not healthy, using cached data")
                return self.last_data if self.last_data else {}

            _LOGGER.debug("Fetching data for device %s", self.device_id)
            status = await self.api.get_ac_status(self.device_id)
            parsed_data = self._parse_data(status)
            self.last_data = parsed_data
            _LOGGER.debug("Parsed data: %s", parsed_data)
            return parsed_data
        except AuthenticationError as err:
            _LOGGER.error("Authentication error: %s", err)
            raise ConfigEntryAuthFailed from err
        except ApiError as err:
            _LOGGER.error("Error communicating with API: %s", err)
            if self.last_data:
                _LOGGER.warning("Using cached data due to API error")
                return self.last_data
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error occurred: %s", err)
            if self.last_data:
                _LOGGER.warning("Using cached data due to unexpected error")
                return self.last_data
            raise UpdateFailed(f"Unexpected error: {err}") from err

    def _parse_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the data from the API into a format suitable for the climate entity.
        
        Args:
            data: Raw API response data
            
        Returns:
            Dict containing parsed data including raw data for diagnostics
            
        Raises:
            UpdateFailed: If parsing fails
        """
        try:
            last_known_state = data.get("lastKnownState", {})
            user_aircon_settings = last_known_state.get("UserAirconSettings", {})
            master_info = last_known_state.get("MasterInfo", {})
            live_aircon = last_known_state.get("LiveAircon", {})
            aircon_system = last_known_state.get("AirconSystem", {})
            alerts = last_known_state.get("Alerts", {})
            
            # Get fan mode and check for continuous state using '+CONT'
            fan_mode = user_aircon_settings.get("FanMode", "")
            is_continuous = fan_mode.endswith("+CONT")

            # Strip the continuous suffix for clean fan_mode storage
            base_fan_mode = fan_mode.split('+')[0] if '+' in fan_mode else fan_mode
            base_fan_mode = base_fan_mode.split('-')[0] if '-' in base_fan_mode else base_fan_mode

            parsed_data = {
                # Store raw data for diagnostics
                "raw_data": data,
                
                "main": {
                    "is_on": user_aircon_settings.get("isOn", False),
                    "mode": user_aircon_settings.get("Mode", "OFF"),
                    "fan_mode": fan_mode,  # Store complete fan mode string
                    "fan_continuous": is_continuous,  # Explicit continuous state tracking
                    "base_fan_mode": base_fan_mode,  # Store base fan mode without suffix
                    "temp_setpoint_cool": user_aircon_settings.get("TemperatureSetpoint_Cool_oC"),
                    "temp_setpoint_heat": user_aircon_settings.get("TemperatureSetpoint_Heat_oC"),
                    "indoor_temp": master_info.get("LiveTemp_oC"),
                    "indoor_humidity": master_info.get("LiveHumidity_pc"),
                    "compressor_state": live_aircon.get("CompressorMode", "OFF"),
                    "EnabledZones": user_aircon_settings.get("EnabledZones", []),
                    "away_mode": user_aircon_settings.get("AwayMode", False),
                    "quiet_mode": user_aircon_settings.get("QuietMode", False),
                    "model": aircon_system.get("MasterWCModel"),
                    "serial_number": aircon_system.get("MasterSerial"),
                    "firmware_version": aircon_system.get("MasterWCFirmwareVersion"),
                    # Add alert statuses
                    "filter_clean_required": alerts.get("CleanFilter", False),
                    "defrosting": alerts.get("Defrosting", False),
                },
                "zones": {}
            }

            # Update continuous fan state based on actual mode
            self._continuous_fan = is_continuous
            
            _LOGGER.debug(
                "Fan mode status - Raw: %s, Base: %s, Continuous: %s",
                fan_mode,
                base_fan_mode,
                is_continuous
            )

            # Parse zone data with battery information
            remote_zone_info = last_known_state.get("RemoteZoneInfo", [])
            peripherals = aircon_system.get("Peripherals", [])

            for i, zone in enumerate(remote_zone_info):
                if i < MAX_ZONES and zone.get("NV_Exists", False):
                    zone_id = f"zone_{i+1}"
                    zone_data = {
                        "name": zone.get("NV_Title", f"Zone {i+1}"),
                        "temp": zone.get("LiveTemp_oC"),
                        "humidity": zone.get("LiveHumidity_pc"),
                        "is_enabled": parsed_data["main"]["EnabledZones"][i] if i < len(parsed_data["main"]["EnabledZones"]) else False,
                    }

                    # Find matching peripheral for battery info
                    for peripheral in peripherals:
                        if peripheral.get("ZoneAssignment", []) == [i + 1]:
                            zone_data.update({
                                "battery_level": peripheral.get("RemainingBatteryCapacity_pc"),
                                "signal_strength": peripheral.get("Signal_of3"),
                                "peripheral_type": peripheral.get("DeviceType"),
                                "last_connection": peripheral.get("LastConnectionTime"),
                                "connection_state": peripheral.get("ConnectionState"),
                            })
                            break

                    parsed_data["zones"][zone_id] = zone_data

            return parsed_data

        except Exception as e:
            _LOGGER.error("Failed to parse API response: %s", e, exc_info=True)
            raise UpdateFailed(f"Failed to parse API response: {e}") from e

    def get_zone_peripheral(self, zone_id: str) -> Union[Dict[str, Any], None]:
        """Get peripheral data for a specific zone."""
        try:
            zone_index = int(zone_id.split('_')[1]) - 1
            peripherals = self.data.get("raw_data", {}).get("AirconSystem", {}).get("Peripherals", [])

            for peripheral in peripherals:
                if peripheral.get("ZoneAssignment", []) == [zone_index + 1]:
                    return peripheral

            return None
        except (KeyError, ValueError, IndexError) as ex:
            _LOGGER.error("Error getting peripheral data for zone %s: %s", zone_id, str(ex))
            return None

    def get_zone_last_updated(self, zone_id: str) -> Optional[str]:
        """Get last update time for a specific zone."""
        try:
            peripheral_data = self.get_zone_peripheral(zone_id)
            return peripheral_data.get("LastConnectionTime") if peripheral_data else None
        except (KeyError, ValueError, IndexError) as ex:
            _LOGGER.error("Error getting last update time for zone %s: %s", zone_id, str(ex))
            return None

    async def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set HVAC mode."""
        try:
            if hvac_mode == HVACMode.OFF:
                command = self.api.create_command("OFF")
            else:
                command = self.api.create_command("CLIMATE_MODE", mode=hvac_mode)
            await self.api.send_command(self.device_id, command)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set HVAC mode to %s: %s", hvac_mode, err)
            raise

    async def set_temperature(self, temperature: float, is_cooling: bool) -> None:
        """Set temperature."""
        try:
            command = self.api.create_command("SET_TEMP", temp=temperature, is_cool=is_cooling)
            await self.api.send_command(self.device_id, command)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set %s temperature to %s: %s", 'cooling' if is_cooling else 'heating', temperature, err)
            raise

    async def set_fan_mode(self, mode: str, continuous: bool | None = None) -> None:
        """Set fan mode with proper state tracking and validation.
        
        Args:
            mode: The fan mode to set (LOW, MED, HIGH, AUTO)
            continuous: Whether to enable continuous mode. If None, maintains current state.
            
        Raises:
            ApiError: If API communication fails
            ValueError: If fan mode is invalid
        """
        try:
            # Validate mode before proceeding
            valid_modes = ["LOW", "MED", "HIGH", "AUTO"]
            base_mode = mode.upper()
            if base_mode not in valid_modes:
                _LOGGER.warning("Invalid fan mode %s, defaulting to LOW", mode)
                base_mode = "LOW"
                
            # If continuous is not specified, maintain current state from coordinator data
            if continuous is None:
                current_mode = self.data["main"].get("fan_mode", "")
                continuous = current_mode.endswith("+CONT")
                _LOGGER.debug("Maintaining current continuous state: %s", continuous)

            # Log the intended change
            _LOGGER.debug(
                "Setting fan mode - Base: %s, Continuous: %s (Current: %s)", 
                base_mode,
                continuous,
                self.data["main"].get("fan_mode")
            )

            # Send command to API
            await self.api.set_fan_mode(base_mode, continuous)
            
            # Update local state tracking
            self._continuous_fan = continuous
            
            # Force immediate refresh to update UI state
            await self.async_request_refresh()
            
            # Verify the change was successful
            new_mode = self.data["main"].get("fan_mode", "")
            _LOGGER.debug("New fan mode after update: %s", new_mode)
            
            if continuous and not new_mode.endswith("+CONT"):
                _LOGGER.warning("Continuous mode may not have been set correctly")
                
        except ApiError as err:
            _LOGGER.error(
                "API error setting fan mode %s (continuous=%s): %s", 
                mode, continuous, err
            )
            raise
        except Exception as err:
            _LOGGER.error(
                "Failed to set fan mode %s (continuous=%s): %s",
                mode, continuous, err,
                exc_info=True
            )
            raise

    async def set_zone_temperature(self, zone_id: str, temperature: float, temp_key: str) -> None:
        """Set temperature for a specific zone with comprehensive validation.
        
        Args:
            zone_id: Identifier for the zone
            temperature: Target temperature
            temp_key: Temperature key for heating or cooling
            
        Raises:
            ValueError: If zone control is disabled or validation fails
            ApiError: If API communication fails
        """
        if not self.enable_zone_control:
            _LOGGER.error("Attempted to set zone temperature while zone control is disabled")
            raise ValueError("Zone control is not enabled")

        if not self.last_data:
            _LOGGER.error("No data available for zone temperature control")
            raise ValueError("No system data available")

        zones_data = self.last_data.get("zones", {})
        zone_data = zones_data.get(zone_id)

        if not zone_data:
            _LOGGER.error("Zone %s not found in available zones: %s", zone_id, list(zones_data.keys()))
            raise ValueError(f"Zone {zone_id} not found")

        if not zone_data.get("is_enabled", False):
            _LOGGER.error("Cannot set temperature for disabled zone %s", zone_id)
            raise ValueError(f"Zone {zone_id} is not enabled")

        try:
            zone_index = int(zone_id.split('_')[1]) - 1
            command = self.api.create_command("SET_ZONE_TEMP",
                                        zone=zone_index,
                                        temp=temperature,
                                        temp_key=temp_key)
            await self.api.send_command(self.device_id, command)
            _LOGGER.info("Successfully set zone %s temperature to %s", zone_id, temperature)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set zone %s temperature to %s: %s", zone_id, temperature, err)
            raise

    async def set_zone_state(self, zone_id: Union[str, int], enable: bool) -> None:
        """Set zone state.
        Args:
            zone_id: Either a zone ID string (e.g. 'zone_1') or direct zone index (0-7)
            enable: True to enable zone, False to disable
        """
        try:
            # Handle both string zone_id and direct integer index
            if isinstance(zone_id, str):
                zone_index = int(zone_id.split('_')[1]) - 1
            else:
                zone_index = int(zone_id)  # Direct index from switch component

            current_zone_status = self.last_data["main"]["EnabledZones"]
            modified_statuses = current_zone_status.copy()

            # Ensure zone_index is within bounds
            if 0 <= zone_index < len(modified_statuses):
                modified_statuses[zone_index] = enable
                command = self.api.create_command("SET_ZONE_STATE", zones=modified_statuses)
                await self.api.send_command(self.device_id, command)
                await self.async_request_refresh()
            else:
                raise ValueError(f"Zone index {zone_index} out of range")

        except Exception as err:
            _LOGGER.error("Failed to set zone %s state to %s: %s", zone_id, 'on' if enable else 'off', err)
            raise

    async def set_climate_mode(self, mode: str) -> None:
        """Set climate mode for all zones."""
        try:
            command = self.api.create_command("CLIMATE_MODE", mode=mode)
            await self.api.send_command(self.device_id, command)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set climate mode to %s: %s", mode, err)
            raise

    async def set_away_mode(self, state: bool) -> None:
        """Set away mode."""
        try:
            await self.api.set_away_mode(state)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set away mode to %s: %s", state, err)
            raise

    async def set_quiet_mode(self, state: bool) -> None:
        """Set quiet mode."""
        try:
            await self.api.set_quiet_mode(state)
            await self.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to set quiet mode to %s: %s", state, err)
            raise

    async def force_update(self) -> None:
        """Force an immediate update of the device data."""
        await self.async_refresh()
