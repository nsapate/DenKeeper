"""Configuration for the Denkeeper expense worker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    db_path: str
    timezone: ZoneInfo
    api_token: str | None
    require_api_token: bool
    allowed_scopes: frozenset[str] | None


def load_settings() -> Settings:
    """Load settings once at startup."""

    timezone_name = os.getenv("DENKEEPER_EXPENSE_TIMEZONE", "America/Los_Angeles")
    api_token = os.getenv("DENKEEPER_EXPENSE_API_TOKEN") or None
    require_api_token = _parse_bool(
        os.getenv("DENKEEPER_EXPENSE_REQUIRE_API_TOKEN"),
        default=True,
    )
    allowed_scopes = _parse_allowed_scopes(os.getenv("DENKEEPER_EXPENSE_ALLOWED_SCOPES"))

    return Settings(
        db_path=os.getenv(
            "DENKEEPER_EXPENSE_DB_PATH",
            "/app/data/expenses.sqlite3",
        ),
        timezone=ZoneInfo(timezone_name),
        api_token=api_token,
        require_api_token=require_api_token,
        allowed_scopes=allowed_scopes,
    )


def _parse_allowed_scopes(raw: str | None) -> frozenset[str] | None:
    """Parse comma-separated allowed scopes from environment."""

    if raw is None:
        return None
    values = {value.strip() for value in raw.split(",") if value.strip()}
    if not values:
        return None
    return frozenset(values)


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    """Parse an environment boolean with a secure fallback default."""

    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {raw}")
