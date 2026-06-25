"""Pure data helpers for the Infolada integration."""

from __future__ import annotations

import logging
from typing import Any

from .const import DEFAULT_CURRENCY, INTERNET_USER_TYPES

_LOGGER = logging.getLogger(__name__)


def normalize_account_data(
    *,
    login: str,
    contract: dict[str, Any],
    account: dict[str, Any],
    users: list[dict[str, Any]],
) -> dict[str, Any]:
    """Map API payloads to integration data."""
    internet_users = [
        user for user in users if str(user.get("user_type", "")).lower() in INTERNET_USER_TYPES
    ]
    primary_user = internet_users[0] if internet_users else (users[0] if users else {})

    state = primary_user.get("state") if isinstance(primary_user.get("state"), dict) else {}
    internet_status = state.get("title") or state.get("name") or primary_user.get("type_definition")
    current_tariff = _extract_tariff_name(primary_user)

    return {
        "login": login,
        "contract_number": as_str(contract.get("conto_num")),
        "contract_owner": as_str(contract.get("client_name") or contract.get("client_name_io")),
        "need_pay": to_float(contract.get("need_pay")),
        "current_balance": to_float(account.get("balance")),
        "balance_currency": DEFAULT_CURRENCY,
        "bonus": to_float(account.get("bonus")),
        "traffic_mb": to_float(account.get("bytes_in_balance")),
        "can_pay": bool(account.get("can_pay")),
        "internet_login": as_str(primary_user.get("login") or primary_user.get("user_name")),
        "current_tariff": current_tariff,
        "internet_status": as_str(internet_status),
        "internet_users_count": len(internet_users),
        "internet_users": [
            {
                "user_id": user.get("user_id"),
                "login": user.get("login") or user.get("user_name"),
                "tariff": _extract_tariff_name(user) or user.get("type_definition"),
                "user_type": user.get("user_type"),
            }
            for user in internet_users
        ],
        "raw_contract": contract,
        "raw_account": account,
    }


def _extract_tariff_name(user: dict[str, Any]) -> str | None:
    """Return the human-readable tariff name from a user payload."""
    plan = user.get("plan")
    if isinstance(plan, dict):
        for key in ("plan_name_print", "plan_name", "name", "title"):
            value = as_str(plan.get(key))
            if value:
                return value
    for key in ("programm_name", "program_name", "tariff_name"):
        value = as_str(user.get(key))
        if value:
            return value
    value = as_str(user.get("type_definition"))
    if value and value.lower() not in {"пользователь интернет", "internet user"}:
        return value
    return None


def as_dict(value: Any) -> dict[str, Any]:
    """Return a dict payload or an empty dict."""
    if not isinstance(value, dict):
        return {}
    for key in ("data", "result", "payload"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    return value


def as_user_list(value: Any) -> list[dict[str, Any]]:
    """Return a list of user dicts."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("users", "items", "data"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def as_str(value: Any) -> str | None:
    """Convert a value to a trimmed string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_float(value: Any) -> float | None:
    """Convert API numeric values to float."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(" ", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            _LOGGER.debug("Failed to parse numeric value: %s", value)
            return None
    return None
