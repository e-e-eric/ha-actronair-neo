import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ActronApi, AuthenticationError, ApiError
from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class ActronDataCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, api: ActronApi, device_id: str, update_interval: int):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.api = api
        self.device_id = device_id

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            if not self.api.bearer_token:
                await self.api.authenticate()

            status = await self.api.get_ac_status(self.device_id)
            events = await self.api.get_ac_events(self.device_id)

            return self._parse_data(status, events)

        except AuthenticationError as auth_err:
            _LOGGER.error("Authentication error: %s", auth_err)
            raise UpdateFailed("Authentication failed") from auth_err
        except ApiError as api_err:
            _LOGGER.error("API error: %s", api_err)
            raise UpdateFailed("Failed to fetch data from Actron API") from api_err
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            raise UpdateFailed("Unexpected error occurred") from err

    def _parse_data(self, status: Dict[str, Any], events: Dict[str, Any]) -> Dict[str, Any]:
        parsed_data = {}
        if 'UserAirconSettings' in status:
            user_settings = status['UserAirconSettings']
            parsed_data.update({
                'isOn': user_settings.get('isOn', False),
                'mode': user_settings.get('Mode', 'OFF'),
                'fanMode': user_settings.get('FanMode', 'AUTO'),
                'temperatureSetpointCool': user_settings.get('TemperatureSetpoint_Cool_oC'),
                'temperatureSetpointHeat': user_settings.get('TemperatureSetpoint_Heat_oC'),
            })

        if 'SystemStatus_Local' in status:
            system_status = status['SystemStatus_Local']
            if 'SensorInputs' in system_status:
                sensor_inputs = system_status['SensorInputs']
                if 'SHTC1' in sensor_inputs:
                    shtc1 = sensor_inputs['SHTC1']
                    parsed_data['indoor_temperature'] = shtc1.get('Temperature_oC')
                    parsed_data['indoor_humidity'] = shtc1.get('RelativeHumidity_pc')
                if 'Battery' in sensor_inputs:
                    parsed_data['battery_level'] = sensor_inputs['Battery'].get('Level')
            if 'Outdoor' in system_status:
                parsed_data['outdoor_temperature'] = system_status['Outdoor'].get('Temperature_oC')

        parsed_data['zones'] = self._parse_zone_data(status)
        parsed_data['events'] = events.get('events', [])

        return parsed_data

    def _parse_zone_data(self, status: Dict[str, Any]) -> Dict[str, Any]:
        zones = {}
        user_settings = status.get('UserAirconSettings', {})
        remote_zone_info = status.get('RemoteZoneInfo', {})

        for i, enabled in enumerate(user_settings.get('EnabledZones', [])):
            zone_data = remote_zone_info.get(str(i), {})
            zones[str(i)] = {
                'enabled': enabled,
                'name': zone_data.get('Name', f'Zone {i}'),
                'temperature': zone_data.get('Temperature_oC'),
                'target_temperature_cool': zone_data.get('TemperatureSetpoint_Cool_oC'),
                'target_temperature_heat': zone_data.get('TemperatureSetpoint_Heat_oC'),
            }

        return zones