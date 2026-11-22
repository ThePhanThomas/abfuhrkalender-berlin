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

BR_ROWS = [
    {"Task Date": "2026-01-09", "Material Description": "Papier, Pappe, Kartonagen 240 l"},
    {"Task Date": "2026-02-06", "Material Description": "Papier, Pappe, Kartonagen 240 l"},
    {"Task Date": "2026-02-10", "Material Description": "Glas weiß"},
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
    path = request.url.path
    if path == "/":
        return httpx.Response(302, headers={"Location": "/Login.aspx"})
    if path.endswith("/Login.aspx/Auth"):
        inner = {"Error": False} if login_ok else {"Error": True, "Message": "Access denied"}
        return httpx.Response(200, json={"d": json.dumps(inner)})
    if path.endswith("/GetDashboard"):
        return httpx.Response(200, json={"d": "{}"})
    if path.endswith("/GetDatasetTableHead"):
        return httpx.Response(200, json={"d": json.dumps({"Object": {"data": BR_ROWS}})})
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
