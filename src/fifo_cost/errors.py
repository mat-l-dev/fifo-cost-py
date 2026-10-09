"""Stable exception types for invalid event streams."""


class FifoError(ValueError):
    """Base error for FIFO input that cannot be valued."""

    code = "fifo_error"


class InvalidEventError(FifoError):
    """An event or JSON document does not satisfy the input contract."""

    code = "invalid_event"


class DuplicateEventError(FifoError):
    """An event identifier has already occurred in the stream."""

    code = "duplicate_event"


class EventOrderError(FifoError):
    """Event sequences are not strictly increasing in input order."""

    code = "event_order"


class InsufficientStockError(FifoError):
    """An issue would consume more stock than its item/currency holds."""

    code = "insufficient_stock"

    def __init__(
        self,
        *,
        event_id: str,
        item_id: str,
        currency: str,
        requested: int,
        available: int,
    ) -> None:
        self.event_id = event_id
        self.item_id = item_id
        self.currency = currency
        self.requested = requested
        self.available = available
        super().__init__(
            f"Event {event_id!r}: requested {requested} of {item_id!r} "
            f"in {currency}, available {available}"
        )
