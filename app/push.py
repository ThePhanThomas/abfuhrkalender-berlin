"""Web Push reminders the evening before a pickup.

How it works: each browser/iPhone that switches reminders on registers a
"subscription" (an https URL at Apple/Google/Mozilla plus two keys). We store
those in DATA_DIR/push.json. Once a day, at the configured time, the server
checks whether anything is picked up tomorrow and sends one encrypted message
to every subscription. The server only makes outgoing requests, so this also
works when the phone is not in the home network.

The VAPID key pair identifies this server towards the push services. It is
generated on first use and stored in DATA_DIR/vapid.json (not a user secret,
but never logged or sent to the UI except the public half). It can also be
provided via the environment (VAPID_PRIVATE_KEY, PEM).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02
from pywebpush import WebPushException, webpush

from app import store
from app.models import CATEGORIES

log = logging.getLogger("abfuhrkalender")
TZ = ZoneInfo("Europe/Berlin")
_lock = threading.Lock()


# ---------- keys ----------
def _private_pem() -> bytes:
    env = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if env:
        return env.replace("\\n", "\n").encode()
    path = store.data_dir() / "vapid.json"
    with _lock:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["private_pem"].encode()
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        path.write_text(json.dumps({"private_pem": pem.decode()}), encoding="utf-8")
        with_restricted_permissions(path)
        return pem


def with_restricted_permissions(path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:  # e.g. on file systems without Unix permissions
        pass


def public_key() -> str:
    """Public key in the format the browser expects (base64url, uncompressed point)."""
    key = serialization.load_pem_private_key(_private_pem(), password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _vapid() -> Vapid02:
    return Vapid02.from_pem(_private_pem())


def _subject() -> str:
    # Apple wants a "sub" claim with mailto: or https:. No personal address here;
    # can be overridden via VAPID_SUBJECT.
    return os.environ.get("VAPID_SUBJECT", "mailto:abfuhrkalender@example.com")


# ---------- subscriptions ----------
def _load() -> dict:
    path = store.data_dir() / "push.json"
    if not path.exists():
        return {"subscriptions": [], "last_sent": None}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    path = store.data_dir() / "push.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def subscriptions() -> list[dict]:
    with _lock:
        return _load()["subscriptions"]


DEFAULT_PREFS = {"nag": False, "out_notice": False}


def _prefs(sub: dict) -> dict:
    return {**DEFAULT_PREFS, **(sub.get("prefs") or {})}


def add_subscription(sub: dict) -> None:
    with _lock:
        data = _load()
        old = next((s for s in data["subscriptions"] if s["endpoint"] == sub["endpoint"]), None)
        if old and old.get("prefs"):  # re-subscribing keeps this device's options
            sub = {**sub, "prefs": old["prefs"]}
        data["subscriptions"] = [s for s in data["subscriptions"] if s["endpoint"] != sub["endpoint"]]
        data["subscriptions"].append(sub)
        _save(data)


def set_prefs(endpoint: str, changes: dict) -> dict | None:
    """Change (or with empty `changes` only read) a device's options; None if unknown."""
    with _lock:
        data = _load()
        sub = next((s for s in data["subscriptions"] if s["endpoint"] == endpoint), None)
        if sub is None:
            return None
        if changes:
            sub["prefs"] = {**_prefs(sub), **{k: bool(v) for k, v in changes.items() if k in DEFAULT_PREFS}}
            _save(data)
        return _prefs(sub)


def remove_subscription(endpoint: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["subscriptions"])
        data["subscriptions"] = [s for s in data["subscriptions"] if s["endpoint"] != endpoint]
        _save(data)
        return len(data["subscriptions"]) < before


# ---------- sending ----------
class PushError(Exception):
    """Message is shown in the UI."""


