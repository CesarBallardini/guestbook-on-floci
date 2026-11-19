"""Unit tests for the clock adapter."""

from datetime import UTC, timedelta

import pytest

from guestbook.infrastructure.system_clock_adapter import SystemClockAdapter

pytestmark = pytest.mark.unit


def test_the_clock_tells_an_aware_time_in_utc() -> None:
    assert SystemClockAdapter().now_datetime_utc().tzinfo is UTC


def test_the_clock_does_not_go_backwards() -> None:
    clock = SystemClockAdapter()
    first_datetime_utc = clock.now_datetime_utc()

    elapsed_duration = clock.now_datetime_utc() - first_datetime_utc

    assert timedelta(0) <= elapsed_duration < timedelta(minutes=1)
