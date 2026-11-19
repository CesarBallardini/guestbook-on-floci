"""The time, from the machine's clock."""

from datetime import UTC, datetime


class SystemClockAdapter:
    """Implements ClockPort with the clock of the machine the guestbook runs on."""

    def now_datetime_utc(self) -> datetime:
        """Return the present moment, aware, in UTC."""
        return datetime.now(UTC)
