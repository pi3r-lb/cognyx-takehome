"""Behavioral integration checks against temporary real SQLite databases."""
import csv
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest

from cognyx_takehome.pipeline import reconcile
from cognyx_takehome.storage import database, ingest, parse_file, status

DATA = Path(__file__).resolve().parents[1] / "data"


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"

    def import_bom(self, path=None, override=False):
        return ingest(self.store, "bom", path or DATA / "bom.csv", DATA / "variants.csv", override=override)

    def import_notes(self, path=None, override=False):
        return ingest(self.store, "technical-notes", path or DATA / "technical_notes.csv", override=override)

    def full(self):
        self.import_bom()
        self.import_notes()
        reconcile(self.store)

    def rows(self, query, params=()):
        with database(self.store) as db:
            return [dict(r) for r in db.execute(query, params)]

    def mutate(self, file, transform):
        with (DATA / file).open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)
        rows = transform(rows) or rows
        out = self.root / file
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)
        return out

    def test_raw_bytes_counts_and_provenance(self):
        self.full()
        counts = status(self.store)["counts"]
        self.assertEqual((counts["raw_bom_rows"], counts["variants"], counts["raw_notes"]), (118, 3, 20))
        self.assertEqual(counts["included_bom_rows"], 117)
        self.assertEqual(status(self.store)["unresolved_errors"], 0)
        source = self.rows("SELECT content FROM imports WHERE source_kind='bom'")[0]["content"]
        self.assertEqual(source, (DATA / "bom.csv").read_bytes())
        b = self.rows("SELECT * FROM raw_bom_rows WHERE row_id='REG-B-001'")[0]
        self.assertEqual(b["item_ref"], " LGT-1O0 ")
        self.assertEqual(b["source_line"], "2")
        self.assertNotEqual(b["physical_line"], 2)

    def test_supported_corrections_and_unknowns(self):
        self.full()
        self.assertEqual(len(self.rows("SELECT * FROM corrections WHERE rule='reference_alias'")), 13)
        self.assertEqual(self.rows("SELECT quantity,uom FROM bom_rows WHERE row_id='REG-B-008'")[0], {"quantity": "2.5", "uom": "M"})
        self.assertEqual(self.rows("SELECT quantity,length_mm FROM bom_rows WHERE row_id='REG-B-015'")[0], {"quantity": "1", "length_mm": "600"})
        self.assertEqual(self.rows("SELECT quantity FROM bom_rows WHERE row_id='REG-B-017'")[0]["quantity"], "2.4")
        self.assertIsNone(self.rows("SELECT quantity FROM bom_rows WHERE row_id='REG-B-032'")[0]["quantity"])
        self.assertIsNone(self.rows("SELECT supplier FROM bom_rows WHERE row_id='REG-C-031'")[0]["supplier"])
        self.assertEqual(self.rows("SELECT length_mm FROM bom_rows WHERE row_id='REG-C-037'")[0]["length_mm"], "25")
        f = self.rows("SELECT * FROM findings WHERE rule='attribute_conflicts' AND entity_id='REG-C-037'")[0]
        self.assertIn("NOTE-011", json.loads(f["evidence_json"])["note_ids"])
        self.assertEqual({r["revision"] for r in self.rows("SELECT * FROM parts WHERE ref='CAB-FAN'")}, {"A", "B"})

    def test_occurrences_and_duplicate_evidence(self):
        self.full()
        changes = self.rows("SELECT * FROM corrections WHERE rule='duplicate_occurrence'")
        self.assertEqual(len(changes), 1)
        self.assertIn("NOTE-015", json.loads(changes[0]["evidence_json"])["note_ids"])
        roots = {r["item_ref"]: Decimal(r["quantity"]) for r in self.rows("SELECT * FROM bom_rows WHERE variant_id='REG-A' AND parent_ref='SYN-TRAIN-A'")}
        bolts = self.rows("SELECT * FROM bom_rows WHERE variant_id='REG-A' AND item_ref='FIX-M6-20'")
        self.assertEqual(len(bolts), 3)
        self.assertEqual(sum(roots[r["parent_ref"]]*Decimal(r["quantity"]) for r in bolts), 70)

    def test_exact_reimport_is_noop(self):
        self.full()
        before = status(self.store)
        self.assertFalse(self.import_bom()["changed"])
        self.assertFalse(self.import_notes()["changed"])
        after = status(self.store)
        self.assertEqual(before["counts"], after["counts"])
        self.assertEqual(before["generations"], after["generations"])
        self.assertTrue(after["reconciliation_current"])
        reconcile(self.store)
        self.assertEqual(before["findings"], status(self.store)["findings"])

    def test_same_key_conflict_and_source_collision_roll_back(self):
        self.full()
        before = status(self.store)
        changed = self.mutate("bom.csv", lambda rows: rows[0].update(quantity="99"))
        with self.assertRaisesRegex(ValueError, "Source conflict"):
            self.import_bom(changed)
        self.assertEqual(before, status(self.store))
        changed = self.mutate("bom.csv", lambda rows: rows[0].update(row_id="NEW-ID"))
        with self.assertRaisesRegex(ValueError, "Source position conflict"):
            self.import_bom(changed)
        self.assertEqual(before, status(self.store))

    def test_malformed_override_keeps_previous_data(self):
        self.full()
        before = status(self.store)
        path = self.root / "bad.csv"
        for content in ("wrong,headers\na,b\n", (DATA / "bom.csv").read_text().splitlines()[0] + '\n"unterminated',
                        (DATA / "bom.csv").read_text().splitlines()[0] + "\n"):
            with self.subTest(content=content[:30]):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    self.import_bom(path, override=True)
                self.assertEqual(before, status(self.store))

    def test_scoped_override_invalidates_and_removes_old_evidence(self):
        self.full()
        bom_bytes = self.rows("SELECT * FROM raw_bom_rows")
        path = self.mutate("technical_notes.csv", lambda rows: [n for n in rows if n["note_id"] not in {"NOTE-002", "NOTE-015"}])
        self.import_notes(path, override=True)
        self.assertEqual(bom_bytes, self.rows("SELECT * FROM raw_bom_rows"))
        self.assertFalse(status(self.store)["reconciliation_current"])
        self.assertEqual(status(self.store)["counts"]["normalized_bom_rows"], 0)
        reconcile(self.store)
        self.assertEqual(status(self.store)["counts"]["included_bom_rows"], 118)
        self.assertEqual(self.rows("SELECT * FROM corrections WHERE rule='reference_alias'"), [])
        self.assertEqual(self.rows("SELECT item_ref FROM bom_rows WHERE row_id='REG-B-001'")[0]["item_ref"], "LGT-1O0")
        self.assertTrue(self.rows("SELECT * FROM findings WHERE rule='possible_alias'"))

    def test_import_order_converges(self):
        self.import_notes()
        reconcile(self.store)
        self.assertTrue(self.rows("SELECT * FROM notes.findings WHERE rule='note_links'"))
        self.import_bom()
        reconcile(self.store)
        before = status(self.store)
        self.import_notes(override=True)
        self.import_bom(override=True)
        reconcile(self.store)
        self.assertEqual(before["counts"], status(self.store)["counts"])
        self.assertEqual(before["findings"], status(self.store)["findings"])

    def test_numeric_garbage_and_fractional_each_block(self):
        self.full()
        for token in ("NaN", "Infinity", "two", "1e6", "-1", "0", "1.5", "1,2,3", "123456789012345678901234567890"):
            with self.subTest(token=token):
                path = self.mutate("bom.csv", lambda rows: rows[0].update(quantity=token))
                self.import_bom(path, override=True)
                reconcile(self.store)
                self.assertIsNone(self.rows("SELECT quantity FROM bom_rows WHERE row_id='REG-A-001'")[0]["quantity"])
                self.assertGreater(status(self.store)["unresolved_errors"], 0)
                self.assertEqual(self.rows("SELECT quantity FROM raw_bom_rows WHERE row_id='REG-A-001'")[0]["quantity"], token)

    def test_bad_units_missing_identity_and_graph_cycles(self):
        self.full()
        for updates in ({"uom": "kg"}, {"item_revision": ""}, {"parent_ref": "NO-SUCH-PARENT"},
                        {"item_ref": "SYN-TRAIN-A"}, {"variant_id": "NO-VARIANT"}):
            with self.subTest(updates=updates):
                path = self.mutate("bom.csv", lambda rows: rows[0].update(updates))
                self.import_bom(path, override=True)
                reconcile(self.store)
                self.assertGreater(status(self.store)["unresolved_errors"], 0)

    def test_unsupported_or_conflicting_alias_is_never_applied(self):
        self.full()
        def wrong_revision(rows):
            rows[1]["applies_to_revision"] = "B"
        path = self.mutate("technical_notes.csv", wrong_revision)
        self.import_notes(path, override=True)
        reconcile(self.store)
        self.assertFalse(self.rows("SELECT * FROM corrections WHERE rule='reference_alias'"))
        self.assertGreater(status(self.store)["unresolved_errors"], 0)
        def conflict(rows):
            extra = dict(rows[1])
            extra.update(note_id="NOTE-CONFLICT", text=extra["text"].replace("désigne LGT-100", "désigne LGT-200"))
            return rows + [extra]
        self.import_notes(self.mutate("technical_notes.csv", conflict), override=True)
        reconcile(self.store)
        self.assertFalse(self.rows("SELECT * FROM corrections WHERE rule='reference_alias'"))

    def test_note_quotes_and_partial_coverage(self):
        self.full()
        claims = self.rows("SELECT c.*,n.text FROM notes.claims c JOIN notes.raw_notes n USING(note_id)")
        for c in claims:
            self.assertEqual(c["quote"], c["text"][c["span_start"]:c["span_end"]])
        self.assertTrue(self.rows("SELECT * FROM notes.normalized_notes WHERE extraction_status='unprocessed'"))
        self.assertFalse(self.rows("SELECT * FROM notes.normalized_notes WHERE link_status='unlinked'"))

    def test_header_and_source_duplicate_rejected(self):
        path = self.root / "duplicate.csv"
        path.write_text("note_id,note_id\na,b\n")
        with self.assertRaises(ValueError):
            parse_file(path, "technical-notes")
        path = self.mutate("bom.csv", lambda rows: rows + [rows[0]])
        with self.assertRaises(ValueError):
            self.import_bom(path)

    def test_reexported_occurrence_is_flagged_not_silently_counted(self):
        self.full()
        def reexport(rows):
            row = dict(rows[1])
            row.update(row_id="SECOND-EXPORT-002", source_export_id="SECOND-EXPORT")
            return [row]
        self.import_bom(self.mutate("bom.csv", reexport))
        reconcile(self.store)
        repeated = self.rows("SELECT * FROM bom_rows WHERE row_id IN ('REG-A-002','SECOND-EXPORT-002')")
        self.assertEqual(len(repeated), 2)
        self.assertEqual({r["quality_status"] for r in repeated}, {"needs_review"})
        self.assertFalse(self.rows("SELECT * FROM eligible_bom_rows WHERE row_id='SECOND-EXPORT-002'"))

    def test_correction_declarations_with_extra_context_are_not_executed(self):
        self.full()
        for prefix, suffix in (("Le contrôle confirme que la déclaration suivante est fausse : ", ""),
                               ("", " Cette correction est annulée.")):
            with self.subTest(prefix=prefix, suffix=suffix):
                def cancelled(rows):
                    for n in rows:
                        if n["note_id"] in {"NOTE-002", "NOTE-015", "NOTE-016"}:
                            n["text"] = prefix + n["text"] + suffix
                self.import_notes(self.mutate("technical_notes.csv", cancelled), override=True)
                reconcile(self.store)
                self.assertFalse(self.rows("SELECT * FROM corrections WHERE rule IN ('reference_alias','duplicate_occurrence','supplier_alias')"))
                self.assertEqual(status(self.store)["counts"]["included_bom_rows"], 118)

    def test_part_unit_dimension_and_type_conflicts_are_flagged(self):
        self.full()
        for updates in ({"uom": "EA"}, {"item_type": "assembly"}):
            with self.subTest(updates=updates):
                path = self.mutate("bom.csv", lambda rows: rows[46].update(updates))
                self.import_bom(path, override=True)
                reconcile(self.store)
                self.assertTrue(self.rows("SELECT * FROM findings WHERE entity_id='REG-B-008' AND rule='attribute_conflicts'"))
                self.assertFalse(self.rows("SELECT * FROM eligible_bom_rows WHERE row_id='REG-B-008'"))

    def test_storage_failure_during_override_rolls_back_both_stores(self):
        self.full()
        before = status(self.store)
        raw_before = self.rows("SELECT * FROM raw_bom_rows")
        notes_before = self.rows("SELECT * FROM notes.raw_notes")
        with database(self.store) as db:
            db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON raw_bom_rows BEGIN SELECT RAISE(ABORT,'simulated write failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "simulated write failure"):
            self.import_bom(override=True)
        self.assertEqual(before, status(self.store))
        self.assertEqual(raw_before, self.rows("SELECT * FROM raw_bom_rows"))
        self.assertEqual(notes_before, self.rows("SELECT * FROM notes.raw_notes"))

    def test_bom_override_preserves_notes(self):
        self.full()
        before = self.rows("SELECT * FROM notes.raw_notes")
        self.import_bom(override=True)
        self.assertEqual(before, self.rows("SELECT * FROM notes.raw_notes"))
        reconcile(self.store)
        self.assertEqual(status(self.store)["counts"]["included_bom_rows"], 117)


if __name__ == "__main__":
    unittest.main()
