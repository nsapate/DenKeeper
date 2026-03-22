from expense_worker.config import load_settings

import pytest


def test_load_settings_parses_allowed_scopes(monkeypatch) -> None:
    monkeypatch.setenv("DENKEEPER_EXPENSE_ALLOWED_SCOPES", "the-den, travel-2026 ,  ")

    settings = load_settings()

    assert settings.allowed_scopes == frozenset({"the-den", "travel-2026"})


def test_load_settings_empty_allowed_scopes_is_none(monkeypatch) -> None:
    monkeypatch.setenv("DENKEEPER_EXPENSE_ALLOWED_SCOPES", "  ,  ")

    settings = load_settings()

    assert settings.allowed_scopes is None


def test_load_settings_requires_api_token_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DENKEEPER_EXPENSE_REQUIRE_API_TOKEN", raising=False)

    settings = load_settings()

    assert settings.require_api_token is True


def test_load_settings_allows_disabling_required_api_token(monkeypatch) -> None:
    monkeypatch.setenv("DENKEEPER_EXPENSE_REQUIRE_API_TOKEN", "false")

    settings = load_settings()

    assert settings.require_api_token is False


def test_load_settings_rejects_invalid_require_api_token_value(monkeypatch) -> None:
    monkeypatch.setenv("DENKEEPER_EXPENSE_REQUIRE_API_TOKEN", "not-a-bool")

    with pytest.raises(ValueError, match="Invalid boolean value"):
        load_settings()
