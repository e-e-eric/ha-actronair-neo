"""Constants for the Actron Air Neo integration."""

DOMAIN = "actron_air_neo"

# Configuration constants
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REFRESH_INTERVAL = "refresh_interval"
CONF_SERIAL_NUMBER = "serial_number"

# Default values
DEFAULT_REFRESH_INTERVAL = 60  # seconds

# API related constants
API_URL = "https://nimbus.actronair.com.au"
API_TIMEOUT = 10  # seconds

# HVAC modes
HVAC_MODE_OFF = "OFF"
HVAC_MODE_COOL = "COOL"
HVAC_MODE_HEAT = "HEAT"
HVAC_MODE_FAN = "FAN"
HVAC_MODE_AUTO = "AUTO"

# Fan modes
FAN_LOW = "LOW"
FAN_MEDIUM = "MEDIUM"
FAN_HIGH = "HIGH"
FAN_AUTO = "AUTO"

# Temperature limits
MIN_TEMP = 16
MAX_TEMP = 32

# Device attributes
ATTR_INDOOR_TEMPERATURE = "indoor_temperature"
ATTR_INDOOR_HUMIDITY = "indoor_humidity"
ATTR_OUTDOOR_TEMPERATURE = "outdoor_temperature"
ATTR_SETPOINT_COOL = "setpoint_cool"
ATTR_SETPOINT_HEAT = "setpoint_heat"
ATTR_COMPRESSOR_STATE = "compressor_state"

# Error messages
ERROR_AUTH = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_UNKNOWN = "unknown"

# Device identifiers
DEVICE_MANUFACTURER = "ActronAir"
DEVICE_MODEL = "Neo"

# Service names
SERVICE_FORCE_UPDATE = "force_update"

# Coordinator update interval
UPDATE_INTERVAL = 60  # seconds

# Zone related constants
MAX_ZONES = 8
ATTR_ZONE_TEMP = "zone_temperature"
ATTR_ZONE_HUMIDITY = "zone_humidity"
ATTR_ZONE_TARGET_TEMP = "zone_target_temperature"

# System modes
MODE_COOL = "COOL"
MODE_HEAT = "HEAT"
MODE_AUTO = "AUTO"
MODE_FAN = "FAN"
MODE_DRY = "DRY"

# System states
STATE_ON = "ON"
STATE_OFF = "OFF"

# Other constants
QUIET_MODE = "quiet_mode"
AWAY_MODE = "away_mode"