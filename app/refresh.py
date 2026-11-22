"""Fetch all configured sources and persist the result.

A failing source keeps its previously stored dates, so one outage never wipes
the calendar.
"""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timezone

import httpx

from app import store
from app.models import SourceError
from app.sources import berlin_recycling, bsr, manual

_refresh_lock = threading.Lock()


def date_range(today: date | None = None) -> tuple[date, date]:
    """Current year plus the next one."""
    today = today or date.today()
    return date(today.year, 1, 1), date(today.year + 1, 12, 31)


def portal_configured() -> bool:
    return bool(os.environ.get("BR_USERNAME") and os.environ.get("BR_PASSWORD"))


def run(client: httpx.Client | None = None, today: date | None = None) -> dict:
    with _refresh_lock:
        own_client = client is None
        client = client or httpx.Client(headers={"User-Agent": "abfuhrkalender/1.0"})
        try:
            return _run(client, today)
        finally:
            if own_client:
                client.close()


def _run(client: httpx.Client, today: date | None) -> dict:
    cfg = store.load_config()
    data = store.load_data()
    sources = data.setdefault("sources", {})
    today = today or date.today()
    start, end = date_range(today)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def attempt(name: str, fn, keep_past: bool = False):
        """keep_past: the source only returns upcoming dates (Berlin Recycling
        portal), so past dates from earlier fetches are kept to fill the year."""
        prev = sources.get(name, {})
        try:
            pickups = [p.to_dict() for p in fn()]
            if keep_past:
                fetched = {(p["date"], p["category"]) for p in pickups}
                kept = [
                    p
                    for p in prev.get("pickups", [])
                    if start.isoformat() <= p["date"] < today.isoformat() and (p["date"], p["category"]) not in fetched
                ]
                pickups = sorted(kept + pickups, key=lambda p: (p["date"], p["category"]))
            sources[name] = {
                "ok": True,
                "error": None,
                "fetched_at": now,
                "count": len(pickups),
                "pickups": pickups,
            }
        except SourceError as e:
            sources[name] = {**prev, "ok": False, "error": str(e), "fetched_at": now}

    addr = cfg.get("address")
    if addr and addr.get("key"):
        attempt("bsr", lambda: bsr.fetch_pickups(client, addr["key"], start, end))
    else:
        sources.pop("bsr", None)

    paper = cfg.get("paper") or {}
    mode = paper.get("mode")
    if mode == "portal":
        sources.pop("paper_manual", None)
        attempt(
            "berlin_recycling",
            lambda: berlin_recycling.fetch_pickups(
                client, os.environ.get("BR_USERNAME", ""), os.environ.get("BR_PASSWORD", "")
            ),
            keep_past=True,
        )
    elif mode == "manual" and paper.get("first_date"):
        sources.pop("berlin_recycling", None)
        attempt(
            "paper_manual",
            lambda: manual.generate(
                date.fromisoformat(paper["first_date"]), int(paper.get("interval_weeks") or 4), start, end
            ),
        )
    else:
        sources.pop("berlin_recycling", None)
        sources.pop("paper_manual", None)

    data["updated_at"] = now
    store.save_data(data)
    return data
