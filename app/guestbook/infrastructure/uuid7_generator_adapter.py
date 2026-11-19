"""Identifiers, as version 7 UUIDs."""

import uuid


class Uuid7GeneratorAdapter:
    """Implements UuidGeneratorPort with version 7 UUIDs.

    A version 7 UUID starts with the time it was made, so identifiers made later sort later;
    the rest is random.
    """

    def new_uuid(self) -> uuid.UUID:
        """Return an identifier nobody got before."""
        return uuid.uuid7()
