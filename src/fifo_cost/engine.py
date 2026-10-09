"""Single-pass, side-effect-free replay of an explicitly ordered event stream."""

from collections import deque
from collections.abc import Iterable

from .errors import (
    DuplicateEventError,
    EventOrderError,
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


def replay(events: Iterable[Event]) -> LedgerResult:
    """Value events in input order, requiring strictly increasing sequences.

    Gaps in sequences are allowed. Event IDs must be unique across the entire
    stream, including different items and currencies. Nothing is persisted:
    a failure raises a typed error and returns no partial result. Replaying
    the same immutable events always yields an equal result.
    """
    layers: dict[tuple[str, str], deque[Layer]] = {}
    available: dict[tuple[str, str], int] = {}
    received_values: dict[str, int] = {}
    issued_values: dict[str, int] = {}
    seen_ids: set[str] = set()
    accepted: list[Event] = []
    issues: list[IssueCost] = []
    previous_sequence = 0

    for event in events:
        if type(event) not in (Receipt, Issue):
            raise InvalidEventError("events must contain Receipt or Issue instances")
        if event.event_id in seen_ids:
            raise DuplicateEventError(f"Duplicate event_id: {event.event_id!r}")
        if event.sequence <= previous_sequence:
            raise EventOrderError(
                f"Event {event.event_id!r}: sequence {event.sequence} must be "
                f"greater than previous sequence {previous_sequence}"
            )
        key = (event.item_id, event.currency)
        if isinstance(event, Receipt):
            queue = layers.setdefault(key, deque())
            queue.append(
                Layer(event.event_id, event.sequence, event.quantity, event.unit_cost_minor)
            )
            available[key] = available.get(key, 0) + event.quantity
            received_values[event.currency] = (
                received_values.get(event.currency, 0)
                + event.quantity * event.unit_cost_minor
            )
        else:
            stock = available.get(key, 0)
            if event.quantity > stock:
                raise InsufficientStockError(
                    event_id=event.event_id,
                    item_id=event.item_id,
                    currency=event.currency,
                    requested=event.quantity,
                    available=stock,
                )
            queue = layers[key]
            needed = event.quantity
            allocations: list[Allocation] = []
            while needed:
                layer = queue.popleft()
                consumed = min(needed, layer.quantity)
                allocations.append(
                    Allocation(
                        layer.receipt_id,
                        layer.receipt_sequence,
                        consumed,
                        layer.unit_cost_minor,
                    )
                )
                if consumed < layer.quantity:
                    queue.appendleft(
                        Layer(
                            layer.receipt_id,
                            layer.receipt_sequence,
                            layer.quantity - consumed,
                            layer.unit_cost_minor,
                        )
                    )
                needed -= consumed
            issue = IssueCost(
                event.event_id,
                event.sequence,
                event.item_id,
                event.currency,
                event.quantity,
                tuple(allocations),
            )
            issues.append(issue)
            available[key] -= event.quantity
            issued_values[event.currency] = (
                issued_values.get(event.currency, 0) + issue.cost_minor
            )
        seen_ids.add(event.event_id)
        previous_sequence = event.sequence
        accepted.append(event)

    balances = tuple(
        StockBalance(item_id, currency, tuple(layers[(item_id, currency)]))
        for item_id, currency in sorted(layers)
    )
    remaining_values: dict[str, int] = {}
    for balance in balances:
        remaining_values[balance.currency] = (
            remaining_values.get(balance.currency, 0) + balance.value_minor
        )
    totals = tuple(
        CurrencyTotals(
            currency,
            received_values[currency],
            issued_values.get(currency, 0),
            remaining_values.get(currency, 0),
        )
        for currency in sorted(received_values)
    )
    return LedgerResult(tuple(accepted), tuple(issues), balances, totals)
