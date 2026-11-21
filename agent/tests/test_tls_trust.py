"""Explicit control-plane trust never disables peer or hostname checks."""
import ssl

import certifi
import pytest

from nimbusops_agent.client import Sender


def test_default_trust_remains_verified():
    sender = Sender("https://example.test", "host", "token")
    context = sender._client._transport._pool._ssl_context
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    sender.close()


def test_explicit_bundle_is_used_despite_bad_environment(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/missing/inherited-ca.pem")
    sender = Sender("https://example.test", "host", "token", ca_bundle=certifi.where())
    context = sender._client._transport._pool._ssl_context
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.cert_store_stats()["x509_ca"] > 0
    sender.close()


@pytest.mark.parametrize("value", ["relative.pem", "/missing/ca.pem", ""])
def test_invalid_bundle_fails_closed(value):
    with pytest.raises(ValueError, match="CA bundle"):
        Sender("https://example.test", "host", "token", ca_bundle=value)


def test_malformed_bundle_fails_closed(tmp_path):
    path = tmp_path / "ca.pem"
    path.write_text("not certificates")
    with pytest.raises(ValueError, match="CA bundle"):
        Sender("https://example.test", "host", "token", ca_bundle=str(path))
