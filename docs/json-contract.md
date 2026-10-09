# Contrato JSON / JSON contract

## Entrada / Input

Un único documento JSON UTF-8. La raíz contiene exactamente `events`, una lista de eventos. Un documento vacío válido es `{"events": []}`. Los campos son obligatorios y los campos adicionales se rechazan.

One UTF-8 JSON document. The root contains exactly `events`, an array. All event fields below are required; additional fields are rejected.

```json
{
  "events": [
    {
      "type": "receipt",
      "event_id": "R1",
      "sequence": 1,
      "item_id": "SKU-001",
      "currency": "PEN",
      "quantity": 10,
      "unit_cost_minor": 1250
    },
    {
      "type": "receipt",
      "event_id": "R2",
      "sequence": 2,
      "item_id": "SKU-001",
      "currency": "PEN",
      "quantity": 5,
      "unit_cost_minor": 1400
    },
    {
      "type": "issue",
      "event_id": "I1",
      "sequence": 3,
      "item_id": "SKU-001",
      "currency": "PEN",
      "quantity": 12
    }
  ]
}
```

`type` admite solo `receipt` e `issue`. Una salida no acepta `unit_cost_minor`: su costo se calcula. Secuencia/cantidad deben ser enteros positivos y costo entero no negativo. No se convierten cadenas, booleanos o números decimales a enteros.

`type` is either `receipt` or `issue`. Issues must not include `unit_cost_minor`; their cost is derived. Sequence/quantity must be positive integers, and unit cost a nonnegative integer. Strings, booleans, and decimal numbers are not coerced.

## Salida / Output

```json
{
  "schema_version": 1,
  "event_count": 3,
  "issues": [
    {
      "event_id": "I1",
      "sequence": 3,
      "item_id": "SKU-001",
      "currency": "PEN",
      "quantity": 12,
      "cost_minor": 15300,
      "allocations": [
        {"receipt_id": "R1", "receipt_sequence": 1, "quantity": 10, "unit_cost_minor": 1250, "cost_minor": 12500},
        {"receipt_id": "R2", "receipt_sequence": 2, "quantity": 2, "unit_cost_minor": 1400, "cost_minor": 2800}
      ]
    }
  ],
  "balances": [
    {
      "item_id": "SKU-001",
      "currency": "PEN",
      "quantity": 3,
      "value_minor": 4200,
      "layers": [
        {"receipt_id": "R2", "receipt_sequence": 2, "quantity": 3, "unit_cost_minor": 1400, "value_minor": 4200}
      ]
    }
  ],
  "totals": [
    {"currency": "PEN", "received_value_minor": 19500, "issued_value_minor": 15300, "balance_value_minor": 4200}
  ]
}
```

- `issues`: orden original de salidas / original issue order
- `allocations` y `layers`: orden de antigüedad de las entradas / oldest receipt first
- `balances`: orden lexicográfico por `(item_id, currency)` / sorted by exact pair
- `totals`: orden lexicográfico por moneda, sin total combinado / sorted by currency, never combined

No se usan timestamps, números aleatorios ni datos del entorno para generar el resultado. La salida no reproduce todos los eventos de entrada; conserve el documento original para repetir el cálculo. Los enteros de Python son de precisión arbitraria, pero un consumidor JSON debe evitar convertir importes a coma flotante; JavaScript pierde exactitud por encima de `2^53 - 1`. La CLI conserva los límites normales de conversión de enteros JSON de la versión de Python, sin prometer tamaño de entrada ilimitado.

No timestamps, randomness, or environment data enter the result. Output does not reproduce every input event; retain the original document for replay. Python integers have arbitrary precision, but JSON consumers must avoid floating-point conversion; JavaScript loses integer precision beyond `2^53 - 1`. The CLI retains the Python version's normal JSON integer-conversion limits and does not promise unlimited input size.

## Errores / Errors

```json
{"error": {"code": "insufficient_stock", "message": "Event 'I1': requested 16 of 'SKU-001' in PEN, available 15"}}
```

Los códigos estables son `invalid_event`, `duplicate_event`, `event_order`, `insufficient_stock`, `invalid_json`, `input_error` y `output_error`. Los textos de `message` son descriptivos y no forman una interfaz estable. Las claves JSON repetidas y constantes no estándar generan `invalid_event`.

Stable codes are listed above; human-readable `message` strings are not a stable interface. Duplicate JSON keys and nonstandard numeric constants produce `invalid_event`.

Errores de datos: stderr JSON y código de salida 2; problemas de E/S: código 1. Los errores de argumentos de CLI usan texto de `argparse`, también con código 2. Ante un fallo de escritura, el sistema operativo puede haber enviado parte del texto: la atomicidad de cálculo no garantiza entrega atómica al destino de stdout.

Data errors use JSON stderr and exit 2; I/O failures use exit 1. CLI argument errors use `argparse` text and exit 2. An output failure can occur after the operating system delivered part of the text: atomic calculation does not guarantee atomic transport to stdout.
