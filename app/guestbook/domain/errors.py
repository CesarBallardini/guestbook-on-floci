"""The errors the guestbook's domain speaks of."""


class InvalidMessageError(ValueError):
    """A new message breaks one of the guestbook's rules. The text says which."""


class StorageError(Exception):
    """A place where messages or pictures are kept could not do what an output port asked.

    Every adapter turns its own failures (the database's, S3's) into this one, so that what
    calls a port never needs to know which adapter is behind it.
    """
