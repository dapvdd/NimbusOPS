"""CORS regression tests (release review R-1, 2026-11-11).

Phase 3B introduced browser-called PATCH/DELETE operator endpoints
(docker enable, revoke, bootstrap-token revoke) while main.py's CORS
allow_methods still listed only GET/POST. In any cross-origin deployment
those mutations fail preflight (400) — fail-closed, but a functional
regression of the Phase 3B feature set. These tests pin the contract:
every method the frontend client actually uses must pass preflight.

Note: TestClient does not enforce CORS on normal requests, which is why
the regression was invisible to the endpoint test suites — only a real
OPTIONS preflight probe catches it.
"""

from fastapi.testclient import TestClient

from backend.app.main import app

# Methods the Phase 3B browser client actually issues (frontend/src/api/client.ts).
_PHASE3B_BROWSER_METHODS = ("GET", "POST", "PATCH", "DELETE")


def _preflight(client: TestClient, method: str, path: str):
    return client.options(
        path,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )


def test_cors_preflight_allows_phase3b_browser_methods(client):
    for method in _PHASE3B_BROWSER_METHODS:
        resp = _preflight(client, method, "/api/v1/hosts/abc")
        assert resp.status_code == 200, f"{method} preflight failed: {resp.status_code}"
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert method in resp.headers["access-control-allow-methods"]


def test_cors_preflight_still_rejects_unknown_origin(client):
    resp = _preflight(client, "POST", "/api/v1/operators/login")
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example"


def test_cors_wildcard_origin_still_rejected_at_startup():
    import importlib

    import backend.app.core.config as config_module

    original = config_module.get_settings.cache_info()
    assert original is not None  # sanity: settings cached via lru_cache
    import os

    old = os.environ.get("NIMBUSOPS_CORS_ORIGINS")
    os.environ["NIMBUSOPS_CORS_ORIGINS"] = "*"
    try:
        config_module.get_settings.cache_clear()
        import backend.app.main as main_module

        with __import__("pytest").raises(RuntimeError):
            main_module.create_app()
    finally:
        if old is None:
            os.environ.pop("NIMBUSOPS_CORS_ORIGINS", None)
        else:
            os.environ["NIMBUSOPS_CORS_ORIGINS"] = old
        config_module.get_settings.cache_clear()
    importlib.invalidate_caches()
