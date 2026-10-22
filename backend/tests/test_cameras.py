import http.server
import json
import socketserver
import threading

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.cctv import repository as repo
from app.cctv import streams
from app.cctv.security import EndpointRejected, validate_endpoint, verify_playback_token
from app.core.config import settings
from app.main import app

KEY = {"X-API-Key": "test-operator-key"}


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "test-operator-key")
    monkeypatch.setattr(settings, "cctv_secret_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "playback_signing_key", "sign-me")
    monkeypatch.setattr(settings, "cctv_allow_loopback", True)   # mock servers live on 127.0.0.1
    monkeypatch.setattr(settings, "cctv_timeout_sec", 2.0)
    streams.active().clear()
    yield
    streams.active().clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
        for item in c.get("/api/cctv/sources").json()["items"]:
            if item.get("origin") == "registered":
                c.delete(f"/api/cctv/sources/{item['id']}", headers=KEY)


# ---- mock servers -----------------------------------------------------------
class _Tcp(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture
def rtsp_server():
    seen = {}

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            lines = []
            while (l := self.rfile.readline().strip()):
                lines.append(l.decode())
            seen["request"] = lines
            if any(l.lower().startswith("authorization") for l in lines) or not seen.get("need_auth"):
                self.wfile.write(b"RTSP/1.0 200 OK\r\nCSeq: 1\r\nPublic: OPTIONS, DESCRIBE\r\n\r\n")
            else:
                self.wfile.write(b"RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\n\r\n")

    srv, port = _serve(_Tcp(("127.0.0.1", 0), H))
    yield port, seen
    srv.shutdown(); srv.server_close()


@pytest.fixture
def http_server():
    routes = {"onvif": (200, b"<s:Envelope><GetSystemDateAndTimeResponse/></s:Envelope>"), "hls": (200, b"#EXTM3U")}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            code, body = routes["onvif"]
            self.send_response(code); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            code, body = routes["hls"] if self.path.startswith("/cam1/index.m3u8") else (404, b"")
            self.send_response(code); self.end_headers(); self.wfile.write(body)

    srv, port = _serve(_Tcp(("127.0.0.1", 0), H))
    yield port, routes
    srv.shutdown(); srv.server_close()


def add(client, **kw):
    body = {"name": "Gate E cam", "source_type": "rtsp", "zone_id": "gate-e", **kw}
    return client.post("/api/cctv/sources", json=body, headers=KEY)


# ---- auth + validation -----------------------------------------------------
def test_reads_are_open_but_mutations_need_operator_key(client):
    assert client.get("/api/cctv/sources").status_code == 200
    body = {"name": "x", "source_type": "rtsp", "endpoint": "rtsp://127.0.0.1:1/s"}
    assert client.post("/api/cctv/sources", json=body).status_code == 401
    assert client.post("/api/cctv/sources", json=body, headers={"X-API-Key": "wrong"}).status_code == 401


def test_mutations_fail_closed_when_no_operator_key_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "operator_api_key", "")
    r = client.post("/api/cctv/sources", json={"name": "x", "source_type": "usb", "device_label": "c"}, headers=KEY)
    assert r.status_code == 503


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1/", "rtsp://user:pw@127.0.0.1/s",
    "rtsp://169.254.169.254/latest", "rtsp://metadata.google.internal/", "rtsp://[fe80::1]/s", "rtsp://",
])
def test_ssrf_guard_rejects_bad_endpoints(url, monkeypatch):
    monkeypatch.setattr(settings, "cctv_allow_loopback", False)
    with pytest.raises(EndpointRejected):
        validate_endpoint("rtsp", url)


def test_private_lan_addresses_are_allowed_and_allowlist_is_enforced(monkeypatch):
    assert validate_endpoint("rtsp", "rtsp://192.168.1.50:554/stream1")
    monkeypatch.setattr(settings, "cctv_allowed_hosts", ["10.0.0.0/8"])
    with pytest.raises(EndpointRejected):
        validate_endpoint("rtsp", "rtsp://192.168.1.50/stream1")
    assert validate_endpoint("rtsp", "rtsp://10.1.2.3/stream1")


def test_schema_validation(client):
    assert add(client, source_type="rtsp").status_code == 422                       # no endpoint
    assert add(client, source_type="usb", endpoint="rtsp://127.0.0.1/s", device_label="c").status_code == 422
    assert add(client, source_type="usb").status_code == 422                        # no device_label
    assert add(client, endpoint="rtsp://127.0.0.1:1/s", username="u").status_code == 422   # half a credential
    assert add(client, endpoint="rtsp://127.0.0.1:1/s", name="").status_code == 422
    assert add(client, endpoint="http://127.0.0.1:1/s").status_code == 422          # wrong scheme for rtsp


