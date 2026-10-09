from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def is_secure_service_url(value: str) -> bool:
    """Allow HTTPS everywhere and plain HTTP only on the local loopback interface."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return False

    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.scheme == "https":
        return bool(parsed.hostname)
    if parsed.scheme != "http" or not parsed.hostname:
        return False

    hostname = parsed.hostname.casefold()
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
