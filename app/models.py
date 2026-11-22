"""Shared data types."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Optional

# Category codes used throughout the app. BSR uses HM/BI/WS/LT/WB natively.
CATEGORIES: dict[str, str] = {
    "HM": "Hausmüll",
    "BI": "Biogut",
    "WS": "Wertstoffe",
    "PP": "Papier",
    "GL": "Glas",
    "LT": "Laubtonne",
    "WB": "Weihnachtsbaum",
    "SO": "Sonstiges",
}

DEFAULT_CATEGORIES = ["HM", "BI", "WS", "PP"]


@dataclass(frozen=True)
class Pickup:
    date: date
    category: str
    provider: str
    moved_from: Optional[date] = None
    note: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["moved_from"] = self.moved_from.isoformat() if self.moved_from else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Pickup":
        return cls(
            date=date.fromisoformat(d["date"]),
            category=d["category"],
            provider=d.get("provider", ""),
            moved_from=date.fromisoformat(d["moved_from"]) if d.get("moved_from") else None,
            note=d.get("note", ""),
        )


class SourceError(Exception):
    """Raised by a source when fetching fails; the message is shown in the UI."""
