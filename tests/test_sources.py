from datetime import date

import httpx
import pytest

from app.models import SourceError
from app.sources import berlin_recycling, bsr, manual
from tests.conftest import ADDR_KEY, br_handler


def test_bsr_search_address(client):
    res = bsr.search_address(client, "Musterstraße", "1A")
    assert res == [{"key": ADDR_KEY, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"}]


def test_bsr_search_requires_both_fields(client):
    assert bsr.search_address(client, "Musterstraße", "") == []


def test_bsr_search_html_error_means_no_match():
    def handler(_):
        return httpx.Response(200, text="<html>error</html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        assert bsr.search_address(c, "Irgendwo", "1") == []


def test_bsr_fetch_parses_categories_providers_and_shifts(client):
    pickups = bsr.fetch_pickups(client, ADDR_KEY, date(2026, 1, 1), date(2026, 12, 31))
    assert [(p.date, p.category, p.provider) for p in pickups] == [
        (date(2026, 1, 6), "WS", "ALBA"),
        (date(2026, 1, 7), "BI", "BSR"),
        (date(2026, 1, 29), "HM", "BSR"),
    ]
    moved = pickups[-1]
    assert moved.moved_from == date(2026, 1, 28)
    assert pickups[0].moved_from is None


def test_bsr_fetch_invalid_json_raises():
    def handler(_):
        return httpx.Response(200, text="<html>error</html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(SourceError):
            bsr.fetch_pickups(c, "x", date(2026, 1, 1), date(2026, 12, 31))


def test_berlin_recycling_fetch(client):
    pickups = berlin_recycling.fetch_pickups(client, "user", "pw")
    assert [(p.date, p.category) for p in pickups] == [
        (date(2026, 1, 9), "PP"),
        (date(2026, 2, 6), "PP"),
        (date(2026, 2, 10), "GL"),
    ]


def test_berlin_recycling_bad_login():
    transport = httpx.MockTransport(lambda r: br_handler(r, login_ok=False))
    with httpx.Client(transport=transport) as c:
        with pytest.raises(SourceError, match="Login"):
            berlin_recycling.fetch_pickups(c, "user", "falsch")


def test_berlin_recycling_needs_start_page_before_data(client, monkeypatch):
    """Regression: without opening Default.aspx the portal refuses the data."""
    real_get = client.get

    def get_without_start_page(url, *a, **k):
        if str(url).endswith("Default.aspx"):
            return httpx.Response(200, request=httpx.Request("GET", url))
        return real_get(url, *a, **k)

    monkeypatch.setattr(client, "get", get_without_start_page)
    with pytest.raises(SourceError, match="Session invalid"):
        berlin_recycling.fetch_pickups(client, "user", "pw")


def test_berlin_recycling_start_page_redirect_means_login_failed(client):
    def handler(request):
        if request.url.path == "/Default.aspx":
            return httpx.Response(302, headers={"Location": "/Login.aspx"})
        return br_handler(request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(SourceError, match="Login"):
            berlin_recycling.fetch_pickups(c, "user", "pw")


def test_berlin_recycling_missing_credentials(client):
    with pytest.raises(SourceError, match="Zugangsdaten"):
        berlin_recycling.fetch_pickups(client, "", "")


def test_manual_rhythm_aligns_to_range():
    pickups = manual.generate(date(2025, 12, 12), 4, date(2026, 1, 1), date(2026, 3, 31))
    assert [p.date for p in pickups] == [date(2026, 1, 9), date(2026, 2, 6), date(2026, 3, 6)]
    assert all(p.category == "PP" for p in pickups)


def test_manual_rhythm_first_date_inside_range():
    pickups = manual.generate(date(2026, 2, 6), 4, date(2026, 1, 1), date(2026, 3, 31))
    assert [p.date for p in pickups] == [date(2026, 2, 6), date(2026, 3, 6)]
