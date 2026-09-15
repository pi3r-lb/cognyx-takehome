"""Exercise actual Dagster jobs, checks, gating, logging and installed CLI."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import dagster as dg
from cognyx_takehome.definitions import defs
from cognyx_takehome.storage import ingest, status

DATA = Path(__file__).resolve().parents[1] / "data"


class DagsterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.instance = dg.DagsterInstance.ephemeral()
        self.addCleanup(self.instance.dispose)

    def run_job(self, name, ops=None):
        return defs.resolve_job_def(name).execute_in_process(instance=self.instance, raise_on_error=False,
            run_config={"resources": {"store": {"config": {"directory": str(self.directory)}}},
                        "ops": ops or {}, "loggers": {"console": {"config": {"log_level": "CRITICAL"}}}})

    def test_real_jobs_have_checks_warnings_and_materializations(self):
        first = self.run_job("ingest_bom", {"bom_raw": {"config": {"path": str(DATA/"bom.csv"), "variants": str(DATA/"variants.csv")}}})
        self.assertTrue(first.success)
        second = self.run_job("ingest_technical_notes", {"technical_notes_raw": {"config": {"path": str(DATA/"technical_notes.csv")}}})
        self.assertTrue(second.success)
        checks = {e.check_name: e for e in second.get_asset_check_evaluations()}
        self.assertTrue(checks["sqlite_integrity"].passed)
        self.assertTrue(checks["safe_to_use"].passed)
        self.assertTrue(checks["reference_alias"].passed)
        self.assertFalse(checks["missing_values"].passed)
        self.assertFalse(checks["extraction_coverage"].passed)
        self.assertEqual(checks["missing_values"].severity, dg.AssetCheckSeverity.WARN)
        self.assertTrue(second.asset_materializations_for_node("quality_summary"))
        self.assertEqual(status(self.directory)["counts"]["included_bom_rows"], 117)
        events = [json.loads(line) for line in (self.directory/"logs/ingestion.jsonl").read_text().splitlines()]
        self.assertTrue(any(e["event"] == "import_completed" and e["run_id"] == second.run_id for e in events))
        self.assertTrue(any(e["event"] == "reconciliation_completed" and e["duration_ms"] >= 0 for e in events))
        for e in events:
            self.assertIn("timestamp", e)
            self.assertNotIn("text", e)

    def test_failed_check_blocks_downstream_summary(self):
        with (DATA/"bom.csv").open() as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        rows[0]["quantity"] = "not-a-number"
        path = self.directory/"bad-numeric.csv"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)
        ingest(self.directory, "bom", path, DATA/"variants.csv")
        ingest(self.directory, "technical-notes", DATA/"technical_notes.csv")
        result = self.run_job("reconcile")
        self.assertFalse(result.success)
        checks = {e.check_name: e for e in result.get_asset_check_evaluations()}
        self.assertFalse(checks["safe_to_use"].passed)
        self.assertFalse(result.asset_materializations_for_node("quality_summary"))
        self.assertFalse(any(e.is_step_start and e.step_key == "quality_summary" for e in result.all_events))

    def test_failed_import_is_logged_and_preserves_data(self):
        ingest(self.directory, "bom", DATA/"bom.csv", DATA/"variants.csv")
        result = self.run_job("ingest_bom", {"bom_raw": {"config": {
            "path": str(self.directory/"missing.csv"), "variants": str(DATA/"variants.csv"), "override": True}}})
        self.assertFalse(result.success)
        self.assertEqual(status(self.directory)["counts"]["raw_bom_rows"], 118)
        events = [json.loads(line) for line in (self.directory/"logs/ingestion.jsonl").read_text().splitlines()]
        self.assertTrue(any(e["event"] == "pipeline_step_failed" and e["run_id"] == result.run_id for e in events))

    def test_notes_first_is_successful_but_readiness_is_incomplete(self):
        first = self.run_job("ingest_technical_notes", {"technical_notes_raw": {"config": {"path": str(DATA/"technical_notes.csv")}}})
        self.assertTrue(first.success)
        checks = {e.check_name: e for e in first.get_asset_check_evaluations()}
        self.assertFalse(checks["safe_to_use"].passed)
        self.assertEqual(checks["safe_to_use"].severity, dg.AssetCheckSeverity.WARN)
        self.assertFalse(status(self.directory)["inputs_complete"])
        second = self.run_job("ingest_bom", {"bom_raw": {"config": {"path": str(DATA/"bom.csv"), "variants": str(DATA/"variants.csv")}}})
        self.assertTrue(second.success)
        self.assertTrue(status(self.directory)["inputs_complete"])
        self.assertEqual(status(self.directory)["counts"]["included_bom_rows"], 117)

    def test_installed_cli_contract(self):
        cli = str(Path(sys.executable).with_name("cognyx-takehome"))
        for args in (["--help"], ["ingest", "bom", "--help"], ["ingest", "technical-notes", "--help"]):
            result = subprocess.run([cli, *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([cli, "status", "--data-dir", str(self.directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"]["raw_bom_rows"], 0)
        self.assertIn("enabled: false", (self.directory/"dagster/dagster.yaml").read_text())


if __name__ == "__main__":
    unittest.main()
