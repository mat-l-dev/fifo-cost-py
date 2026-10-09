# fifo-cost-py

A small, deterministic FIFO inventory-costing engine for Python 3.12+. An explicitly ordered stream of receipts and issues produces issue costs, remaining layers, and a receipt-level audit trail.

[Documentación en español](../README.md) · [JSON contract](json-contract.md) · [Changelog](../CHANGELOG.md)

## Scope

- Typed API with immutable events and results; no runtime dependencies
- Positive integer quantities and integer minor-unit costs
- Separate FIFO queues for each exact item/currency pair
- Explicit ordering, unique event IDs, and atomic rejection of insufficient stock
- JSON CLI with stable error codes

This is an in-memory calculation library, not a persistent accounting ledger. Returns, reversals, backdating, fractional quantities, currency conversion, taxes, and invoicing are outside this release. It does not validate jurisdiction-specific accounting or tax requirements.

## Install locally

From the repository root, using Python 3.12+ and `uv`:

```sh
uv venv
uv pip install .
.venv/bin/fifo-cost examples/basic.json --pretty
```

Alternatively, run `python -m pip install .` in a virtual environment. Building uses `setuptools`; the installed library only uses Python's standard library. The `.venv/bin/` paths above are for Linux/macOS; Windows uses `.venv\Scripts\`.

## Python API

```python
from fifo_cost import Issue, Receipt, replay

result = replay([
    Receipt(
        event_id="R1", sequence=1, item_id="SKU-001", currency="PEN",
        quantity=10, unit_cost_minor=1250,
    ),
    Receipt(
        event_id="R2", sequence=2, item_id="SKU-001", currency="PEN",
        quantity=5, unit_cost_minor=1400,
    ),
    Issue(
        event_id="I1", sequence=3, item_id="SKU-001", currency="PEN",
        quantity=12,
    ),
])

assert result.issues[0].cost_minor == 15300
assert [a.quantity for a in result.issues[0].allocations] == [10, 2]
balance = result.balance("SKU-001", "PEN")
assert balance is not None
assert (balance.quantity, balance.value_minor) == (3, 4200)
```

The issue consumes 10 units from R1 and 2 from R2, leaving 3 units from R2. If PEN amounts use céntimos, 1250 means S/ 12.50. The library does not infer currency precision or convert monetary units.

Results expose tuples of `events`, `issues`, `balances`, and per-currency `totals`. Each allocation identifies the original receipt, its sequence, consumed quantity, unit cost, and calculated cost. Fully depleted pairs remain in balances with zero quantity/value and no layers. `result.balance(item_id, currency)` returns `None` for a pair that never received stock.

## Input and ordering rules

1. `sequence` is a positive built-in `int`, strictly increasing across the entire stream, including different items/currencies. Gaps are valid. Input order is authoritative; the engine never sorts events.
2. `event_id` is globally unique. Event/item IDs must be nonempty strings without surrounding whitespace or ASCII control characters. Case and Unicode are preserved without normalization.
3. Quantities are positive built-in integers. Unit costs are nonnegative built-in integers; zero-cost stock is valid. Booleans, floats, `Decimal`, numeric strings, and integer subclasses are rejected.
4. Currency is exactly three uppercase ASCII letters, such as `PEN` or `USD`. This validates the label format, not membership in an ISO registry.
5. Issues consume only the same exact `(item_id, currency)` pair, oldest receipt first. Equal-cost receipts remain distinct layers for auditability.
6. Negative stock is rejected. Failure returns no partial result and cannot change a previously returned result.

All arithmetic is integer multiplication and addition, so there is no rounding. Within each currency, received value equals issued cost plus remaining value. Different currencies are never added together. Quantities also reconcile per item/currency pair.

## Replay and immutability

`replay(events)` accepts an iterable of exact `Receipt`/`Issue` instances and returns an independent immutable snapshot. Inputs are retained in a tuple. The iterable is consumed; external generator consumption cannot be rolled back after failure. No global state, database, filesystem writes, or network calls are involved.

Extend a history with `replay((*result.events, next_event))`. This recalculates the entire history, so prefer one batch replay over repeated appends for large streams. Memory grows with retained events, allocations, and layers. This is not a transactional store and provides no persistence, cross-process concurrency, or defense against deliberate object manipulation by external Python code.

## Errors

Domain exceptions inherit from `FifoError`, a `ValueError` subclass:

- `InvalidEventError`: invalid fields, types, or input structure
- `DuplicateEventError`: repeated event ID
- `EventOrderError`: repeated or decreasing sequence
- `InsufficientStockError`: exposes `event_id`, `item_id`, `currency`, `requested`, and `available`

Constructors validate individual events; replay validates the stream. Exceptions raised by caller-supplied iterators propagate unchanged.

## CLI

```sh
fifo-cost examples/basic.json --pretty
cat examples/basic.json | fifo-cost
python -m fifo_cost examples/basic.json
```

A complete JSON result goes to stdout with a trailing newline. Data errors produce one JSON error object on stderr and no partial result on stdout. No files are written.

Exit codes: `0` success, `2` invalid JSON/domain input or CLI arguments, `1` input/output failure. Help and argument errors use `argparse` text rather than JSON. JSON rejects unknown fields, duplicate keys, and nonstandard numeric constants. See the [JSON contract](json-contract.md) for full structures and error codes.

## Local verification

No installation or test dependencies are required:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python examples/basic.py
PYTHONPATH=src python -m fifo_cost examples/basic.json --pretty
```

Tests cover partial consumption, depletion/restocking, item/currency isolation, invalid input, observable atomicity, determinism, and CLI behavior. An independent unit-by-unit oracle checks 100 reproducible streams of 150 events each, including quantity and value conservation.

Build distributions with `uv build`. No CI workflows or remote integrations are included. This initial release is verified locally. The API is preliminary (`0.1.0`) and may change before `1.0`.

## License

A license has not yet been selected by the rights holder. This release does not include a license grant for use or redistribution.
