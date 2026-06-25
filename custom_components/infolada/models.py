"""Pure data helpers for the Infolada integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .const import DEFAULT_CURRENCY, INTERNET_USER_TYPES

_LOGGER = logging.getLogger(__name__)

_PLAN_DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
)
_PLAN_DATE_KEYS = (
    ("date_on", "date_off", "left_day"),
    ("dateOn", "dateOff", "leftDay"),
    ("date_start", "date_end", "days_left"),
)


def normalize_account_data(
    *,
    login: str,
    contract: dict[str, Any],
    account: dict[str, Any],
    users: list[dict[str, Any]],
    ktv: Any = None,
    telephone: Any = None,
) -> dict[str, Any]:
    """Map API payloads to integration data."""
    internet_users = [
        user for user in users if str(user.get("user_type", "")).lower() in INTERNET_USER_TYPES
    ]
    primary_user = select_primary_internet_user(users)

    state = primary_user.get("state") if isinstance(primary_user.get("state"), dict) else {}
    internet_status = state.get("title") or state.get("name") or primary_user.get("type_definition")
    current_tariff = _extract_tariff_name(primary_user)
    plan_fields = _extract_plan_fields(primary_user)
    ktv_data = _normalize_service_account(ktv, "ktv")
    telephone_data = _normalize_service_account(telephone, "telephone")

    return {
        "login": login,
        "contract_number": as_str(contract.get("conto_num")),
        "contract_owner": format_fio_initials(
            as_str(contract.get("client_name") or contract.get("client_name_io"))
        ),
        "need_pay": to_float(contract.get("need_pay")),
        "current_balance": to_float(account.get("balance")),
        "balance_currency": DEFAULT_CURRENCY,
        "bonus": to_float(account.get("bonus")),
        "traffic_mb": to_float(account.get("bytes_in_balance")),
        "can_pay": bool(account.get("can_pay")),
        "internet_login": as_str(primary_user.get("login") or primary_user.get("user_name")),
        "current_tariff": current_tariff,
        **plan_fields,
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
        **ktv_data,
        **telephone_data,
        "raw_contract": contract,
        "raw_account": account,
        "raw_ktv": ktv if isinstance(ktv, dict) else {},
        "raw_telephone": telephone if isinstance(telephone, dict) else {},
    }


def _normalize_service_account(payload: Any, prefix: str) -> dict[str, Any]:
    """Normalize KTV or telephony account payloads."""
    available_key = f"{prefix}_available"
    if isinstance(payload, list) or not payload:
        return {available_key: False}

    data = as_dict(payload)
    if not data.get("account_no"):
        return {available_key: False}

    result: dict[str, Any] = {
        available_key: True,
        f"{prefix}_account": as_str(data.get("account_no")),
        f"{prefix}_balance": to_float(data.get("balance")),
        f"{prefix}_debt": to_float(data.get("debt")),
        f"{prefix}_plan": as_str(data.get("plan")),
        f"{prefix}_plan_price": to_float(data.get("plan_price")),
        f"{prefix}_can_pay": bool(data.get("can_pay")),
    }
    return result


def format_fio_initials(name: str | None) -> str | None:
    """Return a Russian full name as initials, e.g. 'Т. А. С.'."""
    if not name:
        return None
    parts = [part for part in name.split() if part]
    if not parts:
        return None
    return " ".join(f"{part[0].upper()}." for part in parts)


def parse_infolada_datetime(value: Any) -> str | None:
    """Parse API datetime values to an ISO string."""
    text = as_str(value)
    if not text:
        return None
    for fmt in _PLAN_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    _LOGGER.debug("Failed to parse datetime value: %s", value)
    return None


def select_primary_internet_user(users: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the primary internet user from a user list payload."""
    internet_users = [
        user for user in users if str(user.get("user_type", "")).lower() in INTERNET_USER_TYPES
    ]
    return internet_users[0] if internet_users else (users[0] if users else {})


def merge_user_payload(*sources: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user payloads, keeping nested plan fields from all sources."""
    merged: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        plan = merged.get("plan") if isinstance(merged.get("plan"), dict) else {}
        incoming_plan = source.get("plan") if isinstance(source.get("plan"), dict) else {}
        merged = {**merged, **source}
        if plan or incoming_plan:
            merged["plan"] = {**plan, **incoming_plan}
    return merged


def _extract_plan_fields(user: dict[str, Any]) -> dict[str, Any]:
    """Return tariff period fields from a user or plan payload."""
    sources: list[dict[str, Any]] = []
    if isinstance(user, dict):
        sources.append(user)
        plan = user.get("plan")
        if isinstance(plan, dict):
            sources.append(plan)

    date_on: str | None = None
    date_off: str | None = None
    days_left: int | None = None

    for source in sources:
        for on_key, off_key, left_key in _PLAN_DATE_KEYS:
            if date_on is None:
                date_on = parse_infolada_datetime(source.get(on_key))
            if date_off is None:
                date_off = parse_infolada_datetime(source.get(off_key))
            if days_left is None:
                days_left = _parse_days_left(source.get(left_key))

    return {
        "tariff_date_on": date_on,
        "tariff_date_off": date_off,
        "tariff_days_left": days_left,
    }


def _parse_days_left(value: Any) -> int | None:
    """Parse the days-left counter from API payloads."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    parsed = to_float(value)
    return int(parsed) if parsed is not None else None


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
