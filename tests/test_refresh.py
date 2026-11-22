from datetime import date

import pytest

from app import refresh, store
from app.models import Pickup, SourceError
from tests.conftest import ADDR_KEY


def pp(d: str) -> Pickup:
    return Pickup(date=date.fromisoformat(d), category="PP", provider="Berlin Recycling")


@pytest.fixture
def portal(monkeypatch, client):
    """Configure portal mode and let tests decide what the portal returns."""
    monkeypatch.setenv("BR_USERNAME", "user")
    monkeypatch.setenv("BR_PASSWORD", "pw")
    store.save_config(
        {
            "address": {"key": ADDR_KEY, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"},
            "categories": ["PP"],
            "paper": {"mode": "portal", "first_date": None, "interval_weeks": 4},
        }
    )
    answers = []
    monkeypatch.setattr(refresh.berlin_recycling, "fetch_pickups", lambda *a, **k: answers.pop(0))

    def run(today: str, result):
        answers.append(result)
        data = refresh.run(client=client, today=date.fromisoformat(today))
        return [p["date"] for p in data["sources"]["berlin_recycling"]["pickups"]]

    return run


def test_portal_keeps_past_dates_from_earlier_fetches(portal):
    portal("2026-11-22", [pp("2026-12-01"), pp("2026-12-29")])
    # Later the portal only returns upcoming dates; 01.12. is now in the past.
    dates = portal("2026-12-10", [pp("2026-12-29"), pp("2027-01-26")])
    assert dates == ["2026-12-01", "2026-12-29", "2027-01-26"]


def test_portal_future_dates_always_come_from_latest_fetch(portal):
    portal("2026-11-22", [pp("2026-12-01"), pp("2026-12-29")])
    # 29.12. was moved by the portal to 30.12. -> the old future date must go.
    dates = portal("2026-11-23", [pp("2026-12-01"), pp("2026-12-30")])
    assert dates == ["2026-12-01", "2026-12-30"]


def test_portal_drops_dates_before_current_year(portal):
    portal("2026-12-20", [pp("2026-12-01"), pp("2026-12-29")])
    dates = portal("2027-01-05", [pp("2027-01-26")])
    assert dates == ["2027-01-26"]  # nothing from 2026 is kept


def test_portal_failure_keeps_everything(portal, monkeypatch, client):
    portal("2026-11-22", [pp("2026-12-01")])

    def boom(*a, **k):
        raise SourceError("Berlin Recycling nicht erreichbar")

    monkeypatch.setattr(refresh.berlin_recycling, "fetch_pickups", boom)
    data = refresh.run(client=client, today=date(2026, 12, 10))
    src = data["sources"]["berlin_recycling"]
    assert src["ok"] is False
    assert [p["date"] for p in src["pickups"]] == ["2026-12-01"]
