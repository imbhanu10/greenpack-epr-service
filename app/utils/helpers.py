"""Reusable pure utility functions for the GreenPack EPR backend."""

import re
from decimal import Decimal, InvalidOperation


MONTH_REGEX = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalize_text(value: str) -> str:
    """Trim text and collapse internal whitespace."""
    return " ".join(value.strip().split())


def normalize_key(value: str) -> str:
    """Normalize text for deterministic dictionary keys."""
    return normalize_text(value).lower()


def is_valid_month(value: str) -> bool:
    """Return whether a value matches YYYY-MM format."""
    return bool(MONTH_REGEX.fullmatch(value))


def parse_decimal(value: str | int | float | Decimal) -> Decimal:
    """Convert a numeric value to Decimal."""
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("value must be a valid decimal") from exc


def require_non_negative(value: Decimal, field_name: str) -> Decimal:
    """Return a finite non-negative Decimal or raise ValueError."""
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value