def send(sub: dict, payload: dict) -> None:
    """Send one message. Raises PushError; removes subscriptions the push service
    reports as gone (404/410, e.g. app deleted from the home screen)."""
    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_vapid(),
            vapid_claims={"sub": _subject()},
            ttl=12 * 3600,
            timeout=15,
        )
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):
            remove_subscription(sub["endpoint"])
            raise PushError("Dieses Gerät ist nicht mehr für Erinnerungen angemeldet. Bitte neu einschalten.") from e
        log.warning("Push fehlgeschlagen (Status %s)", status)
        raise PushError("Die Erinnerung konnte nicht verschickt werden. Später noch einmal versuchen.") from e
    except Exception as e:  # network errors etc.
        log.warning("Push fehlgeschlagen: %s", type(e).__name__)
        raise PushError("Der Push-Dienst ist gerade nicht erreichbar.") from e


WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
SOURCE_LABELS = {
    "bsr": "BSR (Hausmüll, Bio, Wertstoffe)",
    "berlin_recycling": "Papier (Berlin Recycling)",
    "paper_manual": "Papier (eigener Turnus)",
}
ALERT_FROM, ALERT_TO = 8, 21  # Berlin time, no alerts at night


def _fmt(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day:02d}.{d.month:02d}."


def reminder_for(day: date) -> dict | None:
    """Message for pickups on `day` (only the categories shown in the app), or None."""
    cfg = store.load_config()
    # Schon rausgestellte (oder abgeholte) Tonnen brauchen keine Erinnerung mehr.
    marked = set(store.load_marks(day).get(day.isoformat(), {}))
    wanted = set(cfg["categories"]) - marked
    cats: list[str] = []
    for p in store.all_pickups(store.load_data()):
        if p.date == day and p.category in wanted and p.category not in cats:
            cats.append(p.category)
    if not cats:
        return None
    what = _names(cats)
    body = "Tonne heute Abend rausstellen." if len(cats) == 1 else "Tonnen heute Abend rausstellen."
    moved = next(
        (
            p.moved_from
            for p in store.all_pickups(store.load_data())
            if p.date == day and p.category in wanted and p.moved_from
        ),
        None,
    )
    if moved:
        body += f" Achtung, verschoben von {WEEKDAYS[moved.weekday()]}."
    return {
        "title": f"Morgen: {what}",
        "body": body,
        "tag": f"abfuhr-{day.isoformat()}",
    }


def _names(cats: list[str]) -> str:
    names = [CATEGORIES.get(c, c) for c in cats]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " und " + names[-1]


