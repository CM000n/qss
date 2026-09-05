"""Constants for the QuestDB State Storage integration."""

NAME = "QuestDB State Storage (QSS)"
DOMAIN = "qss"
ISSUES_URL = "https://github.com/CM000n/qss/issues"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TABLE_NAME = "table_name"
CONF_MAX_BATCH_SIZE = "max_batch_size"
CONF_FLUSH_INTERVAL_SECONDS = "flush_interval_seconds"

DEFAULT_TABLE_NAME = "qss"
DEFAULT_MAX_BATCH_SIZE = 500
DEFAULT_FLUSH_INTERVAL_SECONDS = 5

CONF_AUTH = "authentication"
CONF_AUTH_SSL_CHECK = "ssl_check"
CONF_AUTH_KID = "kid"
CONF_AUTH_D_KEY = "d_key"
CONF_AUTH_X_KEY = "x_key"
CONF_AUTH_Y_KEY = "y_key"

RETRY_WAIT_SECONDS = 5
RETRY_ATTEMPTS = 150

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
Custom integration: {NAME}
In case of any problem, please open a new issue here:
{ISSUES_URL}
-------------------------------------------------------------------
"""
