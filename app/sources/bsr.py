"""Berliner Stadtreinigung (BSR): Hausmüll, Biogut, Wertstoffe, Laubtonne, Weihnachtsbaum.

The BSR website uses an undocumented but public JSON API. Wertstoffe in some
districts are collected by ALBA; those still come through this API with
``disposalComp == "ALBA"``. Holiday shifts are already applied by BSR
(``serviceDate_actual`` vs. ``serviceDate_regular``).

The API rejects browser requests with an ``Origin`` header (403), so it must be
called server-side.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from app.models import Pickup, SourceError

BASE_URL = "https://umnewforms.bsr.de/p/de.bsr.adressen.app"
TIMEOUT = 30.0


def search_address(client: httpx.Client, street: str, number: str) -> list[dict]:
    """Return matching addresses as ``[{"key": ..., "label": ...}]``.

    BSR expects ``<street>:::<house number>`` and is lenient about spelling
    ("Straße"/"str."/case/spaces). Invalid queries return an HTML error page,
    which we treat as "no match".
    """
    street, number = street.strip(), number.strip()
    if not street or not number:
        return []
    try:
        r = client.get(
            f"{BASE_URL}/plzSet/plzSet",
            params={"searchQuery": f"{street}:::{number}"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except ValueError:
        return []
    except httpx.HTTPError as e:
        raise SourceError(f"BSR-Adresssuche nicht erreichbar: {e}") from e
    return [{"key": item["value"], "label": item["label"]} for item in data if item.get("value")]


def fetch_pickups(client: httpx.Client, addr_key: str, start: date, end: date) -> list[Pickup]:
    """Fetch all BSR collection dates for ``addr_key`` between ``start`` and ``end``."""
    flt = (
        f"AddrKey eq '{addr_key}' and "
        f"DateFrom eq datetime'{start.isoformat()}T00:00:00' and "
        f"DateTo eq datetime'{end.isoformat()}T00:00:00'"
    )
    try:
        r = client.get(f"{BASE_URL}/abfuhrEvents", params={"filter": flt}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except ValueError as e:
        raise SourceError("BSR hat keine gültigen Daten geliefert (Adresse prüfen).") from e
    except httpx.HTTPError as e:
        raise SourceError(f"BSR nicht erreichbar: {e}") from e
    return parse_events(data)


def _parse_de_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def parse_events(data: dict) -> list[Pickup]:
    pickups: list[Pickup] = []
    for entries in (data.get("dates") or {}).values():
        for e in entries:
            actual = _parse_de_date(e["serviceDate_actual"])
            regular_raw = e.get("serviceDate_regular") or e["serviceDate_actual"]
            regular = _parse_de_date(regular_raw)
            pickups.append(
                Pickup(
                    date=actual,
                    category=e.get("category") or "SO",
                    provider=e.get("disposalComp") or "BSR",
                    moved_from=regular if regular != actual else None,
                    note=e.get("warningText") or "",
                )
            )
    pickups.sort(key=lambda p: (p.date, p.category))
    return pickups
