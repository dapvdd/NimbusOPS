"""Phase 6: security headers on every response (API + docs).

Pins X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and a
docs-scoped Content-Security-Policy on /api/v1/health and /api/docs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_security_headers_on_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"


def test_security_headers_on_docs(client):
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_security_headers_on_404(client):
    """Headers apply to error responses too (middleware, not route-level)."""
    r = client.get("/api/v1/no-such-endpoint")
    assert r.status_code == 404
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


def test_server_version_header_removed(client):
    """No X-Powered-By / Server detail leaks (observability hygiene)."""
    r = client.get("/api/v1/health")
    assert "x-powered-by" not in {k.lower() for k in r.headers}
