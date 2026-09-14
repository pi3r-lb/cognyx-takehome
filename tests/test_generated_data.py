"""Contract checks on published inputs, including deliberate dirty-data cases."""

from collections import Counter, defaultdict
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from cognyx_takehome.generate_data import generate


DATA = Path(__file__).resolve().parents[1] / "data"


def read_csv(name):
    with (DATA / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(raw):
    return Decimal(raw.replace(",", "."))


def ref(raw):
    # Only the explicit NOTE-002 mapping, never general O-to-0 substitution.
    return {" LGT-1O0 ": "LGT-100"}.get(raw, raw)


class GeneratedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_csv("bom.csv")
        cls.variants = read_csv("variants.csv")
        cls.notes = read_csv("technical_notes.csv")
        cls.oracle = json.loads((DATA / "expected/findings.json").read_text(encoding="utf-8"))

    def select(self, variant, parent=None, item=None):
        return [r for r in self.rows if r["variant_id"] == variant
                and (parent is None or ref(r["parent_ref"]) == parent)
                and (item is None or ref(r["item_ref"]) == item)]

    def test_published_files_are_reproducible_and_manifest_hashes_match(self):
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            generate(directory)
            for path in DATA.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (Path(directory) / path.relative_to(DATA)).read_bytes(), str(path))
        for name, details in manifest["files"].items():
            self.assertEqual(details["sha256"], hashlib.sha256((DATA / name).read_bytes()).hexdigest())
            count = len(self.oracle["findings"]) if name.endswith(".json") else len(read_csv(name))
            self.assertEqual(details["records"], count)
        self.assertEqual(manifest["data_status"], "synthetic")

    def test_inventory_and_source_references(self):
        self.assertEqual(len(self.rows), 118)
        self.assertEqual(Counter(r["variant_id"] for r in self.rows), {"REG-A": 39, "REG-B": 40, "REG-C": 39})
        self.assertEqual(len(self.notes), 18)
        self.assertEqual(len({r["row_id"] for r in self.rows}), len(self.rows))
        self.assertEqual(len({(r["source_export_id"], r["source_line"]) for r in self.rows}), len(self.rows))
        self.assertEqual({n["language"] for n in self.notes}, {"en", "fr", "mixed"})
        self.assertTrue(all(None not in r and all(v is not None for v in r.values()) for r in self.rows))

    def test_hierarchies_resolve_without_cycles_or_orphans(self):
        for variant in self.variants:
            rows = self.select(variant["variant_id"])
            root = variant["root_ref"]
            graph = defaultdict(set)
            assemblies = {(root, "A")}
            for r in rows:
                graph[(ref(r["parent_ref"]), r["parent_revision"])].add((ref(r["item_ref"]), r["item_revision"]))
                if r["item_type"] == "assembly":
                    assemblies.add((ref(r["item_ref"]), r["item_revision"]))
            self.assertEqual(len(assemblies), 4)
            self.assertEqual(set(graph), assemblies)
            visited = set()

            def visit(node, ancestors):
                self.assertNotIn(node, ancestors, "unexpected BOM cycle")
                visited.add(node)
                for child in graph.get(node, set()):
                    visit(child, ancestors | {node})

            visit((root, "A"), set())
            self.assertTrue(all((ref(r["item_ref"]), r["item_revision"]) in visited for r in rows))

    def test_oracle_is_separate_and_all_evidence_exists(self):
        row_ids = {r["row_id"] for r in self.rows}
        note_ids = {n["note_id"] for n in self.notes}
        findings = self.oracle["findings"]
        self.assertEqual(len(findings), 16)
        self.assertEqual(len({f["finding_id"] for f in findings}), 16)
        for finding in findings:
            self.assertTrue(set(finding["row_ids"]) <= row_ids)
            self.assertTrue(set(finding["note_ids"]) <= note_ids)
            self.assertTrue(finding["expected_outcome"])
        self.assertFalse({"canonical_ref", "finding_id", "expected_outcome", "category"} & set(self.rows[0]))
        for note in self.notes:
            self.assertTrue(any(r["variant_id"] == note["variant_id"]
                                and ref(r["item_ref"]) == ref(note["applies_to_ref"])
                                and r["item_revision"] == note["applies_to_revision"] for r in self.rows))

    def test_unit_and_decimal_cases_reconcile_without_scaling_dimensions(self):
        a = self.select("REG-A", "LGT-100", "CBL-2C")[0]
        b = self.select("REG-B", "LGT-100", "CBL-2C")[0]
        self.assertEqual((a["uom"], b["uom"]), ("M", "mm"))
        self.assertEqual(number(a["quantity"]), number(b["quantity"]) / 1000)
        frame = self.select("REG-B", "FLT-100", "FLT-FRAME")[0]
        self.assertEqual(number(frame["length"]) * 1000, Decimal("600"))
        self.assertEqual(frame["quantity"], "1")
        self.assertEqual(frame["uom"], "pcs")
        self.assertEqual(number(self.select("REG-B", "FLT-100", "FLT-GASK-EP")[0]["quantity"]), Decimal("2.4"))

    def test_lighting_design_is_shared_after_evidenced_normalization(self):
        def signature(variant):
            result = []
            for r in self.select(variant, "LGT-100"):
                qty, uom = number(r["quantity"]), r["uom"].lower()
                if uom == "mm":
                    qty, uom = qty / 1000, "m"
                if uom == "pcs":
                    uom = "ea"
                result.append((r["item_ref"], r["item_revision"], qty, uom, r["manufacturer_part_number"]))
            return sorted(result)
        self.assertEqual(signature("REG-A"), signature("REG-B"))
        self.assertEqual(signature("REG-A"), signature("REG-C"))
        raw_b = self.select("REG-B", item="LGT-100")[0]["item_ref"]
        self.assertEqual(raw_b, " LGT-1O0 ")

    def test_candidate_and_incompatible_match_have_distinct_evidence(self):
        a = self.select("REG-A", item="FLT-100")[0]
        c = self.select("REG-C", item="FLT-200")[0]
        self.assertEqual(a["length"], c["length"])
        self.assertEqual(self.select("REG-A", item="FLT-GASK-EP")[0]["material"], "EPDM")
        self.assertEqual(self.select("REG-C", item="FLT-GASK-SI")[0]["material"], "silicone")
        cab_a, cab_c = self.select("REG-A", item="CAB-240")[0], self.select("REG-C", item="CAB-110")[0]
        self.assertEqual(cab_a["description"], cab_c["description"])
        self.assertEqual(cab_a["length"], cab_c["length"])
        self.assertEqual((cab_a["voltage_v"], cab_c["voltage_v"]), ("24", "110"))
        self.assertEqual(next(f for f in self.oracle["findings"] if f["finding_id"] == "F06")["approval_status"], "not_approved")

    def test_missing_values_conflicts_and_revisions_remain_visible(self):
        self.assertEqual(self.select("REG-B", item="CAB-TERM")[0]["quantity"], "")
        self.assertEqual(self.select("REG-C", item="CAB-SW")[0]["supplier"], "")
        self.assertEqual(sum(not r["quantity"] for r in self.rows), 1)
        self.assertEqual(sum(not r["supplier"] for r in self.rows), 1)
        bolts = self.select("REG-C", "CAB-110", "FIX-M6-20") + self.select("REG-A", "CAB-240", "FIX-M6-20")
        self.assertEqual({r["length"] for r in bolts}, {"20", "25"})
        self.assertEqual({r["item_revision"] for r in bolts}, {"A"})
        self.assertEqual(self.select("REG-A", item="CAB-FAN")[0]["item_revision"], "A")
        self.assertEqual(self.select("REG-C", item="CAB-FAN")[0]["item_revision"], "B")

    def test_duplicate_does_not_mean_all_repeated_parts_are_duplicates(self):
        ignored = {"row_id", "source_line"}
        signatures = Counter(tuple((k, v) for k, v in r.items() if k not in ignored) for r in self.rows)
        self.assertEqual(sorted(v for v in signatures.values() if v > 1), [2])
        latches = self.select("REG-B", "FLT-100", "FLT-LATCH")
        self.assertEqual(len(latches), 2)
        self.assertEqual({r["quantity"] for r in latches}, {"2"})
        root_rows = self.select("REG-A", "SYN-TRAIN-A")
        counts = {r["item_ref"]: number(r["quantity"]) for r in root_rows}
        bolts = self.select("REG-A", item="FIX-M6-20")
        self.assertEqual(len({r["parent_ref"] for r in bolts}), 3)
        self.assertEqual(sum(counts[r["parent_ref"]] * number(r["quantity"]) for r in bolts), 70)


if __name__ == "__main__":
    unittest.main()
