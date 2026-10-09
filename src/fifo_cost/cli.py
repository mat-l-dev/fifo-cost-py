"""JSON command-line interface. No files are written or external services used."""

import argparse
import json
import sys
from pathlib import Path

from .engine import replay
from .errors import FifoError, InvalidEventError
from .serialization import events_from_document, result_to_document


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEventError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise InvalidEventError(f"Nonstandard JSON number: {value}")


def _error(code: str, message: str) -> None:
    print(json.dumps({"error": {"code": code, "message": message}}), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 2 on invalid input, or 1 on input/output failure."""
    parser = argparse.ArgumentParser(
        prog="fifo-cost",
        description="Value FIFO inventory events using integer minor-unit costs.",
    )
    parser.add_argument("input", nargs="?", default="-", help="UTF-8 JSON file, or - for stdin")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    args = parser.parse_args(argv)
    try:
        source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        _error("input_error", str(error))
        return 1
    try:
        document = json.loads(
            source, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        result = replay(events_from_document(document))
        output = json.dumps(
            result_to_document(result), indent=2 if args.pretty else None, ensure_ascii=True
        )
    except FifoError as error:
        _error(error.code, str(error))
        return 2
    except (ValueError, RecursionError) as error:
        _error("invalid_json", str(error))
        return 2
    try:
        print(output)
        sys.stdout.flush()
    except OSError as error:
        _error("output_error", str(error))
        # Avoid a second failed flush during interpreter shutdown (exit 120).
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 1
    return 0