def test_credentials_need_secret_key_and_never_leak(client, rtsp_server, monkeypatch):
    port, _ = rtsp_server
    ep = f"rtsp://127.0.0.1:{port}/live"
    ok = add(client, endpoint=ep, username="admin", password="hunter2-secret")
    assert ok.status_code == 201
    cam = ok.json()
    assert cam["has_credentials"] is True and "hunter2" not in json.dumps(cam)
    assert "hunter2" not in client.get("/api/cctv/sources").text
    assert "hunter2" not in client.get(f"/api/cctv/sources/{cam['id']}").text
    assert cam["endpoint_host"] == f"127.0.0.1:{port}" and "live" not in json.dumps(cam)
    monkeypatch.setattr(settings, "cctv_secret_key", "")
    assert add(client, endpoint=ep, username="a", password="b").status_code == 422


# ---- registration / CRUD ---------------------------------------------------
def test_register_list_update_delete_metadata_only_usb_camera(client):
    r = client.post("/api/cctv/sources", json={"name": "Lobby USB", "source_type": "usb", "device_label": "Logitech C920", "zone_id": "j-c"}, headers=KEY)
    assert r.status_code == 201
    cam = r.json()
    assert cam["status"] == "unknown" and cam["capabilities"]["preview"] is False and cam["analytics"] == "not-implemented"
    assert any(i["id"] == cam["id"] for i in client.get("/api/cctv/sources").json()["items"])
    assert client.patch(f"/api/cctv/sources/{cam['id']}", json={"name": "Lobby cam", "zone_id": "stage"}, headers=KEY).json()["name"] == "Lobby cam"
    t = client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()
    assert t["status"] == "agent_offline" and t["last_error_code"] == "local_agent_required"   # honest: no agent
    assert client.delete(f"/api/cctv/sources/{cam['id']}", headers=KEY).status_code == 204
    assert client.get(f"/api/cctv/sources/{cam['id']}").status_code == 404
    assert client.patch("/api/cctv/sources/nope", json={"name": "x"}, headers=KEY).status_code == 404


def test_config_sources_still_listed_and_readonly(client, monkeypatch):
    from app.cctv import service
    monkeypatch.setattr(service.settings, "cctv_sources_json", '[{"id":"cam-1","name":"Gate E","zone":"gate-e"}]')
    items = client.get("/api/cctv/sources").json()["items"]
    cfg = next(i for i in items if i["id"] == "cam-1")
    assert cfg["origin"] == "config" and cfg["configured"] is False and cfg["access_policy"] == "operator-configured"
    assert client.delete("/api/cctv/sources/cam-1", headers=KEY).status_code == 404   # not DB-managed


# ---- real protocol checks --------------------------------------------------
def test_rtsp_online_offline_and_auth_states(client, rtsp_server):
    port, seen = rtsp_server
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{port}/live").json()
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["status"] == "online"
    assert seen["request"][0].startswith("OPTIONS rtsp://")
    got = client.get(f"/api/cctv/sources/{cam['id']}/health").json()
    assert got["status"] == "online" and got["last_seen_at"] and got["probed"] is False

    seen["need_auth"] = True
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["status"] == "auth_required"
    authed = add(client, endpoint=f"rtsp://127.0.0.1:{port}/live", username="u", password="p").json()
    assert client.post(f"/api/cctv/sources/{authed['id']}/test", headers=KEY).json()["status"] == "online"

    dead = add(client, endpoint="rtsp://127.0.0.1:9/live").json()      # nothing listens on port 9
    r = client.post(f"/api/cctv/sources/{dead['id']}/test", headers=KEY).json()
    assert r["status"] == "offline" and r["last_error_code"] in {"connection_failed", "timeout"}


def test_non_rtsp_listener_is_reported_as_error(client, http_server):
    port, _ = http_server
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{port}/x").json()
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["status"] in {"error", "offline"}


def test_onvif_reachability(client, http_server):
    port, routes = http_server
    cam = add(client, source_type="onvif", endpoint=f"http://127.0.0.1:{port}/onvif/device_service").json()
    assert cam["capabilities"]["ptz"] is False and cam["capabilities"]["discovery"] is False
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["status"] == "online"
    routes["onvif"] = (401, b"")
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["status"] == "auth_required"
    routes["onvif"] = (200, b"<html>router admin</html>")
    assert client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY).json()["last_error_code"] == "not_onvif"


