"""Tests for the Infolada integration."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_module(name: str, path: Path):
    """Load a module file into a synthetic package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_models_module():
    """Load models.py without importing Home Assistant dependencies."""
    base = Path(__file__).resolve().parents[1] / "custom_components" / "infolada"
    package_name = "custom_components.infolada"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(base)]  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    _load_module(f"{package_name}.const", base / "const.py")
    return _load_module(f"{package_name}.models", base / "models.py")


models = _load_models_module()


class TestInfoladaNormalization(unittest.TestCase):
    """Validate account data normalization."""

    def test_normalize_account_data(self) -> None:
        """Build normalized account data from API payloads."""
        data = models.normalize_account_data(
            login="demo",
            contract={
                "conto_num": "123456",
                "client_name_io": "Иван Иванов",
                "need_pay": "150.50",
            },
            account={
                "balance": "420,75",
                "bonus": 10,
                "bytes_in_balance": 1024,
                "can_pay": True,
            },
            users=[
                {
                    "user_id": 1,
                    "user_type": "ethernet",
                    "login": "demo",
                    "type_definition": "Пользователь интернет",
                    "plan": {
                        "plan_name_print": "Интернет 100 Мбит/с",
                        "date_on": "01.07.2020 00:44:41",
                        "date_off": "03.07.2026 23:59:59",
                        "left_day": 8,
                    },
                    "state": {"title": "Включен"},
                }
            ],
        )

        self.assertEqual(data["contract_number"], "123456")
        self.assertEqual(data["contract_owner"], "И. И.")
        self.assertEqual(data["need_pay"], 150.5)
        self.assertEqual(data["current_balance"], 420.75)
        self.assertEqual(data["bonus"], 10.0)
        self.assertEqual(data["traffic_mb"], 1024.0)
        self.assertEqual(data["current_tariff"], "Интернет 100 Мбит/с")
        self.assertEqual(data["tariff_date_on"], "2020-07-01T00:44:41")
        self.assertEqual(data["tariff_date_off"], "2026-07-03T23:59:59")
        self.assertEqual(data["tariff_days_left"], 8)
        self.assertEqual(data["internet_status"], "Включен")
        self.assertEqual(data["internet_users_count"], 1)

    def test_normalize_ktv_account(self) -> None:
        """Build normalized KTV account data."""
        data = models.normalize_account_data(
            login="demo",
            contract={},
            account={},
            users=[],
            ktv={
                "account_no": "1121920356",
                "can_pay": True,
                "plan_price": 240,
                "balance": 20,
                "debt": 0,
                "plan": "Тарифный план \"Основной\" 200",
            },
            telephone=[],
        )

        self.assertTrue(data["ktv_available"])
        self.assertEqual(data["ktv_account"], "1121920356")
        self.assertEqual(data["ktv_balance"], 20.0)
        self.assertEqual(data["ktv_plan_price"], 240.0)
        self.assertFalse(data["telephone_available"])

    def test_format_fio_initials(self) -> None:
        """Convert full names to initials."""
        self.assertEqual(
            models.format_fio_initials("Терехин Анатолий Сергеевич"),
            "Т. А. С.",
        )
        self.assertEqual(models.format_fio_initials("Иван Иванов"), "И. И.")
        self.assertIsNone(models.format_fio_initials(None))

    def test_to_float(self) -> None:
        """Parse numeric strings from the API."""
        self.assertEqual(models.to_float("1 234,56"), 1234.56)
        self.assertIsNone(models.to_float("not-a-number"))

    def test_parse_infolada_datetime(self) -> None:
        """Parse API datetime strings."""
        self.assertEqual(
            models.parse_infolada_datetime("01.07.2020 00:44:41"),
            "2020-07-01T00:44:41",
        )
        self.assertEqual(
            models.parse_infolada_datetime("03.07.2026"),
            "2026-07-03T00:00:00",
        )
        self.assertIsNone(models.parse_infolada_datetime("invalid"))

    def test_merge_user_payload(self) -> None:
        """Merge list and detail user payloads."""
        merged = models.merge_user_payload(
            {
                "user_id": 1,
                "login": "demo",
                "plan": {"plan_name_print": "Интернет 100 Мбит/с"},
            },
            {
                "user_id": 1,
                "plan": {
                    "date_on": "01.07.2020 00:44:41",
                    "date_off": "03.07.2026 23:59:59",
                    "left_day": 8,
                },
            },
        )
        fields = models._extract_plan_fields(merged)
        self.assertEqual(fields["tariff_date_on"], "2020-07-01T00:44:41")
        self.assertEqual(fields["tariff_date_off"], "2026-07-03T23:59:59")
        self.assertEqual(fields["tariff_days_left"], 8)


if __name__ == "__main__":
    unittest.main()
