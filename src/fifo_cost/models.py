"""Immutable events and audit results; all money is in minor units."""

from dataclasses import dataclass
from typing import TypeAlias

from .errors import InvalidEventError


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InvalidEventError(f"{field} must be a nonempty, trimmed string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise InvalidEventError(f"{field} must not contain control characters")


def _integer(value: object, field: str, *, minimum: int) -> None:
    # bool is an int subclass, but True is never a valid stock quantity.
    if type(value) is not int or value < minimum:
        raise InvalidEventError(f"{field} must be an integer >= {minimum}")


def _event_fields(
    event_id: object,
    sequence: object,
    item_id: object,
    currency: object,
    quantity: object,
) -> None:
    _text(event_id, "event_id")
    _text(item_id, "item_id")
    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not all("A" <= character <= "Z" for character in currency)
    ):
        raise InvalidEventError("currency must contain exactly three uppercase ASCII letters")
    _integer(sequence, "sequence", minimum=1)
    _integer(quantity, "quantity", minimum=1)


@dataclass(frozen=True, slots=True, kw_only=True)
class Receipt:
    """Add a FIFO layer. Zero unit cost is allowed; zero quantity is not."""

    event_id: str
    sequence: int
    item_id: str
    currency: str
    quantity: int
    unit_cost_minor: int

    def __post_init__(self) -> None:
        _event_fields(
            self.event_id, self.sequence, self.item_id, self.currency, self.quantity
        )
        _integer(self.unit_cost_minor, "unit_cost_minor", minimum=0)


@dataclass(frozen=True, slots=True, kw_only=True)
class Issue:
    """Consume oldest available layers for one exact item/currency pair."""

    event_id: str
    sequence: int
    item_id: str
    currency: str
    quantity: int

    def __post_init__(self) -> None:
        _event_fields(
            self.event_id, self.sequence, self.item_id, self.currency, self.quantity
        )


Event: TypeAlias = Receipt | Issue


@dataclass(frozen=True, slots=True)
class Allocation:
    """One source receipt's contribution to the cost of an issue."""

    receipt_id: str
    receipt_sequence: int
    quantity: int
    unit_cost_minor: int

    @property
    def cost_minor(self) -> int:
        return self.quantity * self.unit_cost_minor


@dataclass(frozen=True, slots=True)
class IssueCost:
    """FIFO valuation and source-layer audit trail for an issue."""

    event_id: str
    sequence: int
    item_id: str
    currency: str
    quantity: int
    allocations: tuple[Allocation, ...]

    @property
    def cost_minor(self) -> int:
        return sum(allocation.cost_minor for allocation in self.allocations)


@dataclass(frozen=True, slots=True)
class Layer:
    """Unconsumed quantity of an original receipt."""

    receipt_id: str
    receipt_sequence: int
    quantity: int
    unit_cost_minor: int

    @property
    def value_minor(self) -> int:
        return self.quantity * self.unit_cost_minor


@dataclass(frozen=True, slots=True)
class StockBalance:
    """Remaining layers, oldest first, for one exact item/currency pair."""

    item_id: str
    currency: str
    layers: tuple[Layer, ...]

    @property
    def quantity(self) -> int:
        return sum(layer.quantity for layer in self.layers)

    @property
    def value_minor(self) -> int:
        return sum(layer.value_minor for layer in self.layers)


@dataclass(frozen=True, slots=True)
class CurrencyTotals:
    """Value conservation totals within a single currency."""

    currency: str
    received_value_minor: int
    issued_value_minor: int
    balance_value_minor: int


@dataclass(frozen=True, slots=True)
class LedgerResult:
    """Immutable replay output. Monetary values are never mixed across currencies."""

    events: tuple[Event, ...]
    issues: tuple[IssueCost, ...]
    balances: tuple[StockBalance, ...]
    totals: tuple[CurrencyTotals, ...]

    def balance(self, item_id: str, currency: str) -> StockBalance | None:
        """Find an exact pair; return None when it never received stock."""
        return next(
            (
                balance
                for balance in self.balances
                if balance.item_id == item_id and balance.currency == currency
            ),
            None,
        )
