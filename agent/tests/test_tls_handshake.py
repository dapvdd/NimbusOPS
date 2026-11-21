"""Real loopback TLS: private trust succeeds, wrong host/untrusted fail."""
import datetime
import ipaddress
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from nimbusops_agent.tls import custom_ca_context


def test_real_private_ca_and_hostname_validation(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    ca = tmp_path / "ca.pem"
    private = tmp_path / "key.pem"
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        with httpx.Client(verify=custom_ca_context(str(ca)), trust_env=False) as client:
            assert client.get(f"https://127.0.0.1:{port}").status_code == 200
            with pytest.raises(httpx.ConnectError):
                client.get(f"https://localhost:{port}")
        with httpx.Client(trust_env=False) as client:
            with pytest.raises(httpx.ConnectError):
                client.get(f"https://127.0.0.1:{port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
