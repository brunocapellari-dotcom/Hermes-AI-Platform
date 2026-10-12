from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

_BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata",
        "metadata.google.internal",
        "metadata.google.internal.",
    }
)


def _address_allowed(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    if address.is_loopback:
        return True
    return not (
        address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def is_secure_service_url(value: str) -> bool:
    """Allow public HTTPS and explicit loopback HTTP/HTTPS, blocking direct SSRF targets."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return False

    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.fragment:
        return False
    if not parsed.hostname:
        return False

    hostname = parsed.hostname.casefold()
    if hostname in _BLOCKED_HOSTNAMES:
        return False
    if not _address_allowed(hostname):
        return False

    if parsed.scheme == "https":
        return True
    if parsed.scheme != "http":
        return False

    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False
