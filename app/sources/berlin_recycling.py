"""Berlin Recycling: Papier (and possibly Glas etc.) via the customer portal.

Requires a portal login (owners / property managers). The public tenant
calendar at abfuhrkalender.berlin-recycling.de is protected by reCAPTCHA and
must NOT be automated.

The portal returns double-encoded JSON (``{"d": "<json string>"}``).
"""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx

from app.models import Pickup, SourceError

PORTAL = "https://kundenportal.berlin-recycling.de/"
TIMEOUT = 30.0
PROVIDER = "Berlin Recycling"


def _decode(r: httpx.Response) -> dict:
    try:
        outer = r.json()
        inner = outer.get("d", outer)
        return json.loads(inner) if isinstance(inner, str) else inner
    except (ValueError, AttributeError) as e:
        raise SourceError("Berlin Recycling hat eine unerwartete Antwort geliefert.") from e


def categorize(material: str) -> str:
    m = material.lower()
    if "papier" in m or "pappe" in m or "ppk" in m or "karton" in m:
        return "PP"
    if "glas" in m:
        return "GL"
    if "bio" in m:
        return "BI"
    return "SO"


def fetch_pickups(client: httpx.Client, username: str, password: str) -> list[Pickup]:
    if not username or not password:
        raise SourceError("Zugangsdaten für Berlin Recycling fehlen (BR_USERNAME/BR_PASSWORD).")
    try:
        client.get(PORTAL, follow_redirects=False, timeout=TIMEOUT)
        r = client.post(
            f"{PORTAL}Login.aspx/Auth",
            json={"username": username, "password": password, "rememberMe": False, "encrypted": False},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        login = _decode(r)
        if isinstance(login, dict) and login.get("Error"):
            raise SourceError("Login bei Berlin Recycling fehlgeschlagen (Zugangsdaten prüfen).")

        headers = {"Content-Type": "application/json"}
        service = f"{PORTAL}Default.aspx"
        client.post(f"{service}/GetDashboard", headers=headers, timeout=TIMEOUT).raise_for_status()
        r = client.post(
            f"{service}/GetDatasetTableHead",
            headers=headers,
            json={
                "datasettablecode": "ABFUHRKALENDER",
                "startindex": 0,
                "searchtext": "",
                "rangefilter": "[]",
                "ordername": "",
                "orderdir": "",
                "ClientParameters": "",
                "headrecid": "",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise SourceError(f"Berlin Recycling nicht erreichbar: {e}") from e

    data = _decode(r)
    rows = (data.get("Object") or {}).get("data") if isinstance(data, dict) else None
    if rows is None:
        raise SourceError("Keine Abfuhrdaten im Kundenportal gefunden.")
    return parse_rows(rows)


def parse_rows(rows: list[dict]) -> list[Pickup]:
    pickups = []
    for row in rows:
        try:
            d = datetime.strptime(row["Task Date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        material = row.get("Material Description", "")
        pickups.append(Pickup(date=d, category=categorize(material), provider=PROVIDER, note=material))
    pickups.sort(key=lambda p: (p.date, p.category))
    return pickups
