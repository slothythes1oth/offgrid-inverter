"""Generate src/solarmon/data/ontario_holidays.json.

Ontario statutory holidays observed by the Hydro One TOU schedule (holidays
count as off-peak all day). Civic Holiday (August) is intentionally absent:
it is not an Ontario statutory holiday.

Run when the covered range needs extending:
    .venv/Scripts/python scripts/gen_holidays.py 2025 2030
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent.parent / "src" / "solarmon" / "data" / "ontario_holidays.json"


def easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` (Mon=0) of the month."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def victoria_day(year: int) -> date:
    """Monday on or before May 24."""
    d = date(year, 5, 24)
    return d - timedelta(days=(d.weekday() - 0) % 7)


def holidays_for(year: int) -> dict[str, str]:
    gf = easter(year) - timedelta(days=2)
    return {
        f"{year}-01-01": "New Year's Day",
        nth_weekday(year, 2, 0, 3).isoformat(): "Family Day",
        gf.isoformat(): "Good Friday",
        victoria_day(year).isoformat(): "Victoria Day",
        f"{year}-07-01": "Canada Day",
        nth_weekday(year, 9, 0, 1).isoformat(): "Labour Day",
        nth_weekday(year, 10, 0, 2).isoformat(): "Thanksgiving",
        f"{year}-12-25": "Christmas Day",
        f"{year}-12-26": "Boxing Day",
    }


def main() -> None:
    start = int(sys.argv[1]) if len(sys.argv) > 2 else 2025
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 2030
    all_days: dict[str, str] = {}
    for y in range(start, end + 1):
        all_days.update(holidays_for(y))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(sorted(all_days.items())), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(all_days)} holidays ({start}-{end}) to {OUT}")


if __name__ == "__main__":
    main()
