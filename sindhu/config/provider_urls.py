"""Validated provider URL defaults and overrides for CCTV adapters."""

from __future__ import annotations

import ipaddress
from typing import Any, Optional
import urllib.parse

ALLOWED_PUBLIC_API_HOSTS = frozenset(
    {
        "hatyaicityclimate.org",
        "www.hatyaicityclimate.org",
        "photo.hatyaicityclimate.org",
        "telemetry.dwr.go.th",
    }
)
ALLOWED_LEGACY_RID_HOSTS = frozenset({"119.110.213.190"})
ALLOWED_LOCAL_API_HOSTS = frozenset({"localhost", "127.0.0.1", "host.docker.internal"})

DEFAULT_HATYAI_CCTV_BASE_URL = "https://hatyaicityclimate.org"
DEFAULT_DWR_CCTV_BASE_URL = "https://telemetry.dwr.go.th/api"
DEFAULT_RID_CCTV_BASE_URL = "http://119.110.213.190"


def validate_allowed_api_base_url(
    value: Optional[str], allow_custom_hosts: bool = False
) -> Optional[str]:
    """Validate a provider URL, allowing public providers and local proxies by default."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("API base URL must be a string")
    raw = value.strip()
    if not raw or len(raw) > 2048:
        raise ValueError("API base URL must be a non-empty URL")
    if any(ord(char) < 33 for char in raw) or "\\" in raw:
        raise ValueError("API base URL contains invalid characters")

    try:
        parsed = urllib.parse.urlsplit(raw)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("API base URL is malformed") from error

    if parsed.netloc.endswith(":") or (port is not None and not 1 <= port <= 65535):
        raise ValueError("API base URL is malformed")
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "API base URL must be an absolute http(s) URL without credentials, query, or fragment"
        )

    hostname = hostname.lower().strip()
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        # กัน SSRF เสมอ แม้จะเป็น custom proxy ก็ตาม (ห้าม link-local เช่น cloud metadata, multicast, reserved)
        if ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("API base URL host is not allowed")

    scheme = parsed.scheme.lower()

    if not allow_custom_hosts:
        if hostname in ALLOWED_LOCAL_API_HOSTS:
            if scheme != "http":
                raise ValueError("Local API base URLs must use http")
        elif hostname in ALLOWED_LEGACY_RID_HOSTS:
            if scheme != "http":
                raise ValueError("Legacy RID API base URL must use http")
        elif hostname in ALLOWED_PUBLIC_API_HOSTS:
            if scheme != "https":
                raise ValueError("Public API base URLs must use https")
        else:
            raise ValueError("API base URL host is not allowed")

    return urllib.parse.urlunsplit(
        (scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
    )


def resolve_provider_base_urls(
    system_setting: Any = None,
    settings: Any = None,
) -> dict[str, str]:
    """Prefer database overrides, then environment settings, then defaults."""
    urls = {
        "hatyai": DEFAULT_HATYAI_CCTV_BASE_URL,
        "dwr": DEFAULT_DWR_CCTV_BASE_URL,
        "rid": DEFAULT_RID_CCTV_BASE_URL,
    }

    if settings is not None:
        for provider, attribute in (
            ("hatyai", "HATYAI_CCTV_API_BASE_URL"),
            ("dwr", "DWR_CCTV_API_BASE_URL"),
            ("rid", "RID_CCTV_API_BASE_URL"),
        ):
            configured = getattr(settings, attribute, None)
            if configured:
                urls[provider] = validate_allowed_api_base_url(configured)

    if system_setting is not None:
        for provider, attribute in (
            ("hatyai", "hatyai_cctv_api_base_url"),
            ("dwr", "dwr_cctv_api_base_url"),
            ("rid", "rid_cctv_api_base_url"),
        ):
            configured = getattr(system_setting, attribute, None)
            if configured:
                urls[provider] = validate_allowed_api_base_url(configured)

    return urls
