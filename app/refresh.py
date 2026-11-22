"""Fetch all configured sources and persist the result.

A failing source keeps its previously stored dates, so one outage never wipes
the calendar.
"""

from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta, timezone

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


def detect_changes(old: list[dict], new: list[dict], today: date, detected_at: str) -> list[dict]:
    """Dates that moved without a `moved_from` hint (tomorrow .. today+14).
    Per category: a vanished date is paired with the nearest new date; an
    unpaired vanished date means the pickup is cancelled (new: None)."""
    lo, hi = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=14)).isoformat()

    def window(items: list[dict]) -> dict[tuple[str, str], dict]:
        return {
            (p["category"], p["date"]): p
            for p in items
            if lo <= p["date"] <= hi and not p.get("moved_from")
        }

    o, n = window(old), window(new)
    # Dates the source itself reports as moved (moved_from) are announced separately.
    announced = {(p["category"], p["moved_from"]) for p in new if p.get("moved_from")}
    changes: list[dict] = []
    used: set[tuple[str, str]] = set()
    for (cat, d), p in sorted(o.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if (cat, d) in n or (cat, d) in announced:
            continue
        candidates = [k for k in n if k[0] == cat and k not in o and k not in used]
        best = min(candidates, key=lambda k: abs((date.fromisoformat(k[1]) - date.fromisoformat(d)).days), default=None)
        if best:
            used.add(best)
        changes.append(
            {
                "category": cat,
                "old": d,
                "new": best[1] if best else None,
                "provider": p.get("provider", ""),
                "detected_at": detected_at,
            }
        )
    return changes


def _run(client: httpx.Client, today: date | None) -> dict:
    cfg = store.load_config()
    data = store.load_data()
    sources = data.setdefault("sources", {})
    today = today or date.today()
    start, end = date_range(today)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    new_changes: list[dict] = []

    def attempt(name: str, fn, keep_past: bool = False, extra: dict | None = None, compare: bool = False):
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
            if compare and prev.get("ok") and prev.get("pickups"):
                same_address = extra is None or (prev.get("address_key") and prev.get("address_key") == extra["address_key"])
                if same_address:
                    new_changes.extend(detect_changes(prev["pickups"], pickups, today, now))
            sources[name] = {
                "ok": True,
                "error": None,
                "fetched_at": now,
                "count": len(pickups),
                "pickups": pickups,
                **(extra or {}),
            }
        except SourceError as e:
            sources[name] = {
                **prev,
                "ok": False,
                "error": str(e),
                "fetched_at": now,
                "failed_since": prev.get("failed_since") if prev.get("ok") is False and prev.get("failed_since") else now,
                "fail_count": int(prev.get("fail_count") or 0) + 1,
            }

    addr = cfg.get("address")
    if addr and addr.get("key"):
        attempt(
            "bsr",
            lambda: bsr.fetch_pickups(client, addr["key"], start, end),
            extra={"address_key": addr["key"]},
            compare=True,
        )
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
            compare=True,
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

    if new_changes or data.get("changes"):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        data["changes"] = [c for c in data.get("changes", []) if c.get("detected_at", "") >= cutoff] + new_changes
    data["updated_at"] = now
    store.save_data(data)
    return data