def _parse_time(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def run_due(now: datetime | None = None) -> int:
    """Send today's evening reminder if it is due and not yet sent. Returns the
    number of devices reached. Called every minute by the background loop."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    cfg = store.load_config()
    h, m = _parse_time(cfg.get("notify_time") or "18:00")
    today = now.date()
    if (now.hour, now.minute) < (h, m):
        return 0
    with _lock:
        data = _load()
        if data.get("last_sent") == today.isoformat() or not data["subscriptions"]:
            return 0
        data["last_sent"] = today.isoformat()  # mark first: never send twice, even if a send fails
        _save(data)
        subs = list(data["subscriptions"])
    message = reminder_for(today + timedelta(days=1))
    if not message:
        return 0
    sent = 0
    for sub in subs:
        try:
            send(sub, message)
            sent += 1
        except PushError:
            pass
    log.info("Erinnerung an %d Gerät(e) verschickt", sent)
    return sent


def _collect_alerts(data: dict, today: date) -> list[dict]:
    """Work out which alerts are new and record them in `data` (push.json content)."""
    cfg = store.load_config()
    wanted = set(cfg["categories"])
    pickups_data = store.load_data()
    messages: list[dict] = []

    # 1. failing sources
    sources = pickups_data.get("sources", {})
    alerted: dict = data.setdefault("failure_alerted", {})
    for name in [n for n in alerted if n not in sources]:
        del alerted[name]
    for name, src in sources.items():
        label = SOURCE_LABELS.get(name, name)
        if src.get("ok") is False and int(src.get("fail_count") or 0) >= 2:
            since = src.get("failed_since") or ""
            if alerted.get(name) != since:
                alerted[name] = since
                try:
                    shown = datetime.fromisoformat(since).astimezone(TZ).strftime("%d.%m.")
                except ValueError:
                    shown = "einiger Zeit"
                messages.append(
                    {
                        "title": f"Abruf klappt nicht: {label}",
                        "body": f"Seit {shown} schlagen die Abrufe fehl: {src.get('error')}. "
                        "Die bisherigen Termine bleiben sichtbar.",
                        "tag": f"abruf-{name}",
                    }
                )
        elif src.get("ok") is True and name in alerted:
            del alerted[name]
            messages.append(
                {"title": f"Abruf klappt wieder: {label}", "body": "Die Termine sind wieder aktuell.", "tag": f"abruf-{name}"}
            )

    # 2a. moved dates announced by the source (moved_from)
    announced = [k for k in data.get("moved_announced", []) if k.split("|")[0] >= today.isoformat()]
    horizon = today + timedelta(days=7)
    for p in store.all_pickups(pickups_data):
        if not p.moved_from or p.category not in wanted or p.date < today:
            continue
        key = f"{p.date.isoformat()}|{p.category}"
        if min(p.date, p.moved_from) > horizon or key in announced:
            continue
        announced.append(key)
        messages.append(
            {
                "title": f"Verschoben: {CATEGORIES.get(p.category, p.category)}",
                "body": f"Abholung am {_fmt(p.date)} statt {_fmt(p.moved_from)}",
                "tag": f"verschoben-{p.category}-{p.date.isoformat()}",
            }
        )
    data["moved_announced"] = announced

    # 2b. changes found by comparing fetches
    sent_keys = [k for k in data.get("changes_sent", []) if k.split("|")[1] >= today.isoformat()]
    for c in pickups_data.get("changes", []):
        if c["category"] not in wanted or c["old"] < today.isoformat():
            continue
        key = f"{c['category']}|{c['old']}|{c.get('new') or ''}"
        if key in sent_keys:
            continue
        sent_keys.append(key)
        old = date.fromisoformat(c["old"])
        name = CATEGORIES.get(c["category"], c["category"])
        if c.get("new"):
            body = f"Jetzt am {_fmt(date.fromisoformat(c['new']))} statt {_fmt(old)}"
        else:
            body = f"Die Abholung am {_fmt(old)} entfällt laut {c.get('provider') or 'Anbieter'}."
        messages.append(
            {"title": f"Termin geändert: {name}", "body": body, "tag": f"geaendert-{c['category']}-{c['old']}"}
        )
    data["changes_sent"] = sent_keys
    return messages


def run_alerts(now: datetime | None = None) -> int:
    """Send alerts (failing sources, moved dates) to all devices, 08:00-21:00 Berlin
    time only. Returns the number of messages delivered (device x message)."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    if not (ALERT_FROM <= now.hour < ALERT_TO):
        return 0
    with _lock:
        data = _load()
        if not data["subscriptions"]:
            return 0
        messages = _collect_alerts(data, now.date())
        _save(data)  # mark first: never send twice
        subs = list(data["subscriptions"])
    sent = 0
    for message in messages:
        for sub in subs:
            try:
                send(sub, message)
                sent += 1
            except PushError:
                pass
    if messages:
        log.info("%d Hinweis(e) verschickt, %d Zustellung(en)", len(messages), sent)
    return sent


# ---------- bins: second reminder and "put out" notice ----------
NAG_WINDOW_MIN = 60  # after a restart, send a missed second reminder only within this window
OUT_DELAY = timedelta(minutes=2)  # undo within this time = no notice (tapped by mistake)
OUT_MAX_AGE = timedelta(minutes=30)  # older notices are dropped (e.g. server was down)
QUIET_FROM, QUIET_TO = 23, 6  # no "put out" notices at night


def nag_for(day: date) -> dict | None:
    """Second reminder for pickups on `day` whose bins are not marked yet, or None."""
    cfg = store.load_config()
    marked = set(store.load_marks(day).get(day.isoformat(), {}))
    cats: list[str] = []
    for p in store.all_pickups(store.load_data()):
        if p.date == day and p.category in cfg["categories"] and p.category not in marked and p.category not in cats:
            cats.append(p.category)
    if not cats:
        return None
    return {
        "title": f"Noch nicht draußen: {_names(cats)}",
        "body": "Morgen ist Abholung. " + ("Tonne" if len(cats) == 1 else "Tonnen") + " heute Abend noch rausstellen.",
        "tag": f"abfuhr-{day.isoformat()}",  # replaces the first reminder on the device
    }


def run_nag(now: datetime | None = None) -> int:
    """At the nag time: remind devices that asked for it about bins not yet put out.
    Only after the first reminder (nag_time later than notify_time) and once a day."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    cfg = store.load_config()
    nag = _parse_time(cfg.get("nag_time") or "21:00")
    if nag <= _parse_time(cfg.get("notify_time") or "18:00"):
        return 0
    minutes = (now.hour * 60 + now.minute) - (nag[0] * 60 + nag[1])
    if not 0 <= minutes < NAG_WINDOW_MIN:
        return 0
    today = now.date()
    with _lock:
        data = _load()
        subs = [s for s in data["subscriptions"] if _prefs(s)["nag"]]
        if data.get("nag_sent") == today.isoformat() or not subs:
            return 0
        data["nag_sent"] = today.isoformat()  # mark first: never send twice
        _save(data)
    message = nag_for(today + timedelta(days=1))
    if not message:
        return 0
    sent = 0
    for sub in subs:
        try:
            send(sub, message)
            sent += 1
        except PushError:
            pass
    log.info("Nachhak-Erinnerung an %d Gerät(e) verschickt", sent)
    return sent


def queue_out_notice(day: date, category: str, endpoint: str | None, now: datetime | None = None) -> None:
    """Remember that a bin was just marked as put out; sent by run_out_notices after
    OUT_DELAY, unless the mark was taken back. Nothing is queued if no device wants it."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    with _lock:
        data = _load()
        if not any(_prefs(s)["out_notice"] for s in data["subscriptions"]):
            return
        pending = [
            q for q in data.get("out_pending", []) if not (q["date"] == day.isoformat() and q["category"] == category)
        ]
        pending.append({"date": day.isoformat(), "category": category, "at": now.isoformat(), "from": endpoint})
        data["out_pending"] = pending
        _save(data)


def run_out_notices(now: datetime | None = None) -> int:
    """Tell the other devices which bins were put out. Returns deliveries."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    with _lock:
        data = _load()
        pending = data.get("out_pending", [])
        if not pending:
            return 0
        due = [q for q in pending if now - datetime.fromisoformat(q["at"]) >= OUT_DELAY]
        if not due:
            return 0
        data["out_pending"] = [q for q in pending if q not in due]
        _save(data)
        subs = [s for s in data["subscriptions"] if _prefs(s)["out_notice"]]
    if now.hour >= QUIET_FROM or now.hour < QUIET_TO:
        return 0
    marks = store.load_marks(now.date())
    groups: dict[tuple[str, str | None], list[str]] = {}
    for q in due:
        if now - datetime.fromisoformat(q["at"]) > OUT_MAX_AGE:
            continue
        if marks.get(q["date"], {}).get(q["category"]) != "out":  # taken back or already collected
            continue
        groups.setdefault((q["date"], q["from"]), []).append(q["category"])
    sent = 0
    for (day_iso, sender), cats in groups.items():
        day = date.fromisoformat(day_iso)
        when = "heute" if day == now.date() else "morgen" if day == now.date() + timedelta(days=1) else f"am {_fmt(day)}"
        message = {
            "title": f"Steht draußen: {_names(cats)}",
            "body": f"Abholung {when}. Rausstellen ist erledigt.",
            "tag": f"draussen-{day_iso}",
        }
        for sub in subs:
            if sub["endpoint"] == sender:
                continue
            try:
                send(sub, message)
                sent += 1
            except PushError:
                pass
    return sent
