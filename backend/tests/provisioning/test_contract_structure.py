"""Provisioning contract-structure tests (Task D0.1).

Freezes the manager protocol v1 wire contract (design §15.4) as golden
request/receipt fixtures and validates the Sprint 5 OpenAPI companion's
structure. Fixtures carry only placeholder hashes — never secret material.
"""

import json
import pathlib

import pytest

SPEC_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-11-17-sprint5-openapi.json"
)
FIXTURE_PATH = (
    pathlib.Path(__file__).resolve().parent
    / "fixtures"
    / "manager_wire_v1.json"
)

REQUIRED_REQUEST_FIELDS = (
    "protocol_version",
    "job_id",
    "dispatch_id",
    "intent_hash",
    "machine_binding",
    "ownership_generation",
    "expected_credential_version",
    "expected_revocation_revision",
    "request_id",
    "journal_sequence",
)

MANAGER_MESSAGE_KINDS = (
    "STATUS",
    "ADMIT",
    "START_ACTION",
    "CONFIRM_ACTIVATION",
    "ARM_CHALLENGE",
    "CANCEL",
    "CLOSE_RESULT",
)


def load_wire_fixture(name: str) -> dict:
    """Load one named manager wire fixture.

    Shared loader for D2/D3/D4/D6/D7 tests: ``load_wire_fixture("ADMIT")``
    returns ``{"message": ..., "request": {...}, "response": {...}}``.
    """
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for entry in data["fixtures"]:
        if entry["message"] == name:
            return entry
    raise KeyError(f"unknown wire fixture: {name}")


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _resolve_ref(spec: dict, ref: str):
    target = spec
    for key in ref.lstrip("#/").split("/"):
        target = target[key.replace("~1", "/").replace("~0", "~")]
    return target


@pytest.fixture(scope="module")
def spec() -> dict:
    return _spec()


def test_openapi_spec_exists():
    assert SPEC_PATH.is_file()


def test_openapi_paths_resolve(spec):
    """Every path entry must be an object with at least one HTTP operation."""
    empty = [p for p, item in spec["paths"].items() if not isinstance(item, dict) or not item]
    assert empty == []


def test_openapi_local_refs_resolve(spec):
    """Every internal $ref must point at an existing node (mirrors the CJS floor)."""
    broken = []

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/"):
                try:
                    _resolve_ref(spec, ref)
                except (KeyError, TypeError):
                    broken.append(ref)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)
    assert broken == []


def test_manager_fixture_file_exists():
    assert FIXTURE_PATH.is_file(), "manager wire fixtures absent (create fixtures/manager_wire_v1.json)"


def test_manager_fixtures_cover_every_message_kind():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    kinds = {entry.get("message") for entry in data.get("fixtures", [])}
    missing = [k for k in MANAGER_MESSAGE_KINDS if k not in kinds]
    assert missing == [], f"fixtures missing message kinds: {missing}"


@pytest.mark.parametrize("kind", MANAGER_MESSAGE_KINDS)
def test_manager_fixture_request_fields(kind):
    """Every request carries exactly the §15.4 pinned fields."""
    fixture = load_wire_fixture(kind)
    request = fixture["request"]
    for field in REQUIRED_REQUEST_FIELDS:
        assert field in request, f"{kind} request missing {field}"


@pytest.mark.parametrize("kind", MANAGER_MESSAGE_KINDS)
def test_manager_fixture_protocol_version_is_one(kind):
    assert load_wire_fixture(kind)["request"]["protocol_version"] == 1


@pytest.mark.parametrize("kind", MANAGER_MESSAGE_KINDS)
def test_manager_fixture_response_echoes_binding_and_journal(kind):
    """Responses echo machine binding and a durable journal sequence."""
    response = load_wire_fixture(kind)["response"]
    assert response["machine_binding"] == load_wire_fixture(kind)["request"]["machine_binding"]
    assert isinstance(response["journal_sequence"], int)
    assert response["journal_sequence"] >= 1


@pytest.mark.parametrize("kind", MANAGER_MESSAGE_KINDS)
def test_manager_fixture_placeholder_hashes_are_hex64(kind):
    intent_hash = load_wire_fixture(kind)["request"]["intent_hash"]
    assert len(intent_hash) == 64
    int(intent_hash, 16)


def test_manager_fixtures_carry_no_secret_material():
    """No token/password/secret keys anywhere in the fixture file."""
    forbidden = ("token", "password", "secret", "credential_material", "private_key")
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def keys_of(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not any(word in key.lower() for word in forbidden), f"forbidden key: {key}"
                keys_of(value)
        elif isinstance(node, list):
            for value in node:
                keys_of(value)

    keys_of(data)
