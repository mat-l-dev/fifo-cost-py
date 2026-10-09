import random
import unittest
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

from fifo_cost import (
    DuplicateEventError,
    EventOrderError,
    FifoError,
    InsufficientStockError,
    InvalidEventError,
    Issue,
    Receipt,
    replay,
    result_to_document,
)


def receipt(event_id="R1", sequence=1, item_id="A", currency="PEN", quantity=10, unit_cost_minor=1250):
    return Receipt(
        event_id=event_id, sequence=sequence, item_id=item_id,
        currency=currency, quantity=quantity, unit_cost_minor=unit_cost_minor,
    )


def issue(event_id="I1", sequence=2, item_id="A", currency="PEN", quantity=1):
    return Issue(
        event_id=event_id, sequence=sequence, item_id=item_id,
        currency=currency, quantity=quantity,
    )


class EventValidationTests(unittest.TestCase):
    def test_invalid_quantities(self):
        for value in (0, -1, True, False, 1.0, "1", None, Decimal("1")):
            for constructor in (receipt, issue):
                with self.subTest(value=value, constructor=constructor.__name__):
                    with self.assertRaises(InvalidEventError):
                        constructor(quantity=value)

    def test_invalid_sequences(self):
        for value in (0, -1, True, False, 1.0, "1", None):
            for constructor in (receipt, issue):
                with self.subTest(value=value, constructor=constructor.__name__):
                    with self.assertRaises(InvalidEventError):
                        constructor(sequence=value)

    def test_invalid_costs(self):
        for value in (-1, True, False, 1.0, "1", None, Decimal("1")):
            with self.subTest(value=value):
                with self.assertRaises(InvalidEventError):
                    receipt(unit_cost_minor=value)

    def test_invalid_identifiers(self):
        for field in ("event_id", "item_id"):
            for value in ("", " ", " A", "A ", "A\nB", "A\x00B", "A\x7fB", 1, None):
                for constructor in (receipt, issue):
                    with self.subTest(field=field, value=value, constructor=constructor.__name__):
                        with self.assertRaises(InvalidEventError):
                            constructor(**{field: value})

    def test_invalid_currencies(self):
        for value in ("pen", "PeN", "PE", "PENN", " PE", "P€N", "123", "ＰＥＮ", 123, None):
            for constructor in (receipt, issue):
                with self.subTest(value=value, constructor=constructor.__name__):
                    with self.assertRaises(InvalidEventError):
                        constructor(currency=value)

    def test_identifiers_preserve_case_and_unicode(self):
        event = receipt(event_id="Recepción-1", item_id="Café de Perú")
        self.assertEqual(event.event_id, "Recepción-1")
        self.assertEqual(event.item_id, "Café de Perú")

    def test_events_are_immutable(self):
        event = receipt()
        with self.assertRaises(FrozenInstanceError):
            event.quantity = 2
        self.assertFalse(hasattr(event, "__dict__"))

    def test_integer_subclasses_are_not_accepted(self):
        class CustomInteger(int):
            pass
        with self.assertRaises(InvalidEventError):
            receipt(quantity=CustomInteger(1))

    def test_event_subclasses_are_not_replayed(self):
        class CustomReceipt(Receipt):
            pass
        event = CustomReceipt(
            event_id="R1", sequence=1, item_id="A", currency="PEN",
            quantity=1, unit_cost_minor=1,
        )
        with self.assertRaises(InvalidEventError):
            replay([event])


