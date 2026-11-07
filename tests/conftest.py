import pytest

from app import main


@pytest.fixture(autouse=True)
def disable_account_auth_for_legacy_api_tests(monkeypatch):
    monkeypatch.setattr(main, "AUTH_REQUIRED", False)
