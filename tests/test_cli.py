import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fifo_cost.cli import main
from fifo_cost import InvalidEventError, events_from_document, replay, result_to_document

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "basic.json"


def run_cli(source=None, *args):
    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, "-m", "fifo_cost", *args], input=source,
        capture_output=True, text=True, env=env, check=False,
    )


class SerializationTests(unittest.TestCase):
    def test_example_and_output_are_json_compatible(self):
        events = events_from_document(json.loads(EXAMPLE.read_text(encoding="utf-8")))
        output = result_to_document(replay(events))
        self.assertEqual(json.loads(json.dumps(output)), output)
        self.assertEqual(output["schema_version"], 1)
        self.assertEqual(output["issues"][0]["cost_minor"], 15300)
        self.assertEqual(output["balances"][0]["value_minor"], 4200)
        self.assertEqual(output["balances"][0]["layers"][0]["value_minor"], 4200)
        self.assertEqual(output["issues"][0]["allocations"][0]["cost_minor"], 12500)

    def test_bad_document_shapes(self):
        for document in (None, [], {}, {"events": [] , "ignored": 1}, {"events": {}}, {"events": None}):
            with self.subTest(document=document):
                with self.assertRaises(InvalidEventError):
                    events_from_document(document)

    def test_bad_event_shapes(self):
        for event in (None, [], {}, {"type": "transfer"}, {"type": []}, {"type": "issue"}):
            with self.subTest(event=event):
                with self.assertRaises(InvalidEventError):
                    events_from_document({"events": [event]})

    def test_unknown_fields_rejected(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][0]["date"] = "2026-01-01"
        with self.assertRaises(InvalidEventError):
            events_from_document(document)

    def test_issue_cannot_supply_unit_cost(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][2]["unit_cost_minor"] = 100
        with self.assertRaises(InvalidEventError):
            events_from_document(document)

    def test_validation_error_identifies_event_index(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][1]["quantity"] = True
        with self.assertRaisesRegex(InvalidEventError, r"events\[1\].*quantity"):
            events_from_document(document)

    def test_document_does_not_alias_result(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        events = events_from_document(document)
        document["events"][0]["quantity"] = 1
        result = replay(events)
        output = result_to_document(result)
        output["issues"][0]["allocations"][0]["quantity"] = 99
        self.assertEqual(result.issues[0].allocations[0].quantity, 10)


class CliTests(unittest.TestCase):
    def assert_error(self, process, code, exit_code=2):
        self.assertEqual(process.returncode, exit_code, process.stderr)
        self.assertEqual(process.stdout, "")
        self.assertNotIn("Traceback", process.stderr)
        self.assertEqual(json.loads(process.stderr)["error"]["code"], code)

    def test_file_input(self):
        process = run_cli(None, str(EXAMPLE))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertEqual(json.loads(process.stdout)["issues"][0]["cost_minor"], 15300)

    def test_stdin_matches_file_and_pretty_output(self):
        source = EXAMPLE.read_text(encoding="utf-8")
        default = run_cli(source)
        explicit = run_cli(source, "-", "--pretty")
        file_output = run_cli(None, str(EXAMPLE))
        for process in (default, explicit, file_output):
            self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(default.stdout, file_output.stdout)
        self.assertEqual(json.loads(default.stdout), json.loads(explicit.stdout))
        self.assertGreater(len(explicit.stdout.splitlines()), 1)

    def test_empty_events(self):
        process = run_cli('{"events": []}')
        self.assertEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout), {
            "schema_version": 1, "event_count": 0, "issues": [], "balances": [], "totals": [],
        })

    def test_malformed_json(self):
        for source in ("", "{", '{"events":[]} extra'):
            with self.subTest(source=source):
                self.assert_error(run_cli(source), "invalid_json")

    def test_nonstandard_json_numbers_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.assert_error(run_cli('{"events":' + constant + '}'), "invalid_event")

    def test_duplicate_json_keys_rejected_at_any_depth(self):
        for source in ('{"events":[],"events":[]}', '{"events":[{"type":"receipt","type":"issue"}]}'):
            with self.subTest(source=source):
                self.assert_error(run_cli(source), "invalid_event")

    def test_boolean_and_decimal_input_rejected(self):
        for value in (True, 1.5, "10", -1, 0):
            document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
            document["events"][0]["quantity"] = value
            with self.subTest(value=value):
                self.assert_error(run_cli(json.dumps(document)), "invalid_event")

    def test_insufficient_stock_returns_no_partial_result(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][2]["quantity"] = 16
        self.assert_error(run_cli(json.dumps(document)), "insufficient_stock")

    def test_duplicate_event_error_code(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][1]["event_id"] = "R1"
        self.assert_error(run_cli(json.dumps(document)), "duplicate_event")

    def test_order_error_code(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        document["events"][1]["sequence"] = 1
        self.assert_error(run_cli(json.dumps(document)), "event_order")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assert_error(run_cli(None, str(Path(directory) / "missing.json")), "input_error", 1)

    def test_invalid_utf8_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(b"\xff")
            self.assert_error(run_cli(None, str(path)), "input_error", 1)

    def test_unicode_identifiers_round_trip(self):
        document = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for event in document["events"]:
            event["item_id"] = "Café peruano"
        process = run_cli(json.dumps(document))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["balances"][0]["item_id"], "Café peruano")

    def test_stdout_failure_returns_io_error(self):
        class FailingOutput(io.StringIO):
            def write(self, value):
                raise OSError("Output unavailable")

        output = FailingOutput()
        stderr = io.StringIO()
        with patch("sys.stdin", io.StringIO('{"events": []}')), patch("sys.stdout", output), patch("sys.stderr", stderr):
            self.assertEqual(main([]), 1)
        self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], "output_error")
        self.assertTrue(output.closed)

    @unittest.skipUnless(os.name == "posix", "POSIX pipe semantics")
    def test_closed_stdout_pipe_has_stable_exit_code(self):
        env = os.environ.copy()
        read_fd, write_fd = os.pipe()
        os.close(read_fd)
        try:
            process = subprocess.run(
                [sys.executable, "-m", "fifo_cost"], input='{"events": []}',
                stdout=write_fd, stderr=subprocess.PIPE, text=True, env=env, check=False,
            )
        finally:
            os.close(write_fd)
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertEqual(json.loads(process.stderr)["error"]["code"], "output_error")
        self.assertNotIn("Exception ignored", process.stderr)

    def test_help(self):
        process = run_cli(None, "--help")
        self.assertEqual(process.returncode, 0)
        self.assertIn("fifo-cost", process.stdout)

    def test_unknown_argument(self):
        process = run_cli(None, "--unknown")
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, "")
        self.assertIn("usage:", process.stderr)


if __name__ == "__main__":
    unittest.main()
