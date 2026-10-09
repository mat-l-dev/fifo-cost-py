"""Strict JSON-compatible input and stable versioned output."""

from typing import Any

from .errors import InvalidEventError
from .models import Event, Issue, LedgerResult, Receipt

_COMMON_FIELDS = {"type", "event_id", "sequence", "item_id", "currency", "quantity"}


def events_from_document(document: object) -> tuple[Event, ...]:
    """Parse {"events": [...]} without coercion, aliases, or ignored fields."""
    if not isinstance(document, dict) or set(document) != {"events"}:
        raise InvalidEventError("document must be an object with only the 'events' field")
    if not isinstance(document["events"], list):
        raise InvalidEventError("events must be a JSON array")
    events: list[Event] = []
    for index, value in enumerate(document["events"]):
        if not isinstance(value, dict):
            raise InvalidEventError(f"events[{index}] must be an object")
        kind = value.get("type")
        if kind not in ("receipt", "issue"):
            raise InvalidEventError(f"events[{index}].type must be 'receipt' or 'issue'")
        expected = _COMMON_FIELDS | ({"unit_cost_minor"} if kind == "receipt" else set())
        if set(value) != expected:
            raise InvalidEventError(f"events[{index}] has missing or unknown fields")
        fields = {key: field for key, field in value.items() if key != "type"}
        try:
            event = Receipt(**fields) if kind == "receipt" else Issue(**fields)
        except InvalidEventError as error:
            raise InvalidEventError(f"events[{index}]: {error}") from error
        events.append(event)
    return tuple(events)


def result_to_document(result: LedgerResult) -> dict[str, Any]:
    """Serialize every cost and remaining layer, with deterministic list order."""
    return {
        "schema_version": 1,
        "event_count": len(result.events),
        "issues": [
            {
                "event_id": issue.event_id,
                "sequence": issue.sequence,
                "item_id": issue.item_id,
                "currency": issue.currency,
                "quantity": issue.quantity,
                "cost_minor": issue.cost_minor,
                "allocations": [
                    {
                        "receipt_id": allocation.receipt_id,
                        "receipt_sequence": allocation.receipt_sequence,
                        "quantity": allocation.quantity,
                        "unit_cost_minor": allocation.unit_cost_minor,
                        "cost_minor": allocation.cost_minor,
                    }
                    for allocation in issue.allocations
                ],
            }
            for issue in result.issues
        ],
        "balances": [
            {
                "item_id": balance.item_id,
                "currency": balance.currency,
                "quantity": balance.quantity,
                "value_minor": balance.value_minor,
                "layers": [
                    {
                        "receipt_id": layer.receipt_id,
                        "receipt_sequence": layer.receipt_sequence,
                        "quantity": layer.quantity,
                        "unit_cost_minor": layer.unit_cost_minor,
                        "value_minor": layer.value_minor,
                    }
                    for layer in balance.layers
                ],
            }
            for balance in result.balances
        ],
        "totals": [
            {
                "currency": total.currency,
                "received_value_minor": total.received_value_minor,
                "issued_value_minor": total.issued_value_minor,
                "balance_value_minor": total.balance_value_minor,
            }
            for total in result.totals
        ],
    }
