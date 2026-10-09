"""Run after installation: python examples/basic.py."""

from fifo_cost import Issue, Receipt, replay

result = replay([
    Receipt(event_id="R1", sequence=1, item_id="SKU-001", currency="PEN", quantity=10, unit_cost_minor=1250),
    Receipt(event_id="R2", sequence=2, item_id="SKU-001", currency="PEN", quantity=5, unit_cost_minor=1400),
    Issue(event_id="I1", sequence=3, item_id="SKU-001", currency="PEN", quantity=12),
])

balance = result.balance("SKU-001", "PEN")
assert balance is not None
print(f"Costo de salida: {result.issues[0].cost_minor}")
print(f"Cantidad restante: {balance.quantity}")
print(f"Valor restante: {balance.value_minor}")
