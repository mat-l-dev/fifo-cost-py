# fifo-cost-py

Motor pequeño y determinista de valorización FIFO de inventario para Python 3.12 o superior. Recibe entradas y salidas ordenadas; devuelve costos de salida, capas pendientes y un desglose verificable por entrada de origen.

[English documentation](docs/README.en.md) · [Contrato JSON](docs/json-contract.md) · [Cambios](CHANGELOG.md)

## Alcance

- API tipada con eventos y resultados inmutables; sin dependencias de ejecución
- Cantidades enteras positivas y costo unitario entero en unidades monetarias menores
- Capas FIFO independientes por producto y moneda
- Orden explícito, identificadores únicos y rechazo de stock insuficiente
- CLI con entrada/salida JSON y errores identificables

Esta primera versión es una biblioteca de cálculo en memoria, no un libro contable persistente. No implementa devoluciones, anulaciones, fechas retroactivas, cantidades fraccionarias, conversión de monedas, impuestos ni facturación. No valida normas contables o tributarias de una jurisdicción.

## Instalación local

Desde la raíz del repositorio, con Python 3.12+ y `uv`:

```sh
uv venv
uv pip install .
.venv/bin/fifo-cost examples/basic.json --pretty
```

También puede instalarse con `python -m pip install .` en un entorno virtual. La construcción del paquete utiliza `setuptools`; la biblioteca instalada solo utiliza la biblioteca estándar. Los comandos `.venv/bin/` corresponden a Linux/macOS; en Windows, use `.venv\Scripts\`.

## Uso en Python

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
assert balance.quantity == 3
assert balance.value_minor == 4200
```

La salida consume 10 unidades de R1 a 1250 y 2 unidades de R2 a 1400. Quedan 3 unidades de R2. En PEN, 1250 representa S/ 12,50 si se usan céntimos: el programa no convierte importes ni determina cuántos decimales tiene una moneda.

`result.events`, `result.issues`, `result.balances` y `result.totals` son tuplas. Cada asignación conserva el identificador y la secuencia de la entrada original, la cantidad, el costo unitario y su costo calculado. Los saldos agotados permanecen con cantidad y valor cero, y sin capas. `result.balance(producto, moneda)` devuelve `None` si ese par nunca recibió stock.

## Reglas del dominio

1. `sequence` debe ser un `int` positivo y estrictamente creciente en todo el flujo, incluso entre productos o monedas distintos. Se permiten saltos. Se procesa el orden recibido: nunca se reordena por identificador, costo o fecha.
2. `event_id` debe ser único en todo el flujo. `event_id` e `item_id` son cadenas no vacías, sin espacios al inicio/final ni caracteres de control ASCII. Se preservan mayúsculas, minúsculas y Unicode; no se normalizan identificadores.
3. `quantity` debe ser un `int` positivo. `unit_cost_minor` debe ser un `int` no negativo; cero permite inventario sin costo. Se rechazan `bool`, `float`, `Decimal`, cadenas numéricas y subclases de `int`.
4. `currency` es una etiqueta de tres letras ASCII mayúsculas, por ejemplo `PEN` o `USD`. No se comprueba contra un catálogo ISO ni se convierten monedas.
5. Una salida solo consume capas del mismo par exacto `(item_id, currency)`, comenzando por la entrada más antigua. Dos entradas con el mismo costo conservan capas distintas para la trazabilidad.
6. No se permite stock negativo. Si falla un evento, no se devuelve un resultado parcial ni se modifica un resultado anterior.

Todos los cálculos multiplican y suman enteros. No hay redondeo. Por moneda, el valor total recibido equivale al costo total de salidas más el valor del saldo. Nunca se suman importes de monedas diferentes. Por producto y moneda también se conserva la cantidad recibida menos la salida.

### Inmutabilidad y repetición

`replay(eventos)` acepta un iterable de instancias exactas de `Receipt` o `Issue`. Copia los eventos aceptados a una tupla y crea un resultado independiente. El iterable se consume; si es un generador, no puede deshacerse ese consumo tras un error. El motor no escribe archivos ni usa estado global, red o base de datos.

Para extender una historia:

```python
next_result = replay((*result.events, next_event))
```

Se recalcula la historia completa. Para muchos eventos, es preferible una sola llamada por lote, en lugar de repetir la historia después de cada entrada. La memoria crece con los eventos, las asignaciones y las capas almacenadas. La función no es un almacén transaccional, y no aporta persistencia, concurrencia entre procesos ni protección contra modificaciones deliberadas de objetos desde código Python externo.

## Errores tipados

Todos los errores de dominio heredan de `FifoError`, que a su vez hereda de `ValueError`:

- `InvalidEventError`: campos, tipos o estructura inválidos
- `DuplicateEventError`: identificador repetido
- `EventOrderError`: secuencia repetida o decreciente
- `InsufficientStockError`: stock insuficiente; expone `event_id`, `item_id`, `currency`, `requested` y `available`

Los constructores validan los eventos inmediatamente. `replay` verifica la coherencia del flujo. Los errores de iteradores proporcionados por quien llama no se transforman en errores de dominio.

## CLI

```sh
fifo-cost examples/basic.json --pretty
cat examples/basic.json | fifo-cost
python -m fifo_cost examples/basic.json
```

El resultado JSON completo se escribe en stdout, seguido por una nueva línea. Los errores de datos se escriben como JSON en stderr, sin resultado parcial en stdout. No se crean ni modifican archivos.

- Código `0`: resultado calculado
- Código `2`: JSON o datos de dominio inválidos; también argumentos de CLI inválidos
- Código `1`: error de lectura o escritura

`--help` y los errores de argumentos usan el formato de texto de `argparse`. Las entradas JSON rechazan campos desconocidos, claves repetidas y números no estándar (`NaN`, `Infinity`). Consulte el [contrato JSON](docs/json-contract.md) para las estructuras completas y los códigos de error.

## Verificación local

Sin instalar el paquete ni dependencias de pruebas:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python examples/basic.py
PYTHONPATH=src python -m fifo_cost examples/basic.json --pretty
```

Las pruebas incluyen consumos parciales, agotamiento y reabastecimiento, aislamiento por producto/moneda, entradas inválidas, atomicidad observable, determinismo y CLI. Un oráculo independiente por unidad comprueba 100 flujos reproducibles de 150 eventos cada uno, con conservación de cantidades y valores.

Para construir distribuciones con `uv`:

```sh
uv build
```

No se incluyen workflows de CI ni integraciones remotas. La versión inicial se verifica localmente. La API es preliminar (`0.1.0`) y puede cambiar antes de `1.0`.

## Licencia

La licencia está pendiente de elección por el titular. Esta versión no incluye una concesión de licencia de uso o redistribución.
