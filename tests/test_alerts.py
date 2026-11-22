from datetime import date, datetime, timedelta, timezone

import pytest

from app import main, push, refresh, store
from app.models import Pickup, SourceError
from tests.conftest import ADDR_KEY
from tests.test_push import SUB, at, sent, setup_pickups  # noqa: F401  (fixture `sent`)

TODAY = date(2026, 12, 20)


def run_refresh(client, monkeypatch, bsr_result, key=ADDR_KEY, today=TODAY):
    store.save_config(
        {
            "address": {"key": key, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"},
            "categories": ["HM", "PP"],
            "paper": {"mode": "off", "first_date": None, "interval_weeks": 4},
        }
    )

    def fake(*a, **k):
        if isinstance(bsr_result, Exception):
            raise bsr_result
        return bsr_result

    monkeypatch.setattr(refresh.bsr, "fetch_pickups", fake)
    return refresh.run(client=client, today=today)


def pk(d, cat="HM", moved_from=None):
    return Pickup(date=date.fromisoformat(d), category=cat, provider="BSR",
                  moved_from=date.fromisoformat(moved_from) if moved_from else None)


def test_fail_count_and_failed_since(client, monkeypatch):
    run_refresh(client, monkeypatch, [pk("2026-12-22")])
    d = run_refresh(client, monkeypatch, SourceError("kaputt"))
    s = d["sources"]["bsr"]
    assert s["fail_count"] == 1 and s["failed_since"] and s["pickups"]
    first = s["failed_since"]
    d = run_refresh(client, monkeypatch, SourceError("kaputt"))
    assert d["sources"]["bsr"]["fail_count"] == 2
    assert d["sources"]["bsr"]["failed_since"] == first
    d = run_refresh(client, monkeypatch, [pk("2026-12-22")])
    assert "fail_count" not in d["sources"]["bsr"] and "failed_since" not in d["sources"]["bsr"]


def test_refresh_due_retries_after_failure(monkeypatch):
    monkeypatch.setattr(main, "REFRESH_HOURS", 168.0)
    now = datetime(2026, 12, 20, 12, tzinfo=timezone.utc)
    stamp = (now - timedelta(hours=7)).isoformat()
    assert not main._refresh_due({"updated_at": stamp, "sources": {"bsr": {"ok": True}}}, now)
    assert main._refresh_due({"updated_at": stamp, "sources": {"bsr": {"ok": False}}}, now)
    assert main._refresh_due({"updated_at": None, "sources": {}}, now)


def test_failure_alert_once_then_recovery(sent):
    push.add_subscription(SUB)
    setup_pickups()
    data = store.load_data()
    src = data["sources"]["bsr"]
    src.update(ok=False, error="Server down", fail_count=1, failed_since="2026-12-18T10:00:00+00:00")
    store.save_data(data)
    assert push.run_alerts(at("2026-12-20T09:00")) == 0  # only one failure so far
    src["fail_count"] = 2
    store.save_data(data)
    assert push.run_alerts(at("2026-12-20T09:01")) == 1
    assert "Abruf klappt nicht: BSR" in sent[0]["data"]["title"]
    assert "18.12." in sent[0]["data"]["body"]
    assert push.run_alerts(at("2026-12-20T09:02")) == 0
    src.update(ok=True, fail_count=0)
    store.save_data(data)
    assert push.run_alerts(at("2026-12-20T09:03")) == 1
    assert "klappt wieder" in sent[1]["data"]["title"]
    assert push.run_alerts(at("2026-12-20T09:04")) == 0


def test_quiet_hours_and_no_devices(sent):
    setup_pickups(pk("2026-12-27", moved_from="2026-12-26"))
    assert push.run_alerts(at("2026-12-20T09:00")) == 0  # no device: nothing marked
    push.add_subscription(SUB)
    assert push.run_alerts(at("2026-12-20T22:00")) == 0
    assert push.run_alerts(at("2026-12-20T07:59")) == 0
    assert push.run_alerts(at("2026-12-20T08:00")) == 1


def test_moved_pickup_announced_once(sent):
    push.add_subscription(SUB)
    setup_pickups(pk("2026-12-27", moved_from="2026-12-26"), pk("2027-01-20", moved_from="2027-01-19"))
    assert push.run_alerts(at("2026-12-20T09:00")) == 1
    m = sent[0]["data"]
    assert m["title"] == "Verschoben: Hausmüll"
    assert m["body"] == "Abholung am Sonntag 27.12. statt Samstag 26.12."
    assert push.run_alerts(at("2026-12-20T09:05")) == 0


def test_moved_pickup_too_far_or_deselected(sent):
    push.add_subscription(SUB)
    setup_pickups(pk("2026-12-30", moved_from="2026-12-29"))
    assert push.run_alerts(at("2026-12-20T09:00")) == 0  # 9 days away
    setup_pickups(pk("2026-12-27", moved_from="2026-12-26"), categories=("BI",))
    assert push.run_alerts(at("2026-12-20T09:00")) == 0


def test_evening_reminder_mentions_move(sent):
    push.add_subscription(SUB)
    setup_pickups(pk("2026-12-27", moved_from="2026-12-26"))
    msg = push.reminder_for(date(2026, 12, 27))
    assert msg["body"].endswith("Achtung, verschoben von Samstag.")


def test_paper_change_detected_and_sent_once(client, monkeypatch, sent):
    run_refresh(client, monkeypatch, [pk("2026-12-22", "PP")])
    d = run_refresh(client, monkeypatch, [pk("2026-12-23", "PP")])
    assert [(c["category"], c["old"], c["new"]) for c in d["changes"]] == [("PP", "2026-12-22", "2026-12-23")]
    push.add_subscription(SUB)
    assert push.run_alerts(at("2026-12-20T09:00")) == 1
    assert sent[0]["data"]["title"] == "Termin geändert: Papier"
    assert sent[0]["data"]["body"] == "Jetzt am Mittwoch 23.12. statt Dienstag 22.12."
    assert push.run_alerts(at("2026-12-20T09:01")) == 0


def test_cancelled_pickup(client, monkeypatch, sent):
    run_refresh(client, monkeypatch, [pk("2026-12-22", "PP")])
    d = run_refresh(client, monkeypatch, [])
    assert d["changes"][0]["new"] is None
    push.add_subscription(SUB)
    push.run_alerts(at("2026-12-20T09:00"))
    assert "entfällt laut BSR" in sent[0]["data"]["body"]


def test_no_diff_after_address_change(client, monkeypatch):
    run_refresh(client, monkeypatch, [pk("2026-12-22")])
    d = run_refresh(client, monkeypatch, [pk("2026-12-23")], key="TEST-KEY-1")
    assert not d.get("changes")


def test_no_diff_after_failed_fetch(client, monkeypatch):
    run_refresh(client, monkeypatch, [pk("2026-12-22")])
    run_refresh(client, monkeypatch, SourceError("kaputt"))
    d = run_refresh(client, monkeypatch, [pk("2026-12-23")])
    assert not d.get("changes")


def test_holiday_move_with_moved_from_is_not_reported_as_cancelled():
    from app.refresh import detect_changes

    today = date(2026, 12, 20)
    old = [{"date": "2026-12-25", "category": "HM", "provider": "BSR", "moved_from": None}]
    new = [{"date": "2026-12-27", "category": "HM", "provider": "BSR", "moved_from": "2026-12-25"}]
    assert detect_changes(old, new, today, "2026-12-20T10:00:00+00:00") == []
