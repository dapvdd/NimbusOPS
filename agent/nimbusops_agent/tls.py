"""Explicit, connection-scoped CA trust; never alter system/certifi stores."""
from pathlib import Path
import ssl


def custom_ca_context(ca_bundle: str) -> ssl.SSLContext:
    """Load a readable absolute PEM bundle, retaining certificate/host checks."""
    try:
        path = Path(ca_bundle)
        if not path.is_absolute() or not path.is_file():
            raise ValueError
        data = path.read_bytes()
        if b"PRIVATE KEY" in data:
            raise ValueError
        context = ssl.create_default_context(cafile=str(path))
        if not context.cert_store_stats()["x509_ca"]:
            raise ValueError
        return context
    except (OSError, ValueError) as exc:
        raise ValueError("invalid or unreadable CA bundle") from exc
