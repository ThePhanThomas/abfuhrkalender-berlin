"""FastAPI app: serves the UI and a small JSON API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import ics, push, refresh, store
from app.models import CATEGORIES, SourceError
from app.sources import bsr

log = logging.getLogger("abfuhrkalender")
STATIC = Path(__file__).parent / "static"
REFRESH_HOURS = float(os.environ.get("REFRESH_INTERVAL_HOURS", "168"))
RETRY_HOURS = 6.0
PUSH_ENABLED = os.environ.get("PUSH_ENABLED", "1") != "0"


def _refresh_due(data: dict, now: datetime) -> bool:
    """Stored data older than REFRESH_HOURS, or (if a source failed) older than RETRY_HOURS."""
    updated = data.get("updated_at")
    if not updated:
        return True
    age_h = (now - datetime.fromisoformat(updated)).total_seconds() / 3600
    limit = REFRESH_HOURS
    if any(s.get("ok") is False for s in data.get("sources", {}).values()):
        limit = min(limit, RETRY_HOURS)
    return age_h >= limit


async def _auto_refresh_loop() -> None:
    """Refresh automatically when the stored data is old enough (see _refresh_due)."""
    while True:
        try:
            if store.load_config().get("address") and _refresh_due(store.load_data(), datetime.now(timezone.utc)):
                log.info("Automatischer Abruf startet")
                await asyncio.to_thread(refresh.run)
        except Exception:  # never let the loop die
            log.exception("Automatischer Abruf fehlgeschlagen")
        await asyncio.sleep(3600)


async def _push_loop() -> None:
    """Check once a minute whether the evening reminder or other messages are due."""
    while True:
        try:
            await asyncio.to_thread(push.run_due)
        except Exception:  # never let the loop die
            log.exception("Erinnerung fehlgeschlagen")
        try:
            await asyncio.to_thread(push.run_alerts)
        except Exception:
            log.exception("Hinweise fehlgeschlagen")
        try:
            await asyncio.to_thread(push.run_nag)
        except Exception:
            log.exception("Nachhak-Erinnerung fehlgeschlagen")
        try:
            await asyncio.to_thread(push.run_out_notices)
        except Exception:
            log.exception("Rausstell-Mitteilung fehlgeschlagen")
        await asyncio.sleep(60)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = []
    if REFRESH_HOURS > 0:
        tasks.append(asyncio.create_task(_auto_refresh_loop()))
    if PUSH_ENABLED:
        tasks.append(asyncio.create_task(_push_loop()))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Abfuhrkalender", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def no_stale_assets(request, call_next):
    """Without Cache-Control browsers cache HTML/CSS/JS heuristically and may
    combine a new page with old CSS/JS after an update. "no-cache" makes them
    revalidate every time (cheap thanks to ETag/Last-Modified)."""
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    return response


class Address(BaseModel):
    key: str = Field(min_length=5)
    label: str


class Paper(BaseModel):
    mode: Literal["portal", "manual", "off"] = "off"
    first_date: Optional[date] = None
    interval_weeks: int = Field(4, ge=1, le=12)


class Config(BaseModel):
    address: Optional[Address] = None
    categories: list[str]
    paper: Paper
    notify_time: str = Field("18:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    nag_time: str = Field("21:00", pattern=r"^(([01][0-9]|20):[0-5][0-9]|21:00)$")


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushSubscription(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=1000)
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str


class PushPrefs(BaseModel):
    endpoint: str
    nag: Optional[bool] = None  # None = unverändert lassen
    out_notice: Optional[bool] = None


class Mark(BaseModel):
    date: date
    category: str
    status: Optional[Literal["out", "done"]] = None  # None = Markierung entfernen
    endpoint: Optional[str] = None  # Push-Anmeldung des markierenden Geräts (bekommt keine Meldung)


MARK_DAYS_AHEAD = 7  # weiter voraus ergibt "rausgestellt" keinen Sinn


def _today() -> date:
    return datetime.now(push.TZ).date()


def _state() -> dict:
    cfg = store.load_config()
    data = store.load_data()
    return {
        "config": cfg,
        "categories": CATEGORIES,
        "portal_configured": refresh.portal_configured(),
        "updated_at": data.get("updated_at"),
        "sources": {
            name: {k: v for k, v in src.items() if k != "pickups"} for name, src in data.get("sources", {}).items()
        },
        "pickups": [p.to_dict() for p in store.all_pickups(data)],
        "marks": store.load_marks(_today()),
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/sw.js")
def service_worker():
    # Served from the root so that it controls the whole app (scope "/").
    return FileResponse(STATIC / "sw.js", media_type="text/javascript")


@app.get("/api/state")
def get_state():
    return _state()


@app.get("/api/address/search")
def address_search(street: str = Query(..., min_length=2), number: str = Query(..., min_length=1)):
    with httpx.Client(headers={"User-Agent": "abfuhrkalender/1.0"}) as client:
        try:
            return bsr.search_address(client, street, number)
        except SourceError as e:
            raise HTTPException(502, str(e)) from e


@app.put("/api/config")
def put_config(cfg: Config):
    unknown = [c for c in cfg.categories if c not in CATEGORIES]
    if unknown:
        raise HTTPException(422, f"Unbekannte Kategorien: {unknown}")
    if cfg.paper.mode == "manual" and not cfg.paper.first_date:
        raise HTTPException(422, "Für den manuellen Papier-Turnus fehlt das Datum einer Abholung.")
    old = store.load_config()
    new = cfg.model_dump(mode="json")
    store.save_config(new)
    # Different address or paper settings -> refetch right away
    if old.get("address") != new.get("address") or old.get("paper") != new.get("paper"):
        refresh.run()
    return _state()


@app.post("/api/refresh")
async def post_refresh():
    if not store.load_config().get("address"):
        raise HTTPException(400, "Bitte zuerst eine Adresse einrichten.")
    await asyncio.to_thread(refresh.run)
    return _state()


@app.put("/api/marks")
def put_mark(mark: Mark):
    today = _today()
    if mark.category not in CATEGORIES:
        raise HTTPException(422, "Unbekannte Müllart.")
    if mark.date < today:
        raise HTTPException(422, "Vergangene Abholungen lassen sich nicht mehr markieren.")
    if (mark.date - today).days > MARK_DAYS_AHEAD:
        raise HTTPException(422, "So weit im Voraus lässt sich nichts markieren.")
    before = store.load_marks(today).get(mark.date.isoformat(), {}).get(mark.category)
    marks = store.set_mark(mark.date, mark.category, mark.status, today)
    if mark.status == "out" and before is None:
        push.queue_out_notice(mark.date, mark.category, mark.endpoint)
    return {"marks": marks}


@app.get("/api/calendar.ics")
def calendar_ics(reminder: bool = False, categories: Optional[str] = None):
    cfg = store.load_config()
    wanted = set(categories.split(",")) if categories else set(cfg["categories"])
    pickups = [p for p in store.all_pickups(store.load_data()) if p.category in wanted]
    location = (cfg.get("address") or {}).get("label", "")
    body = ics.build(pickups, location=location, reminder=reminder)
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="abfuhrkalender.ics"'},
    )


@app.get("/api/push/key")
def push_key():
    return {"public_key": push.public_key()}


@app.post("/api/push/subscribe")
def push_subscribe(sub: PushSubscription):
    push.add_subscription(sub.model_dump())
    return {"ok": True}


@app.post("/api/push/unsubscribe")
def push_unsubscribe(body: PushEndpoint):
    push.remove_subscription(body.endpoint)
    return {"ok": True}


@app.post("/api/push/prefs")
def push_prefs(body: PushPrefs):
    """Read (no fields) or change this device's push options."""
    changes = {k: v for k, v in (("nag", body.nag), ("out_notice", body.out_notice)) if v is not None}
    prefs = push.set_prefs(body.endpoint, changes)
    if prefs is None:
        raise HTTPException(404, "Dieses Gerät ist nicht für Erinnerungen angemeldet.")
    return {"prefs": prefs}


@app.post("/api/push/test")
def push_test(body: PushEndpoint):
    sub = next((s for s in push.subscriptions() if s["endpoint"] == body.endpoint), None)
    if not sub:
        raise HTTPException(404, "Dieses Gerät ist nicht für Erinnerungen angemeldet.")
    try:
        push.send(sub, {"title": "Abfuhrkalender", "body": "Erinnerungen funktionieren auf diesem Gerät.", "tag": "test"})
    except push.PushError as e:
        raise HTTPException(502, str(e)) from e
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"ok": True}
