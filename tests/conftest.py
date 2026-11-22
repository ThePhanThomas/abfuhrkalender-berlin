import json

import httpx
import pytest

# Fictional address key / data – never put a real household's address in tests.
ADDR_KEY = "04901100010000000000001A"

BSR_EVENTS = {
    "AddrKey": ADDR_KEY,
    "dates": {
        "2026-01-06": [
            {"category": "WS", "serviceDay": "DI", "serviceDate_actual": "06.01.2026",
             "serviceDate_regular": "06.01.2026", "rhythm": "gerade Woche", "warningText": "", "disposalComp": "ALBA"}
        ],
        "2026-01-07": [
            {"category": "BI", "serviceDay": "MI", "serviceDate_actual": "07.01.2026",
             "serviceDate_regular": "07.01.2026", "rhythm": "gerade Woche", "warningText": "", "disposalComp": "BSR"}
        ],
        "2026-01-29": [
            {"category": "HM", "serviceDay": "DO", "serviceDate_actual": "29.01.2026",
             "serviceDate_regular": "28.01.2026", "rhythm": "ungerade Woche",
             "warningText": "Termin verlegt vom 28.01.2026", "disposalComp": "BSR"}
        ],
    },
}

ADDRESS_RESULTS = [{"value": ADDR_KEY, "label": "Musterstr. 1A, 10115 Berlin (Mitte)"}]

# Field names as returned by the real portal ("Description" = container size).
BR_ROWS = [
    {"Task Date": "2026-01-09", "Description": "240 L MGB Leerung", "Material Description": "Papier, Pappe, Kartonagen"},
    {"Task Date": "2026-02-06", "Description": "240 L MGB Leerung", "Material Description": "Papier, Pappe, Kartonagen"},
    {"Task Date": "2026-02-10", "Description": "240 L MGB Leerung", "Material Description": "Glas weiß"},
]


def bsr_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/plzSet/plzSet"):
        q = request.url.params["searchQuery"]
        if q.lower().startswith("musterstr"):
            return httpx.Response(200, json=ADDRESS_RESULTS)
        if ":::" not in q:
            return httpx.Response(200, text="<html>error</html>")
        return httpx.Response(200, json=[])
    if request.url.path.endswith("/abfuhrEvents"):
        return httpx.Response(200, json=BSR_EVENTS)
    return httpx.Response(404)


def br_handler(request: httpx.Request, login_ok: bool = True) -> httpx.Response:
    """Mimics the real portal, which tracks progress in a session cookie:
    after login, Default.aspx must be opened once before data requests work
    (otherwise they return {"Error": ..., "Message": ...})."""
    path = request.url.path
    session = request.headers.get("cookie", "")
    if path == "/":
        return httpx.Response(302, headers={"Location": "/Login.aspx"})
    if path.endswith("/Login.aspx/Auth"):
        if not login_ok:
            inner = {"Error": True, "Message": "Incorrect login data - Access denied"}
            return httpx.Response(200, json={"d": json.dumps(inner)})
        return httpx.Response(
            200,
            json={"d": json.dumps({"Error": False, "Message": "Default.aspx"})},
            headers={"Set-Cookie": "sid=auth; Path=/"},
        )
    if path == "/Default.aspx":
        if "sid=" not in session:
            return httpx.Response(302, headers={"Location": "/Login.aspx"})
        return httpx.Response(200, text="<html></html>", headers={"Set-Cookie": "sid=ready; Path=/"})
    if path.endswith("/GetDashboard"):
        return httpx.Response(200, json={"d": "{}"})
    if path.endswith("/GetDatasetTableHead"):
        if "sid=ready" not in session:
            return httpx.Response(200, json={"d": json.dumps({"Error": True, "Message": "Session invalid"})})
        return httpx.Response(200, json={"d": json.dumps({"Object": {"recordsTotal": len(BR_ROWS), "data": BR_ROWS}})})
    return httpx.Response(404)


def combined_handler(request: httpx.Request) -> httpx.Response:
    if "bsr.de" in request.url.host:
        return bsr_handler(request)
    return br_handler(request)


@pytest.fixture
def client():
    with httpx.Client(transport=httpx.MockTransport(combined_handler)) as c:
        yield c


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REFRESH_INTERVAL_HOURS", "0")
    monkeypatch.delenv("BR_USERNAME", raising=False)
    monkeypatch.delenv("BR_PASSWORD", raising=False)
    return tmp_path