# ---- streams / playback ----------------------------------------------------
def test_stream_lifecycle_requires_gateway_and_serving_manifest(client, rtsp_server, http_server, monkeypatch):
    rport, _ = rtsp_server
    gport, routes = http_server
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{rport}/live", playback_path="cam1").json()
    url = f"/api/cctv/sources/{cam['id']}"

    r = client.post(url + "/stream/start", headers=KEY)
    assert r.status_code == 409 and "media_gateway_not_configured" in r.json()["detail"]

    monkeypatch.setattr(settings, "media_gateway_base_url", f"http://127.0.0.1:{gport}")
    routes["hls"] = (404, b"")
    r = client.post(url + "/stream/start", headers=KEY)
    assert r.status_code == 409 and "gateway_stream_unavailable" in r.json()["detail"]      # never claims 'live' falsely
    assert client.get(url + "/playback", headers=KEY).status_code == 409                   # no active stream

    routes["hls"] = (200, b"#EXTM3U")
    assert client.post(url + "/stream/start", headers=KEY).json()["stream_active"] is True
    pb = client.get(url + "/playback", headers=KEY).json()
    assert pb["format"] == "hls" and "index.m3u8?token=" in pb["url"] and "rtsp://" not in pb["url"]
    token = pb["url"].split("token=")[1]
    assert verify_playback_token(cam["id"], "cam1", token) and not verify_playback_token(cam["id"], "other", token)
    assert not verify_playback_token(cam["id"], "cam1", "1.AAAA")
    assert client.get(url + "/playback").status_code == 401                                 # key required

    assert client.post(url + "/stream/stop", headers=KEY).json()["stream_active"] is False


def test_stream_start_refused_when_camera_offline_or_usb(client, monkeypatch, http_server):
    gport, _ = http_server
    monkeypatch.setattr(settings, "media_gateway_base_url", f"http://127.0.0.1:{gport}")
    dead = add(client, endpoint="rtsp://127.0.0.1:9/x", playback_path="cam1").json()
    assert client.post(f"/api/cctv/sources/{dead['id']}/stream/start", headers=KEY).status_code == 409
    usb = client.post("/api/cctv/sources", json={"name": "u", "source_type": "usb", "device_label": "c"}, headers=KEY).json()
    assert "local_agent_required" in client.post(f"/api/cctv/sources/{usb['id']}/stream/start", headers=KEY).json()["detail"]


def test_session_cap_and_delete_stops_session(client, rtsp_server, http_server, monkeypatch):
    rport, _ = rtsp_server
    gport, _ = http_server
    monkeypatch.setattr(settings, "media_gateway_base_url", f"http://127.0.0.1:{gport}")
    monkeypatch.setattr(settings, "cctv_max_sessions", 1)
    a = add(client, endpoint=f"rtsp://127.0.0.1:{rport}/a", playback_path="cam1").json()
    b = add(client, endpoint=f"rtsp://127.0.0.1:{rport}/b", playback_path="cam1").json()
    assert client.post(f"/api/cctv/sources/{a['id']}/stream/start", headers=KEY).status_code == 200
    assert client.post(f"/api/cctv/sources/{b['id']}/stream/start", headers=KEY).status_code == 429
    client.delete(f"/api/cctv/sources/{a['id']}", headers=KEY)
    assert a["id"] not in streams.active()


def test_playback_fails_closed_without_signing_key(client, rtsp_server, http_server, monkeypatch):
    rport, _ = rtsp_server
    gport, _ = http_server
    monkeypatch.setattr(settings, "media_gateway_base_url", f"http://127.0.0.1:{gport}")
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{rport}/a", playback_path="cam1").json()
    client.post(f"/api/cctv/sources/{cam['id']}/stream/start", headers=KEY)
    monkeypatch.setattr(settings, "playback_signing_key", "")
    assert client.get(f"/api/cctv/sources/{cam['id']}/playback", headers=KEY).status_code == 503


# ---- gated controls + audit ------------------------------------------------
def test_ptz_and_snapshot_are_unsupported_not_faked(client, http_server):
    port, _ = http_server
    cam = add(client, source_type="onvif", endpoint=f"http://127.0.0.1:{port}/onvif/device_service").json()
    ptz = client.post(f"/api/cctv/sources/{cam['id']}/ptz", json={"action": "move", "pan": 0.5}, headers=KEY)
    assert ptz.status_code == 409 and "capability_unsupported" in ptz.json()["detail"]
    assert client.post(f"/api/cctv/sources/{cam['id']}/ptz", json={"action": "move", "pan": 5}, headers=KEY).status_code == 422
    assert client.post(f"/api/cctv/sources/{cam['id']}/ptz", json={"action": "move"}).status_code == 401
    assert client.post(f"/api/cctv/sources/{cam['id']}/snapshot", headers=KEY).status_code == 409


