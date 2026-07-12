"""Constants for the NILM integration."""

DOMAIN = "nilm"
PLATFORMS = ["sensor"]

CONF_SOURCE = "source_entity"
CONF_PERIOD = "period"
CONF_T_SS = "t_ss"
CONF_KAPPA = "kappa"
CONF_H = "h"

DEFAULT_PERIOD = 5.0
DEFAULT_T_SS = 25.0
DEFAULT_KAPPA = 15.0
DEFAULT_H = 30.0

MIN_EVENTS_ESTABLISHED = 4     # events before a cluster gets entities
SAVE_INTERVAL_MIN = 15
