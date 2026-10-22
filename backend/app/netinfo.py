"""Find the host's LAN IPv4 addresses (for telling guests which URL to open)."""

from __future__ import annotations

import contextlib
import socket


def lan_addresses() -> list[str]:
    found: set[str] = set()
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    # Connecting a UDP socket sends nothing; it only selects the outgoing interface.
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))
        found.add(s.getsockname()[0])
    return sorted(a for a in found if not a.startswith("127."))


def guest_urls(bind_host: str, port: int) -> list[str]:
    if bind_host in ("0.0.0.0", ""):
        hosts = lan_addresses() or ["127.0.0.1"]
    else:
        hosts = [bind_host]
    return [f"http://{h}:{port}" for h in hosts]
