from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

from ..security import EndpointRejected, resolve_safe
from .base import CameraAdapter, Capabilities, TestResult

SOAP = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        '<s:Body><GetSystemDateAndTime xmlns="http://www.onvif.org/ver10/device/wsdl"/></s:Body></s:Envelope>')


class OnvifAdapter(CameraAdapter):
    """Reachability/identity check via the unauthenticated ONVIF GetSystemDateAndTime call.

    PTZ, snapshot and discovery are deliberately NOT advertised: they are not implemented or verified
    against a real device yet, so the API and UI treat them as unsupported.
    """
    source_type = "onvif"
    capabilities = Capabilities(formats=("rtsp",))

    async def test(self, endpoint, creds, timeout):
        parts = urlsplit(endpoint or "")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            ip = await asyncio.to_thread(resolve_safe, parts.hostname or "", port)
        except EndpointRejected as exc:
            return TestResult("error", "endpoint_rejected", str(exc))
        host = f"[{ip}]" if ":" in ip else ip
        url = parts._replace(netloc=f"{host}:{port}").geturl()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=settings.cctv_tls_verify) as client:
                resp = await client.post(url, content=SOAP, headers={"Content-Type": "application/soap+xml; charset=utf-8", "Host": parts.netloc})
        except httpx.TimeoutException:
            return TestResult("offline", "timeout", "no response within timeout")
        except httpx.HTTPError:
            return TestResult("offline", "connection_failed", "connection refused or unreachable")
        if resp.status_code == 200 and b"GetSystemDateAndTimeResponse" in resp.content:
            return TestResult("online", None, "ONVIF device service responded")
        if resp.status_code in (401, 403):
            return TestResult("auth_required", "unauthorized", "device requires authentication")
        if resp.status_code == 200:
            return TestResult("error", "not_onvif", "endpoint answered but not as an ONVIF device service")
        return TestResult("error", f"http_{resp.status_code}", f"unexpected HTTP status {resp.status_code}")
