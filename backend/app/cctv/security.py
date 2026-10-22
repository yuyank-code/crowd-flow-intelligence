"""Endpoint validation (SSRF guard), credential encryption, playback tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import socket
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

ALLOWED_SCHEMES = {"rtsp": {"rtsp"}, "onvif": {"http", "https"}}
BLOCKED_HOSTNAMES = {"metadata.google.internal", "metadata", "localhost"}


class EndpointRejected(ValueError):
    pass


class SecretStorageUnavailable(RuntimeError):
    pass


def _ip_blocked(ip: ipaddress._BaseAddress) -> str | None:
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if ip.is_loopback and not settings.cctv_allow_loopback:
        return "loopback addresses are not allowed"
    if ip.is_link_local:
        return "link-local addresses (incl. cloud metadata) are not allowed"
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "multicast/reserved addresses are not allowed"
    return None


def _in_allowlist(host: str, ip: ipaddress._BaseAddress) -> bool:
    if not settings.cctv_allowed_hosts:
        return True
    for entry in settings.cctv_allowed_hosts:
        if entry.lower() == host.lower():
            return True
        try:
            if "/" in entry and ip in ipaddress.ip_network(entry, strict=False):
                return True
            if ipaddress.ip_address(entry) == ip:
                return True
        except ValueError:
            continue
    return False


def resolve_safe(host: str, port: int) -> str:
    """Resolve host and return one vetted IP. Call again at connect time to limit DNS-rebinding."""
    if host.lower() in BLOCKED_HOSTNAMES and not (settings.cctv_allow_loopback and host.lower() == "localhost"):
        raise EndpointRejected("hostname is not allowed")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise EndpointRejected("hostname cannot be resolved") from exc
    chosen = None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        reason = _ip_blocked(ip)
        if reason:
            raise EndpointRejected(reason)
        if not _in_allowlist(host, ip):
            raise EndpointRejected("host is not in CCTV_ALLOWED_HOSTS")
        chosen = chosen or str(ip)
    if not chosen:
        raise EndpointRejected("hostname cannot be resolved")
    return chosen


def validate_endpoint(source_type: str, url: str) -> str:
    """Return the normalised endpoint or raise EndpointRejected."""
    schemes = ALLOWED_SCHEMES.get(source_type)
    if not schemes:
        raise EndpointRejected(f"source type '{source_type}' does not take an endpoint")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in schemes:
        raise EndpointRejected(f"scheme must be one of: {', '.join(sorted(schemes))}")
    if parts.username or parts.password:
        raise EndpointRejected("do not put credentials in the URL; use the username/password fields")
    if not parts.hostname:
        raise EndpointRejected("endpoint has no host")
    try:
        port = parts.port
    except ValueError as exc:
        raise EndpointRejected("invalid port") from exc
    resolve_safe(parts.hostname, port or (554 if parts.scheme == "rtsp" else 80))
    return url.strip()


# ---- credentials ---------------------------------------------------------
def _fernet() -> Fernet:
    if not settings.cctv_secret_key:
        raise SecretStorageUnavailable("CCTV_SECRET_KEY is not configured")
    try:
        return Fernet(settings.cctv_secret_key.encode())
    except (ValueError, TypeError) as exc:
        raise SecretStorageUnavailable("CCTV_SECRET_KEY is not a valid Fernet key") from exc


def encrypt_credentials(username: str, password: str) -> str:
    return _fernet().encrypt(json.dumps({"u": username, "p": password}).encode()).decode()


def decrypt_credentials(token: str | None) -> tuple[str, str] | None:
    if not token:
        return None
    try:
        data = json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return None
    return data["u"], data["p"]


# ---- playback tokens -----------------------------------------------------
def make_playback_token(camera_id: str, path: str, ttl: int | None = None) -> tuple[str, int]:
    if not settings.playback_signing_key:
        raise SecretStorageUnavailable("PLAYBACK_SIGNING_KEY is not configured")
    exp = int(time.time()) + (ttl or settings.playback_token_ttl_sec)
    mac = hmac.new(settings.playback_signing_key.encode(), f"{camera_id}|{path}|{exp}".encode(), hashlib.sha256).digest()
    return f"{exp}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}", exp


def verify_playback_token(camera_id: str, path: str, token: str) -> bool:
    """Helper a gateway auth hook (or nginx auth_request) can call to enforce the token."""
    try:
        exp_s, _ = token.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < time.time() or not settings.playback_signing_key:
        return False
    mac = hmac.new(settings.playback_signing_key.encode(), f"{camera_id}|{path}|{exp}".encode(), hashlib.sha256).digest()
    expected = f"{exp}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"
    return hmac.compare_digest(expected, token)
