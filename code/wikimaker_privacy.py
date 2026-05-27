from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse


def classify_endpoint_privacy(base_url: str) -> dict[str, Any]:
    """Classify model endpoint leakage risk without making any network calls."""

    parsed = urlparse(str(base_url or "").strip())
    host = (parsed.hostname or "").strip().lower()
    scheme = (parsed.scheme or "").strip().lower()
    if not host:
        return {
            "base_url": str(base_url or "").strip(),
            "host": "",
            "classification": "missing",
            "network_scope": "unknown",
            "risk": "high",
            "allowed_by_default": False,
            "reason": "No model endpoint was configured.",
        }

    localhost_names = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    if host in localhost_names:
        return {
            "base_url": str(base_url or "").strip(),
            "host": host,
            "classification": "local",
            "network_scope": "this-machine",
            "risk": "low",
            "allowed_by_default": True,
            "reason": "Endpoint resolves to the local machine.",
        }

    try:
        ip = ip_address(host)
    except ValueError:
        ip = None

    if ip is not None and ip.is_private:
        return {
            "base_url": str(base_url or "").strip(),
            "host": host,
            "classification": "lan",
            "network_scope": "private-network",
            "risk": "medium",
            "allowed_by_default": True,
            "reason": "Endpoint is on a private network; prompts may leave this machine but stay on the LAN.",
        }

    if scheme == "file":
        return {
            "base_url": str(base_url or "").strip(),
            "host": host,
            "classification": "local",
            "network_scope": "filesystem",
            "risk": "low",
            "allowed_by_default": True,
            "reason": "Endpoint is a local file URL.",
        }

    return {
        "base_url": str(base_url or "").strip(),
        "host": host,
        "classification": "remote",
        "network_scope": "internet-or-dns",
        "risk": "high",
        "allowed_by_default": False,
        "reason": "Endpoint is not localhost or a private IP address; corpus content may leave the local network.",
    }


def browser_network_posture(*, has_active_fetches: bool = False, external_links: int = 0) -> dict[str, Any]:
    return {
        "active_outbound_fetches": bool(has_active_fetches),
        "external_reference_links": int(external_links),
        "classification": "static-local" if not has_active_fetches else "browser-networked",
        "reason": (
            "Generated browser uses embedded JSON and local artifacts only; external references are passive links."
            if not has_active_fetches
            else "Generated browser contains active network fetch code and should be reviewed before opening sensitive corpora."
        ),
    }
