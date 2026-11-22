"""Manual rhythm for Papier (fallback for tenants without portal access).

Generates dates from a start date and an interval in weeks. Holiday shifts are
not applied, so these dates are marked as computed.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models import Pickup

PROVIDER = "Berlin Recycling"


def generate(first: date, interval_weeks: int, start: date, end: date) -> list[Pickup]:
    if interval_weeks < 1:
        return []
    step = timedelta(weeks=interval_weeks)
    d = first
    if d < start:
        d += step * ((start - d) // step)
        if d < start:
            d += step
    out = []
    while d <= end:
        out.append(Pickup(date=d, category="PP", provider=PROVIDER, note="berechnet (ohne Feiertagsverschiebung)"))
        d += step
    return out
