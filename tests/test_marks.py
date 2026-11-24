"""Tonne als rausgestellt / abgeholt markieren (data/marks.json)."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main, push, store
from app.models import Pickup
from tests.test_push import at, sent, setup_pickups  # noqa: F401 (fixture)

TODAY = date(2026, 1, 6)


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(main, "_today", lambda: TODAY)
    with TestClient(main.app) as c:
        yield c


def test_mark_out_then_done_then_remove(api):
    r = api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "out"})
    assert r.status_code == 200
    assert r.json()["marks"] == {"2026-01-07": {"HM": "out"}}
    api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "done"})
    assert api.get("/api/state").json()["marks"] == {"2026-01-07": {"HM": "done"}}
    r = api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": None})
    assert r.json()["marks"] == {}


def test_past_days_are_dropped(api, tmp_data):
    (tmp_data / "marks.json").write_text(
        json.dumps({"2026-01-01": {"HM": "done"}, "2026-01-05": {"BI": "out"}, "2026-01-06": {"WS": "out"}})
    )
    assert api.get("/api/state").json()["marks"] == {"2026-01-06": {"WS": "out"}}
    # Beim nächsten Schreiben verschwinden die alten Tage auch aus der Datei.
    api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "out"})
    assert json.loads((tmp_data / "marks.json").read_text()) == {
        "2026-01-06": {"WS": "out"},
        "2026-01-07": {"HM": "out"},
    }


def test_broken_file_does_not_break_state(api, tmp_data):
    (tmp_data / "marks.json").write_text(json.dumps({"2026-01-07": "kaputt", "2026-01-08": {"HM": "egal"}}))
    assert api.get("/api/state").json()["marks"] == {}


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"date": "2026-01-05", "category": "HM", "status": "out"}, "Vergangene"),
        ({"date": "2026-01-20", "category": "HM", "status": "out"}, "im Voraus"),
        ({"date": "2026-01-07", "category": "XX", "status": "out"}, "Müllart"),
    ],
)
def test_invalid_marks_rejected(api, body, detail):
    r = api.put("/api/marks", json=body)
    assert r.status_code == 422
    assert detail in r.json()["detail"]


def test_unknown_status_rejected(api):
    r = api.put("/api/marks", json={"date": "2026-01-07", "category": "HM", "status": "weg"})
    assert r.status_code == 422


def test_reminder_skips_bins_already_out(sent):  # noqa: F811
    day = at("2026-01-07").date()
    setup_pickups(
        Pickup(date=day, category="BI", provider="BSR"),
        Pickup(date=day, category="HM", provider="BSR"),
    )
    store.set_mark(day, "HM", "out", TODAY)
    assert push.reminder_for(day)["title"] == "Morgen: Biogut"
    store.set_mark(day, "BI", "out", TODAY)
    assert push.reminder_for(day) is None
