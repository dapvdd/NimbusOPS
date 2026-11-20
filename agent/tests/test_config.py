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


def test_config_allows_empty_token_when_identity_file_exists(tmp_path):
    """Regression (RC1 recovery): a re-running agent with a stored identity must
    start without being handed an enrollment token. Only *fresh* enrollment
    needs the token; startup validation must not demand it when the identity
    file already exists."""
    state_file = tmp_path / "agent.json"
    save_identity(state_file, Identity(host_id="h1", agent_token="stored-tok"))
    cfg = Config(server_url="http://x", enrollment_token="", state_file=state_file)
    assert cfg.enrollment_token == ""


def test_config_rejects_empty_token_when_no_identity_file(tmp_path):
    """Fresh enroll (no identity file) still requires the enrollment token."""
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="", state_file=tmp_path / "nope.json")


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


# ------------------------------------------------ RC2 F01 enrollment contract

def test_config_accepts_bootstrap_token_for_fresh_enrollment(tmp_path):
    cfg = Config(
        server_url="http://x",
        enrollment_token="",
        bootstrap_token="bootstrap-secret",
        state_file=tmp_path / "absent.json",
    )
    assert cfg.bootstrap_token == "bootstrap-secret"
    assert cfg.enrollment_mode == "bootstrap"


def test_config_rejects_both_enrollment_credentials(tmp_path):
    with pytest.raises(ConfigError):
        Config(
            server_url="http://x",
            enrollment_token="legacy",
            bootstrap_token="bootstrap",
            state_file=tmp_path / "absent.json",
        )


def test_config_requires_a_credential_when_no_identity(tmp_path):
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="", state_file=tmp_path / "absent.json")


# ------------------------------------------------ RC2 F14 atomic identity file

def test_save_identity_keeps_previous_file_when_replace_fails(tmp_path, monkeypatch):
    """A failed atomic replace must never leave a truncated/partial identity."""
    import nimbusops_agent.config as cfgmod

    p = tmp_path / "agent.json"
    save_identity(p, Identity(host_id="h-old", agent_token="tok-old"))
    before = p.read_text(encoding="utf-8")

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(cfgmod.os, "replace", boom)
    with pytest.raises(OSError):
        save_identity(p, Identity(host_id="h-new", agent_token="tok-new"))

    assert p.read_text(encoding="utf-8") == before
    # No plaintext-bearing temp file may survive the failure.
    leftovers = [q for q in tmp_path.iterdir() if q.name != "agent.json"]
    assert leftovers == []


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX permission bits")
def test_save_identity_file_is_mode_0600(tmp_path):
    import stat

    p = tmp_path / "sub" / "agent.json"
    save_identity(p, Identity(host_id="h", agent_token="tok"))
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_save_identity_does_not_write_token_to_a_shared_temp_name(tmp_path):
    """Temp file must live beside the target and carry a unique name."""
    import nimbusops_agent.config as cfgmod

    p = tmp_path / "agent.json"
    seen: list[str] = []
    real_replace = cfgmod.os.replace

    def spy(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    cfgmod.os.replace = spy
    try:
        save_identity(p, Identity(host_id="h", agent_token="tok"))
    finally:
        cfgmod.os.replace = real_replace

    assert seen and seen[0] != str(p)
    assert seen[0].startswith(str(tmp_path))


# ------------------------------------------------ S4-3 environment classification

def test_config_accepts_valid_environment(tmp_path):
    """Explicit NIMBUSOPS_AGENT_ENVIRONMENT value lands on Config.environment."""
    cfg = Config(server_url="http://x", enrollment_token="t", environment="PUBLIC-CLOUD",
                 state_file=tmp_path / "a.json")
    assert cfg.environment == "PUBLIC-CLOUD"


def test_config_rejects_invalid_environment(tmp_path):
    """Unknown environment value is a ConfigError (never silently forwarded)."""
    with pytest.raises(ConfigError):
        Config(server_url="http://x", enrollment_token="t", environment="MARS",
               state_file=tmp_path / "a.json")


def test_config_environment_defaults_to_none(tmp_path):
    """Without the operator setting, environment stays None (field omitted)."""
    cfg = Config(server_url="http://x", enrollment_token="t", state_file=tmp_path / "a.json")
    assert cfg.environment is None
