"""FIFO inventory costing with immutable events and exact integer money."""

from .engine import replay
from .errors import (
    DuplicateEventError,
    EventOrderError,
    FifoError,
    InsufficientStockError,
    InvalidEventError,
)
from .models import (
    Allocation,
    CurrencyTotals,
    Event,
    Issue,
    IssueCost,
    Layer,
    LedgerResult,
    Receipt,
    StockBalance,
)
from .serialization import events_from_document, result_to_document

__version__ = "0.1.0"

__all__ = [
    "Allocation",
    "CurrencyTotals",
    "DuplicateEventError",
    "Event",
    "EventOrderError",
    "FifoError",
    "InsufficientStockError",
    "InvalidEventError",
    "Issue",
    "IssueCost",
    "Layer",
    "LedgerResult",
    "Receipt",
    "StockBalance",
    "events_from_document",
    "replay",
    "result_to_document",
]
