"""Constants for the QuestDB State Storage integration."""

NAME = "QuestDB State Storage (QSS)"
DOMAIN = "qss"
ISSUES_URL = "https://github.com/CM000n/qss/issues"

CONF_HOST = "host"
CONF_PORT = "port"

CONF_AUTH_KID = "auth_kid"
CONF_AUTH_D_KEY = "auth_d_key"
CONF_AUTH_X_KEY = "auth_x_key"
CONF_AUTH_Y_KEY = "auth_y_key"

RETRY_WAIT_SECONDS = 5
RETRY_ATTEMPTS = 10

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
Custom integration: {NAME}
In case of any problem, please open a new issue here:
{ISSUES_URL}
-------------------------------------------------------------------
"""
