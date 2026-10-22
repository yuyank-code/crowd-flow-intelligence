from __future__ import annotations

import asyncio
import base64
from urllib.parse import urlsplit

from ..security import EndpointRejected, resolve_safe
from .base import CameraAdapter, Capabilities, TestResult


class RtspAdapter(CameraAdapter):
    """Checks an RTSP server with a real RTSP OPTIONS request (no HTTP HEAD, no video decoding)."""
    source_type = "rtsp"
    capabilities = Capabilities(formats=("rtsp",))

    async def test(self, endpoint, creds, timeout):
        parts = urlsplit(endpoint or "")
        port = parts.port or 554
        try:
            ip = await asyncio.to_thread(resolve_safe, parts.hostname or "", port)  # re-vetted at connect time
        except EndpointRejected as exc:
            return TestResult("error", "endpoint_rejected", str(exc))
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
            path = parts.path or "/"
            req = f"OPTIONS rtsp://{parts.hostname}:{port}{path} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: CrowdFlow\r\n"
            if creds:
                req += "Authorization: Basic " + base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode() + "\r\n"
            writer.write((req + "\r\n").encode())
            await writer.drain()
            line = (await asyncio.wait_for(reader.readline(), timeout)).decode(errors="replace").strip()
        except asyncio.TimeoutError:
            return TestResult("offline", "timeout", "no response within timeout")
        except OSError:
            return TestResult("offline", "connection_failed", "connection refused or unreachable")
        finally:
            if writer:
                writer.close()
        tokens = line.split()
        if len(tokens) < 2 or not tokens[0].startswith("RTSP/") or not tokens[1].isdigit():
            return TestResult("error", "not_rtsp", "endpoint did not answer like an RTSP server")
        code = int(tokens[1])
        if code == 200:
            return TestResult("online", None, "RTSP server responded to OPTIONS")
        if code == 401:
            return TestResult("auth_failed" if creds else "auth_required", "unauthorized",
                              "server requires valid credentials (Basic only; Digest-only cameras are not probed)")
        return TestResult("error", f"rtsp_{code}", f"unexpected RTSP status {code}")
