"""Unit tests for the identifier adapter."""

import pytest

from guestbook.infrastructure.uuid7_generator_adapter import Uuid7GeneratorAdapter

pytestmark = pytest.mark.unit

UUID_VERSION = 7


def test_the_identifiers_are_version_7_uuids() -> None:
    assert Uuid7GeneratorAdapter().new_uuid().version == UUID_VERSION


def test_no_two_identifiers_are_the_same_and_later_ones_sort_later() -> None:
    generator = Uuid7GeneratorAdapter()

    identifiers = [generator.new_uuid() for _ in range(100)]

    assert len(set(identifiers)) == len(identifiers)
    assert identifiers == sorted(identifiers)
