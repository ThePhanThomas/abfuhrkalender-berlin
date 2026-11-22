import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, refresh, store
from app.models import SourceError
from tests.conftest import ADDR_KEY, combined_handler

ADDRESS = {"key": ADDR_KEY, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"}


@pytest.fixture
def api(monkeypatch):
    real_client = httpx.Client

    def mocked_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(combined_handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", mocked_client)
    with TestClient(main.app) as c:
        yield c


def test_initial_state_has_no_address(api):
    s = api.get("/api/state").json()
    assert s["config"]["address"] is None
    assert s["pickups"] == []
    assert s["portal_configured"] is False


def test_address_search(api):
    r = api.get("/api/address/search", params={"street": "Musterstraße", "number": "1A"})
    assert r.status_code == 200
    assert r.json()[0]["key"] == ADDR_KEY


def test_refresh_without_address_is_rejected(api):
    assert api.post("/api/refresh").status_code == 400


def test_save_config_triggers_fetch(api):
    body = {"address": ADDRESS, "categories": ["HM", "BI", "WS", "PP"], "paper": {"mode": "off"}}
    s = api.put("/api/config", json=body).json()
    assert s["sources"]["bsr"]["ok"] is True
    assert len(s["pickups"]) == 3


def test_manual_paper(api):
    body = {
        "address": ADDRESS,
        "categories": ["PP"],
        "paper": {"mode": "manual", "first_date": "2026-01-09", "interval_weeks": 4},
    }
    s = api.put("/api/config", json=body).json()
    assert s["sources"]["paper_manual"]["ok"] is True
    assert any(p["category"] == "PP" for p in s["pickups"])


def test_manual_paper_requires_date(api):
    body = {"address": ADDRESS, "categories": ["PP"], "paper": {"mode": "manual"}}
    assert api.put("/api/config", json=body).status_code == 422


def test_unknown_category_rejected(api):
    body = {"address": ADDRESS, "categories": ["XX"], "paper": {"mode": "off"}}
    assert api.put("/api/config", json=body).status_code == 422


def test_portal_paper(api, monkeypatch):
    monkeypatch.setenv("BR_USERNAME", "user")
    monkeypatch.setenv("BR_PASSWORD", "pw")
    body = {"address": ADDRESS, "categories": ["HM", "PP"], "paper": {"mode": "portal"}}
    s = api.put("/api/config", json=body).json()
    assert s["portal_configured"] is True
    assert s["sources"]["berlin_recycling"]["count"] == 3


def test_failed_source_keeps_previous_dates(api, monkeypatch):
    body = {"address": ADDRESS, "categories": ["HM", "BI", "WS"], "paper": {"mode": "off"}}
    api.put("/api/config", json=body)

    def boom(*a, **k):
        raise SourceError("BSR nicht erreichbar")

    monkeypatch.setattr(refresh.bsr, "fetch_pickups", boom)
    s = api.post("/api/refresh").json()
    assert s["sources"]["bsr"]["ok"] is False
    assert s["sources"]["bsr"]["error"] == "BSR nicht erreichbar"
    assert len(s["pickups"]) == 3


def test_ics_export(api):
    body = {"address": ADDRESS, "categories": ["HM", "BI"], "paper": {"mode": "off"}}
    api.put("/api/config", json=body)
    r = api.get("/api/calendar.ics", params={"reminder": "true"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    text = r.text
    assert text.count("BEGIN:VEVENT") == 2  # WS not selected
    assert "SUMMARY:Hausmüll" in text
    assert "TRIGGER:-PT6H" in text
    assert "LOCATION:Musterstr. 1A\\, 10115 Berlin (Mitte)" in text


def test_secrets_never_stored(api, monkeypatch, tmp_data):
    monkeypatch.setenv("BR_USERNAME", "geheim-user")
    monkeypatch.setenv("BR_PASSWORD", "geheim-pw")
    body = {"address": ADDRESS, "categories": ["PP"], "paper": {"mode": "portal"}}
    api.put("/api/config", json=body)
    for f in tmp_data.iterdir():
        assert "geheim" not in f.read_text(encoding="utf-8")


def test_page_and_assets_are_revalidated(api):
    """Regression: without Cache-Control browsers mixed a new page with old CSS/JS."""
    for path in ("/", "/static/app.css", "/static/app.js", "/api/state"):
        assert api.get(path).headers["cache-control"] == "no-cache", path


def test_store_defaults_merge(tmp_data):
    (tmp_data / "config.json").write_text('{"categories": ["HM"]}', encoding="utf-8")
    cfg = store.load_config()
    assert cfg["categories"] == ["HM"]
    assert cfg["paper"]["mode"] == "off"


def test_glas_and_sonstiges_not_offered(api):
    """Glas and Sonstiges have no reliable source, so they are not selectable."""
    cats = api.get("/api/state").json()["categories"]
    assert "GL" not in cats and "SO" not in cats
    body = {"address": ADDRESS, "categories": ["HM", "GL"], "paper": {"mode": "off"}}
    assert api.put("/api/config", json=body).status_code == 422


def test_old_config_drops_removed_categories(tmp_data):
    (tmp_data / "config.json").write_text('{"categories": ["HM", "GL", "SO"]}', encoding="utf-8")
    assert store.load_config()["categories"] == ["HM"]
