"""Configuration validation and identity persistence tests."""

import json

import pytest

from nimbusops_agent.config import (
    Config,
    ConfigError,
    Identity,
    delete_identity,
    load_identity,
    save_identity,
)


def test_config_rejects_empty_server_url():
    with pytest.raises(ConfigError):
        Config(server_url="", enrollment_token="t")


def test_config_rejects_bad_scheme():
    with pytest.raises(ConfigError):
        Config(server_url="ftp://example", enrollment_token="t")


def test_config_rejects_empty_enrollment_token():
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="")


def test_config_rejects_interval_out_of_range():
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="t", interval=1.0)
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="t", interval=99999.0)


def test_config_accepts_valid():
    cfg = Config(server_url="https://ops.example", enrollment_token="t", interval=60.0)
    assert cfg.interval == 60.0


def test_identity_roundtrip(tmp_path):
    p = tmp_path / "sub" / "agent.json"
    ident = Identity(host_id="abc", agent_token="secret-token")
    save_identity(p, ident)
    loaded = load_identity(p)
    assert loaded == ident
    raw = json.loads(p.read_text())
    assert raw == {"host_id": "abc", "agent_token": "secret-token"}


def test_load_identity_missing_returns_none(tmp_path):
    assert load_identity(tmp_path / "nope.json") is None


def test_load_identity_corrupt_returns_none(tmp_path):
    p = tmp_path / "agent.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_identity(p) is None


def test_delete_identity(tmp_path):
    p = tmp_path / "agent.json"
    save_identity(p, Identity(host_id="a", agent_token="b"))
    delete_identity(p)
    assert not p.exists()
    delete_identity(p)  # Idempotent.
