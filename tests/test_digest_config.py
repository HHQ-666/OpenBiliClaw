"""Digest config: defaults, round-trip, send-time normalization, API wiring."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from openbiliclaw.api.app import create_app
from openbiliclaw.api.models import ConfigUpdateIn
from openbiliclaw.config import (
    Config,
    LLMConfig,
    LLMProviderConfig,
    load_config,
    normalize_digest_send_time,
    save_config,
)

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def _make_client(monkeypatch: MonkeyPatch, tmp_path: Path) -> TestClient:
    config = Config(
        llm=LLMConfig(
            default_provider="openai",
            openai=LLMProviderConfig(api_key="sk-test", model="gpt-4o-mini"),
        ),
        data_dir=str(tmp_path),
    )
    config_path = tmp_path / "config.toml"
    save_config(config, config_path)
    monkeypatch.setenv("OPENBILICLAW_PROJECT_ROOT", str(tmp_path))
    app = create_app(memory_manager=object(), database=object(), soul_engine=object())
    return TestClient(app)


def test_digest_defaults_are_off() -> None:
    config = Config()

    assert config.digest.enabled is False
    assert config.digest.send_time == "09:00"
    assert config.digest.top_n == 10
    assert config.digest.include_delight is True
    assert config.digest.include_cognition is True
    assert config.digest.webhook_url == ""
    assert config.digest.bark_url == ""


def test_digest_round_trips(tmp_path: Path) -> None:
    config = Config()
    config.digest.enabled = True
    config.digest.send_time = "08:30"
    config.digest.top_n = 5
    config.digest.include_delight = False
    config.digest.webhook_url = "https://example.com/hook"
    config.digest.bark_url = "https://api.day.app/abc"

    config_path = tmp_path / "config.toml"
    save_config(config, config_path)
    loaded = load_config(config_path)

    assert loaded.digest == config.digest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("09:00", "09:00"),
        ("9:07", "09:07"),
        ("8:5", "08:05"),
        ("23:59", "23:59"),
        ("  07:05  ", "07:05"),
        ("", "09:00"),
        (None, "09:00"),
        ("25:00", "09:00"),
        ("12:60", "09:00"),
        ("noon", "09:00"),
    ],
)
def test_normalize_digest_send_time(raw: object, expected: str) -> None:
    assert normalize_digest_send_time(raw) == expected


def test_digest_malformed_top_n_falls_back_on_load(tmp_path: Path) -> None:
    config = Config()
    config.digest.enabled = True
    save_config(config, tmp_path / "config.toml")
    # Hand-mangle the field the same way a stray edit would.
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("top_n = 10", 'top_n = "many"'),
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert loaded.digest.enabled is True
    assert loaded.digest.top_n == 10


def test_example_config_digest_defaults_off() -> None:
    example_path = Path(__file__).parents[1] / "config.example.toml"

    with example_path.open("rb") as handle:
        example = tomllib.load(handle)

    assert example["digest"] == {
        "enabled": False,
        "send_time": "09:00",
        "top_n": 10,
        "include_delight": True,
        "include_cognition": True,
        "webhook_url": "",
        "bark_url": "",
    }


def test_config_api_exposes_and_updates_digest(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _make_client(monkeypatch, tmp_path)

    assert client.get("/api/config").json()["digest"]["enabled"] is False

    response = client.put(
        "/api/config",
        json={
            "digest": {
                "enabled": True,
                "send_time": "8:30",
                "top_n": 5,
                "bark_url": "https://api.day.app/abc",
            }
        },
    )

    assert response.status_code == 202
    digest = client.get("/api/config").json()["digest"]
    assert digest["enabled"] is True
    assert digest["send_time"] == "08:30"
    assert digest["top_n"] == 5
    assert digest["bark_url"] == "https://api.day.app/abc"
    loaded = load_config(tmp_path / "config.toml")
    assert loaded.digest.enabled is True
    assert loaded.digest.send_time == "08:30"


def test_config_api_normalizes_send_time_on_update(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _make_client(monkeypatch, tmp_path)

    response = client.put("/api/config", json={"digest": {"send_time": "9:5"}})

    assert response.status_code == 202
    assert client.get("/api/config").json()["digest"]["send_time"] == "09:05"


def test_config_api_rejects_non_integer_top_n(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _make_client(monkeypatch, tmp_path)

    response = client.put("/api/config", json={"digest": {"top_n": "many"}})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"digest": None},
        {"digest": {"enabled": None}},
        {"digest": {"webhook_url": None}},
    ],
    ids=["null-section", "null-enabled", "null-url"],
)
def test_config_update_model_rejects_explicit_digest_nulls(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ConfigUpdateIn.model_validate(payload)


def test_config_update_model_allows_omitted_digest() -> None:
    payload = ConfigUpdateIn.model_validate({"language": "en"})

    assert payload.digest is None
    assert "digest" not in payload.model_fields_set
