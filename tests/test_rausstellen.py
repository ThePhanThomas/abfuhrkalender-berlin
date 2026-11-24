"""Mitteilungen zum Rausstellen: Nachhaken am Vorabend und „Steht draußen“ an andere Geräte."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import main, push, store
from app.models import Pickup
from tests.test_push import SUB, at, sent, setup_pickups  # noqa: F401 (fixture)

TODAY = date(2026, 1, 6)
TOMORROW = TODAY + timedelta(days=1)
OTHER = {**SUB, "endpoint": "https://push.example.test/other"}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main, "_today", lambda: TODAY)
    with TestClient(main.app) as c:
        yield c


def subscribe(*subs, **prefs):
    for s in subs:
        push.add_subscription(dict(s))
        if prefs:
            push.set_prefs(s["endpoint"], prefs)


# ---------- Geräte-Einstellungen ----------
def test_prefs_default_off_and_changeable(api):
    api.post("/api/push/subscribe", json=SUB)
    r = api.post("/api/push/prefs", json={"endpoint": SUB["endpoint"]})
    assert r.json()["prefs"] == {"nag": False, "out_notice": False}
    r = api.post("/api/push/prefs", json={"endpoint": SUB["endpoint"], "nag": True})
    assert r.json()["prefs"] == {"nag": True, "out_notice": False}
    # Neu anmelden (z. B. nach App-Update) behält die Einstellungen.
    api.post("/api/push/subscribe", json=SUB)
    assert api.post("/api/push/prefs", json={"endpoint": SUB["endpoint"]}).json()["prefs"]["nag"] is True


def test_prefs_unknown_device(api):
    r = api.post("/api/push/prefs", json={"endpoint": "https://push.example.test/unbekannt", "nag": True})
    assert r.status_code == 404
    assert "nicht für Erinnerungen angemeldet" in r.json()["detail"]


@pytest.mark.parametrize("value", ["21:05", "22:00", "9:00"])
def test_nag_time_after_21_rejected(api, value):
    cfg = store.load_config()
    r = api.put("/api/config", json={**cfg, "nag_time": value})
    assert r.status_code == 422


# ---------- Nachhaken ----------
def test_nag_names_only_missing_bins(sent):  # noqa: F811
    setup_pickups(Pickup(date=TOMORROW, category="BI", provider="BSR"), Pickup(date=TOMORROW, category="HM", provider="BSR"))
    subscribe(SUB, nag=True)
    store.set_mark(TOMORROW, "HM", "out", TODAY)
    assert push.run_nag(at("2026-01-06T21:00")) == 1
    msg = sent[0]["data"]
    assert msg["title"] == "Noch nicht draußen: Biogut"
    assert msg["tag"] == "abfuhr-2026-01-07"
    assert push.run_nag(at("2026-01-06T21:01")) == 0  # nur einmal am Tag


def test_nag_nothing_when_all_out(sent):  # noqa: F811
    setup_pickups(Pickup(date=TOMORROW, category="HM", provider="BSR"))
    subscribe(SUB, nag=True)
    store.set_mark(TOMORROW, "HM", "out", TODAY)
    assert push.run_nag(at("2026-01-06T21:00")) == 0
    assert sent == []


def test_nag_only_for_devices_that_want_it(sent):  # noqa: F811
    setup_pickups(Pickup(date=TOMORROW, category="HM", provider="BSR"))
    subscribe(SUB, nag=True)
    subscribe(OTHER)
    assert push.run_nag(at("2026-01-06T21:00")) == 1
    assert [c["endpoint"] for c in sent] == [SUB["endpoint"]]


def test_nag_time_window(sent):  # noqa: F811
    setup_pickups(Pickup(date=TOMORROW, category="HM", provider="BSR"))
    subscribe(SUB, nag=True)
    assert push.run_nag(at("2026-01-06T20:59")) == 0  # zu früh
    assert push.run_nag(at("2026-01-06T22:30")) == 0  # nach Neustart zu spät: lieber nichts
    assert push.run_nag(at("2026-01-06T21:30")) == 1


def test_nag_must_be_after_first_reminder(sent):  # noqa: F811
    setup_pickups(Pickup(date=TOMORROW, category="HM", provider="BSR"))
    cfg = store.load_config()
    store.save_config({**cfg, "notify_time": "20:00", "nag_time": "19:00"})
    subscribe(SUB, nag=True)
    assert push.run_nag(at("2026-01-06T19:00")) == 0


# ---------- „Steht draußen“ ----------
def test_out_notice_to_other_devices_after_delay(api, sent):  # noqa: F811
    subscribe(SUB, OTHER, out_notice=True)
    for cat in ("HM", "BI"):
        api.put("/api/marks", json={"date": "2026-01-07", "category": cat, "status": "out", "endpoint": SUB["endpoint"]})
    # Zeitpunkt in der Warteschlange auf den Testtag legen (Tests laufen zu beliebiger Uhrzeit).
    marked = at("2026-01-06T19:00")
    data = push._load()
    for q in data["out_pending"]:
        q["at"] = marked.isoformat()
    push._save(data)
    assert push.run_out_notices(marked + timedelta(seconds=50)) == 0  # erst nach der Wartezeit
    assert push.run_out_notices(marked + timedelta(minutes=1)) == 1
    assert sent[0]["endpoint"] == OTHER["endpoint"]  # nicht an das markierende Gerät
    assert sent[0]["data"]["title"] == "Steht draußen: Hausmüll und Biogut"
    assert push.run_out_notices(marked + timedelta(minutes=3)) == 0  # nur einmal


def queue(category, status_after, minutes_ago=3, when="2026-01-06T19:00", sender=None):
    now = at(when)
    push.queue_out_notice(TOMORROW, category, sender, now - timedelta(minutes=minutes_ago))
    if status_after:
        store.set_mark(TOMORROW, category, status_after, TODAY)
    return now


def test_out_notice_dropped_when_taken_back(sent):  # noqa: F811
    subscribe(SUB, out_notice=True)
    now = queue("HM", None)  # gleich wieder zurückgenommen
    assert push.run_out_notices(now) == 0
    assert push._load()["out_pending"] == []


def test_out_notice_text_for_tomorrow(sent):  # noqa: F811
    subscribe(SUB, out_notice=True)
    now = queue("HM", "out")
    assert push.run_out_notices(now) == 1
    assert sent[0]["data"]["body"] == "Abholung morgen. Rausstellen ist erledigt."


def test_out_notice_not_at_night_and_not_stale(sent):  # noqa: F811
    subscribe(SUB, out_notice=True)
    assert push.run_out_notices(queue("HM", "out", when="2026-01-06T23:30")) == 0
    assert push.run_out_notices(queue("BI", "out", minutes_ago=45)) == 0
    assert sent == []


def test_nothing_queued_if_no_device_wants_it(api):
    subscribe(SUB)
    api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "out"})
    assert "out_pending" not in push._load()


def test_out_to_done_does_not_queue_again(api):
    subscribe(SUB, out_notice=True)
    api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "out"})
    push._save({**push._load(), "out_pending": []})
    api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "done"})
    assert push._load()["out_pending"] == []
