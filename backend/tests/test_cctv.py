def test_cctv_sources_are_operator_configured(monkeypatch):
    from app.cctv import service

    monkeypatch.setattr(service.settings, "cctv_sources_json", '[{"id":"cam-1","name":"Gate E","kind":"http-json","zone":"gate-e"}]')
    items = service.source_catalog()
    assert items == [{"id":"cam-1","name":"Gate E","kind":"http-json","zone":"gate-e","configured":False,"access_policy":"operator-configured"}]


def test_cctv_rejects_invalid_urls(monkeypatch):
    from app.cctv import service

    monkeypatch.setattr(service.settings, "cctv_sources_json", '[{"id":"cam-1","name":"Gate E","url":"file:///secret"}]')
    try:
        service.source_catalog()
        assert False, "expected invalid URL error"
    except service.CCTVAdapterError:
        pass