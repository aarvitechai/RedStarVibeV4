"""Pure slot arithmetic (no I/O), so it is easy to unit test across time zones."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

STEP_MIN = 30
LEAD_MIN = 30  # earliest bookable slot is at least this far in the future


@dataclass(frozen=True)
class Candidate:
    starts_at: datetime  # UTC
    ends_at: datetime  # UTC, end of the service
    blocks_until: datetime  # UTC, end including buffer (what the exclusion constraint covers)


def candidates(
    day: date,
    tz: ZoneInfo,
    intervals: Iterable[tuple[time, time]],
    duration_min: int,
    buffer_min: int,
    now: datetime,
    step_min: int = STEP_MIN,
    lead_min: int = LEAD_MIN,
) -> list[Candidate]:
    duration, buffer, step = timedelta(minutes=duration_min), timedelta(minutes=buffer_min), timedelta(minutes=step_min)
    earliest = now + timedelta(minutes=lead_min)
    out: list[Candidate] = []
    for opens, closes in sorted(intervals):
        start = datetime.combine(day, opens, tzinfo=tz)
        close = datetime.combine(day, closes, tzinfo=tz)
        while start + duration <= close:
            if start >= earliest:
                s = start.astimezone(ZoneInfo("UTC"))
                out.append(Candidate(s, s + duration, s + duration + buffer))
            start += step
    return out


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open [start, end) overlap, matching the Postgres tstzrange default '[)'."""
    return a_start < b_end and b_start < a_end
