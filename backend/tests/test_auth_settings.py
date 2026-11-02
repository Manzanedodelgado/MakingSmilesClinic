import pytest
from pydantic import ValidationError

from domain.config.settings import Settings


def _production_settings(**overrides):
    values = {
        "environment": "production",
        "secret_key": "x" * 40,
        "internal_api_key": "y" * 40,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_forces_secure_cookie_and_public_https_url():
    config = _production_settings()
    assert config.cookie_secure is True
    assert config.public_frontend_url.startswith("https://")


def test_non_development_rejects_http_public_url():
    with pytest.raises(ValidationError, match="PUBLIC_FRONTEND_URL debe usar HTTPS"):
        _production_settings(public_frontend_url="http://mal.example")