class ReplayTests(unittest.TestCase):
    def test_documented_example(self):
        result = replay([
            receipt(),
            receipt("R2", 2, quantity=5, unit_cost_minor=1400),
            issue(sequence=3, quantity=12),
        ])
        output = result.issues[0]
        self.assertEqual(output.cost_minor, 15300)
        self.assertEqual(
            [(a.receipt_id, a.receipt_sequence, a.quantity, a.cost_minor) for a in output.allocations],
            [("R1", 1, 10, 12500), ("R2", 2, 2, 2800)],
        )
        balance = result.balance("A", "PEN")
        self.assertEqual((balance.quantity, balance.value_minor), (3, 4200))
        self.assertEqual(balance.layers[0].receipt_id, "R2")
        total = result.totals[0]
        self.assertEqual((total.received_value_minor, total.issued_value_minor, total.balance_value_minor),
                         (19500, 15300, 4200))

    def test_empty_replay(self):
        result = replay([])
        self.assertEqual((result.events, result.issues, result.balances, result.totals), ((), (), (), ()))
        self.assertIsNone(result.balance("missing", "PEN"))

    def test_exact_depletion_retains_zero_balance(self):
        result = replay([receipt(quantity=2), issue(quantity=2)])
        balance = result.balance("A", "PEN")
        self.assertEqual((balance.quantity, balance.value_minor, balance.layers), (0, 0, ()))

    def test_receipt_after_depletion(self):
        result = replay([
            receipt(quantity=2), issue(quantity=2),
            receipt("R2", 3, quantity=1, unit_cost_minor=500),
            issue("I2", 4),
        ])
        self.assertEqual(result.issues[-1].cost_minor, 500)
        self.assertEqual(result.issues[-1].allocations[0].receipt_id, "R2")

    def test_partial_layer_used_before_newer_layer(self):
        result = replay([
            receipt(quantity=3, unit_cost_minor=10),
            receipt("R2", 2, quantity=3, unit_cost_minor=20),
            issue("I1", 3, quantity=2),
            issue("I2", 4, quantity=3),
        ])
        self.assertEqual([x.cost_minor for x in result.issues], [20, 50])
        self.assertEqual([a.quantity for a in result.issues[1].allocations], [1, 2])
        self.assertEqual(result.balance("A", "PEN").value_minor, 20)

    def test_equal_cost_layers_remain_distinct_for_audit(self):
        result = replay([receipt(quantity=1), receipt("R2", 2, quantity=1), issue(sequence=3, quantity=2)])
        self.assertEqual([a.receipt_id for a in result.issues[0].allocations], ["R1", "R2"])

    def test_zero_cost_stock_is_valid(self):
        result = replay([receipt(unit_cost_minor=0), issue()])
        self.assertEqual(result.issues[0].cost_minor, 0)
        self.assertEqual(result.balance("A", "PEN").value_minor, 0)

    def test_large_integer_values_stay_exact(self):
        quantity, cost = 10**30, 10**25 + 7
        result = replay([receipt(quantity=quantity, unit_cost_minor=cost), issue(quantity=quantity - 1)])
        self.assertEqual(result.issues[0].cost_minor, (quantity - 1) * cost)
        self.assertEqual(result.balance("A", "PEN").value_minor, cost)

    def test_items_and_currencies_are_isolated(self):
        result = replay([
            receipt("R1", 1, "A", "PEN", 2, 100),
            receipt("R2", 2, "B", "PEN", 3, 200),
            receipt("R3", 3, "A", "USD", 4, 300),
            issue("I1", 4, "A", "PEN", 1),
        ])
        self.assertEqual([(b.item_id, b.currency, b.quantity, b.value_minor) for b in result.balances],
                         [("A", "PEN", 1, 100), ("A", "USD", 4, 1200), ("B", "PEN", 3, 600)])
        self.assertEqual([(t.currency, t.received_value_minor, t.issued_value_minor, t.balance_value_minor)
                          for t in result.totals], [("PEN", 800, 100, 700), ("USD", 1200, 0, 1200)])

    def test_wrong_currency_cannot_supply_issue(self):
        with self.assertRaises(InsufficientStockError) as caught:
            replay([receipt(currency="USD"), issue(currency="PEN")])
        self.assertEqual(caught.exception.available, 0)

    def test_wrong_item_cannot_supply_issue(self):
        with self.assertRaises(InsufficientStockError) as caught:
            replay([receipt(item_id="A"), issue(item_id="a")])
        self.assertEqual(caught.exception.available, 0)

    def test_insufficient_stock_has_context(self):
        with self.assertRaises(InsufficientStockError) as caught:
            replay([receipt(quantity=2), issue(quantity=3)])
        error = caught.exception
        self.assertEqual((error.event_id, error.item_id, error.currency, error.requested, error.available),
                         ("I1", "A", "PEN", 3, 2))
        self.assertIsInstance(error, FifoError)

    def test_issue_before_receipt_is_rejected(self):
        with self.assertRaises(InsufficientStockError):
            replay([issue(sequence=1), receipt(sequence=2)])

    def test_duplicate_ids_across_items_and_types_are_rejected(self):
        for duplicate in (receipt("R1", 2, "B", "USD"), issue("R1", 2)):
            with self.subTest(event=duplicate):
                with self.assertRaises(DuplicateEventError):
                    replay([receipt(), duplicate])

    def test_decreasing_or_equal_sequence_is_rejected(self):
        for sequence in (1, 2):
            with self.subTest(sequence=sequence):
                with self.assertRaises(EventOrderError):
                    replay([receipt(sequence=2), receipt("R2", sequence, item_id="B")])

    def test_sequence_gaps_are_allowed(self):
        result = replay([receipt(sequence=5), issue(sequence=20)])
        self.assertEqual(result.issues[0].sequence, 20)

    def test_unknown_event_type_rejected(self):
        for value in (None, {}, "receipt", 1, True):
            with self.subTest(value=value):
                with self.assertRaises(InvalidEventError):
                    replay([value])

    def test_replay_is_deterministic_and_accepts_generators(self):
        events = [receipt(), issue()]
        self.assertEqual(replay(events), replay(event for event in events))
        self.assertEqual(result_to_document(replay(events)), result_to_document(replay(events)))

    def test_failed_replay_does_not_corrupt_prior_result_or_input(self):
        events = [receipt(quantity=2), issue(quantity=1)]
        before = replay(events)
        for invalid in (issue("I2", 3, quantity=2), issue("I1", 3), issue("I2", 2)):
            with self.subTest(event=invalid):
                with self.assertRaises(FifoError):
                    replay([*events, invalid])
                self.assertEqual(replay(events), before)
                self.assertEqual(before.balance("A", "PEN").quantity, 1)
        self.assertEqual(events[0].quantity, 2)

    def test_snapshot_does_not_alias_input_list(self):
        events = [receipt()]
        result = replay(events)
        events.append(issue())
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.balance("A", "PEN").quantity, 10)
        with self.assertRaises(FrozenInstanceError):
            result.balances[0].layers[0].quantity = 0

    def test_immutable_append_by_replay(self):
        old = replay([receipt(quantity=2)])
        new = replay((*old.events, issue(quantity=1)))
        self.assertEqual(old.balance("A", "PEN").quantity, 2)
        self.assertEqual(new.balance("A", "PEN").quantity, 1)

    def test_replacing_an_event_revalidates_it(self):
        with self.assertRaises(InvalidEventError):
            replace(receipt(), quantity=0)

    def test_randomized_unit_reference_and_conservation(self):
        # Independent unit-by-unit oracle: 100 seeded streams, 150 events each.
        for seed in range(100):
            rng = random.Random(seed)
            events = []
            units = {}
            expected_issues = []
            received = {}
            issued = {}
            input_quantity = {}
            output_quantity = {}
            for sequence in range(1, 151):
                key = (rng.choice(("A", "B", "C")), rng.choice(("PEN", "USD")))
                stock = units.setdefault(key, [])
                if not stock or rng.random() < 0.6:
                    quantity, cost = rng.randint(1, 8), rng.randint(0, 2000)
                    event_id = f"R{sequence}"
                    events.append(receipt(event_id, sequence, *key, quantity, cost))
                    stock.extend([(event_id, sequence, cost)] * quantity)
                    received[key] = received.get(key, 0) + quantity * cost
                    input_quantity[key] = input_quantity.get(key, 0) + quantity
                else:
                    quantity = rng.randint(1, min(10, len(stock)))
                    event_id = f"I{sequence}"
                    events.append(issue(event_id, sequence, *key, quantity))
                    consumed = stock[:quantity]
                    del stock[:quantity]
                    cost = sum(unit[2] for unit in consumed)
                    expected_issues.append((event_id, cost, consumed))
                    issued[key] = issued.get(key, 0) + cost
                    output_quantity[key] = output_quantity.get(key, 0) + quantity
            result = replay(events)
            with self.subTest(seed=seed):
                for actual, (event_id, cost, consumed) in zip(result.issues, expected_issues, strict=True):
                    self.assertEqual((actual.event_id, actual.cost_minor), (event_id, cost))
                    audited_units = [
                        (allocation.receipt_id, allocation.receipt_sequence, allocation.unit_cost_minor)
                        for allocation in actual.allocations for _ in range(allocation.quantity)
                    ]
                    self.assertEqual(audited_units, consumed)
                    self.assertEqual(sum(a.quantity for a in actual.allocations), actual.quantity)
                for key, stock in units.items():
                    balance = result.balance(*key)
                    self.assertEqual(balance.quantity, len(stock))
                    self.assertEqual(balance.quantity, input_quantity[key] - output_quantity.get(key, 0))
                    self.assertEqual(balance.value_minor, sum(unit[2] for unit in stock))
                    self.assertEqual(received[key], issued.get(key, 0) + balance.value_minor)
                    self.assertTrue(all(layer.quantity > 0 for layer in balance.layers))
                for total in result.totals:
                    self.assertEqual(total.received_value_minor, total.issued_value_minor + total.balance_value_minor)
                self.assertEqual(result, replay(events))


if __name__ == "__main__":
    unittest.main()
