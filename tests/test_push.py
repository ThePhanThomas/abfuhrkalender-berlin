import base64
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app import main, push, store
from app.models import Pickup
from tests.conftest import ADDR_KEY

# Fictional subscription – a real one would point at web.push.apple.com etc.
SUB = {
    "endpoint": "https://push.example.test/abc123",
    "keys": {"p256dh": "BPlaceholderPublicKeyForTests000000000000", "auth": "authsecret0000000"},
}


@pytest.fixture
def api():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def sent(monkeypatch):
    """Records messages instead of sending them."""
    calls = []

    def fake_webpush(subscription_info, data, **kwargs):
        calls.append({"endpoint": subscription_info["endpoint"], "data": json.loads(data), **kwargs})

    monkeypatch.setattr(push, "webpush", fake_webpush)
    return calls


def setup_pickups(*pickups: Pickup, categories=("HM", "BI", "WS", "PP")):
    cfg = store.load_config()
    cfg["address"] = {"key": ADDR_KEY, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"}
    cfg["categories"] = list(categories)
    store.save_config(cfg)
    store.save_data({"updated_at": None, "sources": {"bsr": {"ok": True, "pickups": [p.to_dict() for p in pickups]}}})


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=push.TZ)


def test_public_key_is_stable_and_browser_format(api, tmp_data):
    k1 = api.get("/api/push/key").json()["public_key"]
    k2 = api.get("/api/push/key").json()["public_key"]
    assert k1 == k2
    raw = base64.urlsafe_b64decode(k1 + "=" * (-len(k1) % 4))
    assert len(raw) == 65 and raw[0] == 4  # uncompressed P-256 point
    assert (tmp_data / "vapid.json").exists()


def test_private_key_never_in_api_responses(api, tmp_data):
    api.get("/api/push/key")
    pem = json.loads((tmp_data / "vapid.json").read_text())["private_pem"]
    secret_line = pem.splitlines()[1]
    for path in ("/api/push/key", "/api/state"):
        assert secret_line not in api.get(path).text


def test_subscribe_and_unsubscribe(api):
    assert api.post("/api/push/subscribe", json=SUB).status_code == 200
    api.post("/api/push/subscribe", json=SUB)  # twice = still one entry
    assert len(push.subscriptions()) == 1
    api.post("/api/push/unsubscribe", json={"endpoint": SUB["endpoint"]})
    assert push.subscriptions() == []


def test_subscribe_requires_https(api):
    bad = {**SUB, "endpoint": "http://192.168.0.1/x"}
    assert api.post("/api/push/subscribe", json=bad).status_code == 422


def test_test_message(api, sent):
    api.post("/api/push/subscribe", json=SUB)
    assert api.post("/api/push/test", json={"endpoint": SUB["endpoint"]}).status_code == 200
    assert sent[0]["endpoint"] == SUB["endpoint"]
    assert sent[0]["vapid_claims"]["sub"].startswith("mailto:")


def test_test_message_unknown_device(api, sent):
    assert api.post("/api/push/test", json={"endpoint": SUB["endpoint"]}).status_code == 404
    assert sent == []


def test_gone_subscription_is_removed(api, monkeypatch):
    api.post("/api/push/subscribe", json=SUB)

    class Gone:
        status_code = 410

    def gone(*a, **k):
        raise WebPushException("gone", response=Gone())

    monkeypatch.setattr(push, "webpush", gone)
    r = api.post("/api/push/test", json={"endpoint": SUB["endpoint"]})
    assert r.status_code == 502
    assert "neu einschalten" in r.json()["detail"]
    assert push.subscriptions() == []


def test_reminder_text_lists_tomorrows_categories(sent):
    setup_pickups(
        Pickup(date=at("2026-01-07").date(), category="BI", provider="BSR"),
        Pickup(date=at("2026-01-07").date(), category="HM", provider="BSR"),
        Pickup(date=at("2026-01-07").date(), category="LT", provider="BSR"),  # not shown -> not mentioned
    )
    msg = push.reminder_for(at("2026-01-07").date())
    assert msg["title"] == "Morgen: Biogut und Hausmüll"
    assert "Tonnen" in msg["body"]


def test_run_due_sends_once_at_configured_time(sent):
    setup_pickups(Pickup(date=at("2026-01-07").date(), category="HM", provider="BSR"))
    push.add_subscription(SUB)
    assert push.run_due(at("2026-01-06T17:59")) == 0  # too early
    assert push.run_due(at("2026-01-06T18:00")) == 1
    assert push.run_due(at("2026-01-06T18:01")) == 0  # already sent today
    assert len(sent) == 1
    assert sent[0]["data"]["title"] == "Morgen: Hausmüll"


def test_run_due_nothing_tomorrow(sent):
    setup_pickups(Pickup(date=at("2026-01-09").date(), category="HM", provider="BSR"))
    push.add_subscription(SUB)
    assert push.run_due(at("2026-01-06T18:30")) == 0
    assert sent == []


def test_run_due_respects_notify_time(api, sent):
    setup_pickups(Pickup(date=at("2026-01-07").date(), category="HM", provider="BSR"))
    push.add_subscription(SUB)
    cfg = store.load_config()
    body = {"address": cfg["address"], "categories": ["HM"], "paper": {"mode": "off"}, "notify_time": "20:30"}
    api.put("/api/config", json=body)  # address unchanged -> no fetch
    assert store.load_config()["notify_time"] == "20:30"
    assert push.run_due(at("2026-01-06T20:00")) == 0
    assert push.run_due(at("2026-01-06T20:30")) == 1


def test_invalid_notify_time_rejected(api):
    body = {"address": None, "categories": ["HM"], "paper": {"mode": "off"}, "notify_time": "25:00"}
    assert api.put("/api/config", json=body).status_code == 422


def test_pwa_files_served(api):
    sw = api.get("/sw.js")
    assert sw.status_code == 200
    assert "javascript" in sw.headers["content-type"]
    manifest = api.get("/static/manifest.webmanifest").json()
    assert manifest["display"] == "standalone"
    for icon in manifest["icons"]:
        assert api.get(icon["src"]).status_code == 200
    assert api.get("/static/icons/apple-touch-icon.png").status_code == 200
