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


def add_subscription(sub: dict) -> None:
    with _lock:
        data = _load()
        data["subscriptions"] = [s for s in data["subscriptions"] if s["endpoint"] != sub["endpoint"]]
        data["subscriptions"].append(sub)
        _save(data)


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


def reminder_for(day: date) -> dict | None:
    """Message for pickups on `day` (only the categories shown in the app), or None."""
    cfg = store.load_config()
    wanted = set(cfg["categories"])
    cats: list[str] = []
    for p in store.all_pickups(store.load_data()):
        if p.date == day and p.category in wanted and p.category not in cats:
            cats.append(p.category)
    if not cats:
        return None
    names = [CATEGORIES.get(c, c) for c in cats]
    what = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " und " + names[-1]
    return {
        "title": f"Morgen: {what}",
        "body": "Tonne heute Abend rausstellen." if len(cats) == 1 else "Tonnen heute Abend rausstellen.",
        "tag": f"abfuhr-{day.isoformat()}",
    }


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
