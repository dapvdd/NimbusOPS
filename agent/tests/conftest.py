"""Shared fixtures for agent tests (no live server needed)."""

import pathlib

import pytest

from nimbusops_agent.config import Config, Identity


@pytest.fixture()
def cfg(tmp_path: pathlib.Path) -> Config:
    return Config(
        server_url="http://127.0.0.1:9999",  # Nothing listens here.
        enrollment_token="test-enroll-token",
        interval=30.0,
        state_file=tmp_path / "agent.json",
    )


@pytest.fixture()
def identity() -> Identity:
    return Identity(host_id="11111111-2222-3333-4444-555555555555", agent_token="tok-" + "x" * 40)
