"""Local source stores. All application writes use one attached transaction.

bom.db (main) + technical_notes.db (notes) use rollback journals on local disk.
Raw imports and invalidation commit together; reconciliation rebuilds from raw.
"""
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
from pathlib import Path
import sqlite3
import time
import uuid

LOG = logging.getLogger("cognyx")
RULE_VERSION = "1"
BOM_FIELDS = "row_id source_export_id source_line variant_id parent_ref parent_revision item_ref item_revision item_type description quantity uom supplier manufacturer_part_number length length_unit material voltage_v".split()
VARIANT_FIELDS = "variant_id name root_ref root_revision snapshot_date scope data_status".split()
NOTE_FIELDS = "note_id source_document variant_id applies_to_ref applies_to_revision language text".split()
SPECS = {
    "bom": ("main", "raw_bom_rows", BOM_FIELDS, "row_id"),
    "variants": ("main", "raw_variants", VARIANT_FIELDS, "variant_id"),
    "technical-notes": ("notes", "raw_notes", NOTE_FIELDS, "note_id"),
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@contextmanager
def database(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "bom.db", timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("ATTACH DATABASE ? AS notes", (str(directory / "technical_notes.db"),))
        for schema in ("main", "notes"):
            db.execute(f"PRAGMA {schema}.journal_mode=DELETE")
            db.execute(f"PRAGMA {schema}.synchronous=FULL")
            db.execute(f"CREATE TABLE IF NOT EXISTS {schema}.meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute(f"INSERT OR IGNORE INTO {schema}.meta VALUES ('generation','0')")
            db.execute(f"""CREATE TABLE IF NOT EXISTS {schema}.imports (
                batch_id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, path TEXT NOT NULL,
                sha256 TEXT NOT NULL, content BLOB NOT NULL, imported_at TEXT NOT NULL,
                run_id TEXT NOT NULL, mode TEXT NOT NULL, added INTEGER NOT NULL, skipped INTEGER NOT NULL)""")
            db.execute(f"""CREATE TABLE IF NOT EXISTS {schema}.findings (
                finding_id INTEGER PRIMARY KEY, rule TEXT NOT NULL, severity TEXT NOT NULL,
                status TEXT NOT NULL, entity_id TEXT NOT NULL, field TEXT,
                message TEXT NOT NULL, evidence_json TEXT NOT NULL)""")
        for schema, table, fields, key in SPECS.values():
            columns = ", ".join(f'"{f}" TEXT NOT NULL' + (" PRIMARY KEY" if f == key else "") for f in fields)
            db.execute(f"CREATE TABLE IF NOT EXISTS {schema}.{table} ({columns}, batch_id TEXT NOT NULL REFERENCES imports(batch_id), physical_line INTEGER NOT NULL)")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS variants (
            variant_id TEXT PRIMARY KEY, name TEXT, root_ref TEXT, root_revision TEXT, snapshot_date TEXT);
        CREATE TABLE IF NOT EXISTS parts (ref TEXT, revision TEXT, PRIMARY KEY(ref,revision));
        CREATE TABLE IF NOT EXISTS bom_rows (
            row_id TEXT PRIMARY KEY REFERENCES raw_bom_rows(row_id), variant_id TEXT NOT NULL,
            parent_ref TEXT, parent_revision TEXT, item_ref TEXT, item_revision TEXT, item_type TEXT,
            description TEXT, quantity TEXT, uom TEXT, supplier TEXT, manufacturer_part_number TEXT,
            length_mm TEXT, material TEXT, voltage_v TEXT, included INTEGER NOT NULL,
            quality_status TEXT NOT NULL,
            FOREIGN KEY(variant_id) REFERENCES variants(variant_id),
            FOREIGN KEY(item_ref,item_revision) REFERENCES parts(ref,revision));
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY, row_id TEXT NOT NULL REFERENCES raw_bom_rows(row_id),
            field TEXT NOT NULL, original_value TEXT, normalized_value TEXT,
            rule TEXT NOT NULL, evidence_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reconciliation (
            id INTEGER PRIMARY KEY CHECK(id=1), bom_generation TEXT, notes_generation TEXT,
            rule_version TEXT, run_id TEXT, completed_at TEXT);
        CREATE TABLE IF NOT EXISTS notes.normalized_notes (
            note_id TEXT PRIMARY KEY REFERENCES raw_notes(note_id), variant_id TEXT,
            ref TEXT, revision TEXT, language TEXT, text TEXT, extraction_status TEXT, link_status TEXT);
        CREATE TABLE IF NOT EXISTS notes.claims (
            claim_id INTEGER PRIMARY KEY, note_id TEXT NOT NULL REFERENCES raw_notes(note_id),
            kind TEXT NOT NULL, value_json TEXT NOT NULL, span_start INTEGER NOT NULL,
            span_end INTEGER NOT NULL, quote TEXT NOT NULL, method TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notes.links (
            note_id TEXT NOT NULL REFERENCES raw_notes(note_id), row_id TEXT NOT NULL,
            match_method TEXT NOT NULL, PRIMARY KEY(note_id,row_id));
        CREATE VIEW IF NOT EXISTS eligible_bom_rows AS
            SELECT * FROM bom_rows WHERE included=1 AND quality_status='checked'
              AND (SELECT value FROM meta WHERE key='eligible')='1';
        """)
        yield db
    finally:
        db.close()


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def generations(db):
    return tuple(db.execute(f"SELECT value FROM {s}.meta WHERE key='generation'").fetchone()[0]
                 for s in ("main", "notes"))


def invalidate(db):
    # Delete children before parents. All callers hold an attached transaction.
    for table in ("notes.links", "notes.claims", "notes.normalized_notes", "notes.findings",
                  "corrections", "bom_rows", "parts", "variants", "findings", "reconciliation"):
        db.execute(f"DELETE FROM {table}")
    db.execute("INSERT OR REPLACE INTO meta VALUES ('eligible','0')")


def parse_file(path, kind):
    schema, table, fields, key = SPECS[kind]
    path = Path(path).resolve()
    content = path.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(fields):
        raise ValueError(f"{path.name}: expected columns {', '.join(fields)}")
    records, keys, sources = [], set(), set()
    try:
        while True:
            line = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            if None in row or any(value is None or '\x00' in value for value in row.values()):
                raise ValueError(f"{path.name}:{line}: malformed CSV row")
            if not row[key].strip() or row[key] != row[key].strip() or row[key] in keys:
                raise ValueError(f"{path.name}:{line}: blank, padded or duplicate {key}")
            keys.add(row[key])
            if kind == "bom":
                if not row["source_export_id"].strip() or not row["source_line"].isdigit() or int(row["source_line"]) < 2:
                    raise ValueError(f"{path.name}:{line}: invalid source identity")
                source = (row["source_export_id"], int(row["source_line"]))
                if source in sources:
                    raise ValueError(f"{path.name}:{line}: duplicate source identity")
                sources.add(source)
            records.append((row, line))
    except csv.Error as exc:
        raise ValueError(f"{path.name}:{reader.line_num}: malformed CSV: {exc}") from exc
    if not records:
        raise ValueError(f"{path.name}: empty input; refusing accidental wipe")
    return {"kind": kind, "path": str(path), "content": content,
            "sha256": hashlib.sha256(content).hexdigest(), "records": records}


def ingest(directory, kind, path, variants_path=None, override=False, run_id="manual"):
    start = time.monotonic()
    if kind == "bom" and not variants_path:
        raise ValueError("BOM ingestion requires --variants PATH")
    files = [parse_file(path, kind)]
    if kind == "bom":
        files.insert(0, parse_file(variants_path, "variants"))
    added = skipped = 0
    batch_ids = []
    with database(directory) as db, transaction(db):
        # Validate all conflicts before removing or adding any active source rows.
        if not override:
            for file in files:
                schema, table, fields, key = SPECS[file["kind"]]
                for row, _ in file["records"]:
                    old = db.execute(f'SELECT * FROM {schema}.{table} WHERE "{key}"=?', (row[key],)).fetchone()
                    if old and any(old[f] != row[f] for f in fields):
                        raise ValueError(f"Source conflict: {key}={row[key]}; use --override for a replacement")
                    if file["kind"] == "bom":
                        collision = db.execute("SELECT row_id FROM raw_bom_rows WHERE source_export_id=? AND CAST(source_line AS INTEGER)=? AND row_id!=?",
                                               (row["source_export_id"], int(row["source_line"]), row[key])).fetchone()
                        if collision:
                            raise ValueError(f"Source position conflict: {row[key]} and {collision[0]}")
        has_new = override or any(
            db.execute(f'SELECT 1 FROM {SPECS[f["kind"]][0]}.{SPECS[f["kind"]][1]} WHERE "{SPECS[f["kind"]][3]}"=?',
                       (row[SPECS[f["kind"]][3]],)).fetchone() is None
            for f in files for row, _ in f["records"])
        if has_new:
            invalidate(db)
        if override:
            for file in files:
                schema, table, _, _ = SPECS[file["kind"]]
                db.execute(f"DELETE FROM {schema}.{table}")
        for file in files:
            schema, table, fields, key = SPECS[file["kind"]]
            new_rows = [(row, line) for row, line in file["records"] if not db.execute(
                f'SELECT 1 FROM {schema}.{table} WHERE "{key}"=?', (row[key],)).fetchone()]
            count = len(new_rows)
            skipped_here = len(file["records"]) - count
            added += count
            skipped += skipped_here
            batch = str(uuid.uuid4())
            batch_ids.append(batch)
            db.execute(f"INSERT INTO {schema}.imports VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (batch, file["kind"], file["path"], file["sha256"], file["content"], timestamp(),
                        run_id, "override" if override else "add", count, skipped_here))
            columns = ",".join(fields + ["batch_id", "physical_line"])
            placeholders = ",".join("?" for _ in range(len(fields) + 2))
            db.executemany(f"INSERT INTO {schema}.{table} ({columns}) VALUES ({placeholders})",
                           [tuple(row[f] for f in fields) + (batch, line) for row, line in new_rows])
        if has_new:
            schema = SPECS[kind][0]
            db.execute(f"UPDATE {schema}.meta SET value=CAST(value AS INTEGER)+1 WHERE key='generation'")
    result = {"kind": kind, "added": added, "skipped": skipped, "batch_ids": batch_ids,
              "source_sha256": files[-1]["sha256"], "changed": has_new}
    LOG.info("import_completed", extra={"details": {**result, "run_id": run_id, "duration_ms": round((time.monotonic()-start)*1000)}})
    return result


def status(directory):
    with database(directory) as db, transaction(db):
        return status_from_connection(db, directory)


def status_from_connection(db, directory):
    """Inspect within the caller's transaction; also used by read-only MCP queries."""
    gen = generations(db)
    rec = db.execute("SELECT * FROM reconciliation").fetchone()
    current = bool(rec and (rec["bom_generation"], rec["notes_generation"]) == gen and rec["rule_version"] == RULE_VERSION)
    counts = {name: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for name, table in {
        "raw_bom_rows": "raw_bom_rows", "variants": "raw_variants", "raw_notes": "notes.raw_notes",
        "normalized_bom_rows": "bom_rows", "included_bom_rows": "bom_rows WHERE included=1",
        "eligible_bom_rows": "eligible_bom_rows", "corrections": "corrections", "claims": "notes.claims",
        "note_links": "notes.links"}.items()}
    findings = [dict(r) for r in db.execute("SELECT 'bom' AS store,* FROM findings UNION ALL SELECT 'notes' AS store,* FROM notes.findings")]
    return {"directory": str(Path(directory).resolve()), "generations": gen, "reconciliation_current": current,
            "inputs_complete": bool(counts["raw_bom_rows"] and counts["raw_notes"] and counts["variants"]),
            "counts": counts, "unresolved_errors": sum(f["severity"] == "ERROR" and f["status"] == "open" for f in findings),
            "unresolved_warnings": sum(f["severity"] == "WARN" and f["status"] == "open" for f in findings),
            "findings": findings}