def test_operator_actions_are_audited(client, rtsp_server):
    port, _ = rtsp_server
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{port}/a").json()
    client.post(f"/api/cctv/sources/{cam['id']}/test", headers=KEY)
    client.post(f"/api/cctv/sources/{cam['id']}/ptz", json={"action": "stop"}, headers=KEY)
    actions = [a["action"] for a in client.get(f"/api/cctv/sources/{cam['id']}").json()["audit"]]
    assert {"create", "test", "ptz_attempt"} <= set(actions)


# ---- media gateway auth hook ------------------------------------------------
def _hook(client, **over):
    body = {"action": "read", "protocol": "hls", "path": "cam1", "query": ""} | over
    return client.post("/api/cctv/gateway/auth", json=body)


def test_gateway_hook_allows_only_valid_hls_read_for_active_stream(client, rtsp_server, monkeypatch):
    from app.cctv.security import make_playback_token
    port, _ = rtsp_server
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{port}/a", playback_path="cam1").json()
    tok, _exp = make_playback_token(cam["id"], "cam1")
    q = f"token={tok}"
    assert _hook(client, query=q).status_code == 401                 # no active stream yet: no access
    streams.active()[cam["id"]] = streams.StreamSession(cam["id"], "cam1")
    assert _hook(client, query=q).status_code == 200
    assert _hook(client, query="").status_code == 401                # no token
    assert _hook(client, query="token=1.bad").status_code == 401     # forged
    assert _hook(client, query=q, path="other").status_code == 401   # token is bound to its path
    for bad in ({"action": "publish"}, {"action": "api"}, {"action": "read", "protocol": "rtsp"}, {"action": "metrics"}):
        assert _hook(client, query=q, **bad).status_code == 401
    expired, _ = make_playback_token(cam["id"], "cam1", ttl=-5)
    assert _hook(client, query=f"token={expired}").status_code == 401
    streams.stop(cam["id"])
    assert _hook(client, query=q).status_code == 401                 # stopping the stream revokes access immediately


def test_gateway_hook_rejects_malformed_bodies(client):
    assert client.post("/api/cctv/gateway/auth", content=b"not json").status_code == 401
    assert client.post("/api/cctv/gateway/auth", json=[1, 2]).status_code == 401


def test_playback_url_uses_public_gateway_address(client, rtsp_server, monkeypatch):
    port, _ = rtsp_server
    monkeypatch.setattr(settings, "media_gateway_base_url", "http://mediamtx:8888")
    monkeypatch.setattr(settings, "media_gateway_public_url", "http://localhost:8888")
    cam = add(client, endpoint=f"rtsp://127.0.0.1:{port}/a", playback_path="cam1").json()
    streams.active()[cam["id"]] = streams.StreamSession(cam["id"], "cam1")
    url = client.get(f"/api/cctv/sources/{cam['id']}/playback", headers=KEY).json()["url"]
    assert url.startswith("http://localhost:8888/cam1/index.m3u8?token=")


def test_gateway_hook_publish_requires_configured_credentials(client, monkeypatch):
    pub = {"action": "publish", "protocol": "rtsp", "path": "webcam", "user": "pubuser", "password": "pubpass"}
    assert client.post("/api/cctv/gateway/auth", json=pub).status_code == 401          # nothing configured: denied
    monkeypatch.setattr(settings, "gateway_publish_user", "pubuser")
    monkeypatch.setattr(settings, "gateway_publish_password", "pubpass")
    assert client.post("/api/cctv/gateway/auth", json=pub).status_code == 200
    assert client.post("/api/cctv/gateway/auth", json=pub | {"password": "nope"}).status_code == 401
    assert client.post("/api/cctv/gateway/auth", json=pub | {"user": ""}).status_code == 401
    assert client.post("/api/cctv/gateway/auth", json=pub | {"protocol": "hls"}).status_code == 401
    monkeypatch.setattr(settings, "gateway_publish_user", "")
    monkeypatch.setattr(settings, "gateway_publish_password", "")
    assert client.post("/api/cctv/gateway/auth", json=pub | {"user": "", "password": ""}).status_code == 401  # empty config never matches empty creds
