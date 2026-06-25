"""Constants for the Infolada integration."""

DOMAIN = "infolada"

CONF_LOGIN = "login"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL_HOURS = 6
MIN_SCAN_INTERVAL_HOURS = 1
MAX_SCAN_INTERVAL_HOURS = 24

BASE_URL = "https://infolada.ru"
AUTH_URL = f"{BASE_URL}/lk/auth"
API_URL = f"{BASE_URL}/api/v2"
LK_URL = f"{BASE_URL}/lk/"
PORTAL_URL = "https://start.infolada.ru/auth?tab=portal"
PAYMENT_URL = f"{BASE_URL}/lk/#/payment/i"

DEFAULT_CURRENCY = "RUB"
INTERNET_USER_TYPES = frozenset(
    {"isg", "ethernet", "homenet", "dialup", "dialup_t", "dialup_city"}
)

COOKIE_ACCESS_TOKEN = "ilkat"
