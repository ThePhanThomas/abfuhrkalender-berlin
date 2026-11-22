"""Minimal iCalendar export (all-day events, optional reminder the evening before)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import CATEGORIES, Pickup


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build(pickups: list[Pickup], location: str = "", reminder: bool = False) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//abfuhrkalender//DE",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Abfuhrkalender",
    ]
    for p in pickups:
        name = CATEGORIES.get(p.category, p.category)
        desc = p.provider + (f" – {p.note}" if p.note else "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{p.date.strftime('%Y%m%d')}-{p.category}@abfuhrkalender",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{p.date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(p.date + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(name)}",
            f"DESCRIPTION:{_esc(desc)}",
        ]
        if location:
            lines.append(f"LOCATION:{_esc(location)}")
        if reminder:
            # 6 hours before midnight = 18:00 the evening before
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:Morgen: {_esc(name)}", "TRIGGER:-PT6H", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
