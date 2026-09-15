"""Reconcile two source stores from a consistent snapshot, with an evidence trail."""
from collections import defaultdict
import logging
import time

from . import notes
from .quality import finding, graph_findings, normalize, observation_findings
from .storage import RULE_VERSION, database, encode, generations, invalidate, timestamp, transaction

LOG = logging.getLogger("cognyx")
BLOCK_CORRECTION = ("ne pas corriger", "do not correct", "do not normalize", "ne pas normaliser")


def reconcile(directory, run_id="manual"):
    start = time.monotonic()
    with database(directory) as db, transaction(db):
        gen = generations(db)
        raw_rows = [dict(r) for r in db.execute("SELECT * FROM raw_bom_rows ORDER BY row_id")]
        raw_variants = [dict(r) for r in db.execute("SELECT * FROM raw_variants ORDER BY variant_id")]
        raw_notes = [dict(r) for r in db.execute("SELECT * FROM notes.raw_notes ORDER BY note_id")]
        rows, variants, findings, corrections = normalize(raw_rows, raw_variants)
        notes_findings, extracted, normalized_notes = [], {}, []
        if not raw_rows or not raw_notes:
            findings.append(finding("input_completeness", "dataset", None,
                                    "Both BOM and notes are required for complete reconciliation"))
        for note in raw_notes:
            claims, coverage = notes.extract(note)
            extracted[note["note_id"]] = claims
            normalized_notes.append(dict(note_id=note["note_id"], variant_id=note["variant_id"].strip(),
                ref=note["applies_to_ref"].strip(), revision=note["applies_to_revision"].strip(),
                language=note["language"].strip().lower(), text=note["text"], extraction_status=coverage,
                link_status="unlinked"))
            if note["language"].strip().lower() not in {"fr", "en", "mixed"}:
                notes_findings.append(finding("note_metadata", note["note_id"], "language", "Unsupported language label"))
            for field in ("source_document", "variant_id", "applies_to_ref", "applies_to_revision", "text"):
                if not note[field].strip():
                    notes_findings.append(finding("note_metadata", note["note_id"], field, "Required note metadata/text missing", "ERROR"))
            notes_findings.append(finding("extraction_coverage", note["note_id"], "text",
                f"{coverage}: bounded patterns only; remaining prose requires review",
                evidence={"note_ids": [note["note_id"]]}))

        # Collect all alias proposals before accepting any, never last-wins.
        aliases = defaultdict(list)
        for note in raw_notes:
            for claim in extracted[note["note_id"]]:
                if claim["kind"] == "reference_alias":
                    value = claim["value"]
                    scope = (note["variant_id"].strip(), value["alias"], note["applies_to_revision"].strip())
                    aliases[scope].append((note, claim))
        valid_aliases = {}
        for scope, proposals in aliases.items():
            if not raw_rows:
                for _, claim in proposals:
                    claim["status"] = "pending_bom"
                continue
            targets = {claim["value"]["target"] for _, claim in proposals}
            target = next(iter(targets))
            variant, alias, revision = scope
            valid = len(targets) == 1 and alias != target and alias.replace("O", "0") == target
            sources = [r for r in rows if (r["variant_id"], r["item_ref"], r["item_revision"]) == scope]
            for note, claim in proposals:
                value = claim["value"]
                valid = valid and note["applies_to_ref"].strip() == alias and value["revision"] == revision
                valid = valid and value["confirmed_variant"] == variant
                valid = valid and not any(p in note["text"].lower() for p in BLOCK_CORRECTION)
                valid = valid and bool(sources) and all(r["manufacturer_part_number"] == value["mpn"] for r in sources)
                target_rows = [r for r in rows if r["item_ref"] == target and r["item_revision"] == revision]
                valid = valid and bool(target_rows) and all(r["manufacturer_part_number"] == value["mpn"] for r in target_rows)
            for note, claim in proposals:
                claim["status"] = "supported" if valid else "rejected"
                if not valid:
                    notes_findings.append(finding("alias_evidence", note["note_id"], "text",
                        "Alias is conflicting or lacks matching subject/revision/manufacturer evidence", "ERROR",
                        evidence={"note_ids": [p[0]["note_id"] for p in proposals]}))
            if valid:
                valid_aliases[scope] = (target, [p[0]["note_id"] for p in proposals])

        def correct(row, field, value, rule, note_ids, extra=None):
            old = row[field]
            row[field] = value
            evidence = {"row_ids": [row["row_id"]], "note_ids": note_ids, **(extra or {})}
            corrections.append(dict(row_id=row["row_id"], field=field, original_value=str(old),
                                    normalized_value=str(value), rule=rule, evidence=evidence))
            findings.append(finding(rule, row["row_id"], field, f"Applied evidenced correction: {old} → {value}",
                                    "INFO", "resolved", evidence))

        for row in rows:
            for field, revision_field in (("item_ref", "item_revision"), ("parent_ref", "parent_revision")):
                key = (row["variant_id"], row[field], row[revision_field])
                if key in valid_aliases:
                    target, note_ids = valid_aliases[key]
                    correct(row, field, target, "reference_alias", note_ids)

        # Suggest unproven O/0 pairs, but never merge them by similarity alone.
        identities = {(r["item_ref"], r["item_revision"]) for r in rows}
        for row in rows:
            ref = row["item_ref"]
            if "O" in ref and (ref.replace("O", "0"), row["item_revision"]) in identities and ref.replace("O", "0") != ref:
                findings.append(finding("possible_alias", row["row_id"], "item_ref",
                                        "Possible O/0 spelling collision; no supported alias correction"))

        # Supplier spelling is corrected only for an explicit case-equivalent claim
        # and the note's assembly scope, never used to infer a missing supplier.
        for note in raw_notes:
            for claim in extracted[note["note_id"]]:
                if claim["kind"] != "supplier_alias":
                    continue
                value = claim["value"]
                matching = [r for r in rows if r["variant_id"] == note["variant_id"].strip()
                    and ((r["item_ref"], r["item_revision"]) == (note["applies_to_ref"].strip(), note["applies_to_revision"].strip())
                         or (r["parent_ref"], r["parent_revision"]) == (note["applies_to_ref"].strip(), note["applies_to_revision"].strip()))
                    and r["supplier"] == value["alias"]]
                valid = (value["alias"].casefold() == value["target"].casefold() and bool(matching)
                         and not any(p in note["text"].lower() for p in BLOCK_CORRECTION))
                claim["status"] = "supported" if valid else "rejected"
                if valid:
                    for row in matching:
                        correct(row, "supplier", value["target"], "supplier_alias", [note["note_id"]])

        groups = defaultdict(list)
        raw_by_id = {r["row_id"]: r for r in raw_rows}
        payload_fields = [k for k in rows[0] if k not in {"row_id", "quality_status", "included"}] if rows else []
        for row in rows:
            groups[tuple(row[k] for k in payload_fields)].append(row)
        for group in groups.values():
            if len(group) < 2:
                continue
            first = group[0]
            evidence_notes = []
            for note in raw_notes:
                for claim in extracted[note["note_id"]]:
                    if claim["kind"] != "duplicate_occurrence":
                        continue
                    valid = (len(group) == 2 and first["quantity"] == "2" and first["uom"] == "EA"
                        and len({raw_by_id[r["row_id"]]["source_export_id"] for r in group}) == 1
                        and note["variant_id"].strip() == first["variant_id"]
                        and note["applies_to_ref"].strip() == first["item_ref"]
                        and note["applies_to_revision"].strip() == first["item_revision"]
                        and claim["value"]["parent"] == first["parent_ref"]
                        and len({r["parent_revision"] for r in rows if r["variant_id"] == first["variant_id"]
                                 and r["parent_ref"] == first["parent_ref"]}) == 1
                        and not any(p in note["text"].lower() for p in BLOCK_CORRECTION))
                    if valid:
                        claim["status"] = "supported"
                        evidence_notes.append(note["note_id"])
            if evidence_notes:
                for duplicate in group[1:]:
                    correct(duplicate, "included", 0, "duplicate_occurrence", evidence_notes,
                            {"row_ids": [r["row_id"] for r in group]})
            else:
                for row in group:
                    findings.append(finding("duplicate_occurrence", row["row_id"], "included",
                        "Repeated same-parent payload; source evidence is insufficient to suppress it",
                        evidence={"row_ids": [r["row_id"] for r in group]}))

        occurrences = defaultdict(list)
        for row in rows:
            occurrences[tuple(row[k] for k in ("variant_id", "parent_ref", "parent_revision", "item_ref", "item_revision"))].append(row)
        for group in occurrences.values():
            if len(group) > 1 and len({tuple(r[k] for k in payload_fields) for r in group}) > 1:
                for row in group:
                    findings.append(finding("duplicate_occurrence", row["row_id"], None,
                        "Multiple same-parent part occurrences have differing payloads; clarify occurrence identity before totaling",
                        evidence={"row_ids": [r["row_id"] for r in group]}))

        links = []
        for note in normalized_notes:
            scope = (note["variant_id"], note["ref"], note["revision"])
            method = "exact"
            if scope in valid_aliases:
                note["ref"] = valid_aliases[scope][0]
                method = "evidenced_alias"
            matched = [r for r in rows if (r["variant_id"], r["item_ref"], r["item_revision"]) ==
                       (note["variant_id"], note["ref"], note["revision"])]
            note["link_status"] = "linked" if matched else "unlinked"
            links.extend((note["note_id"], r["row_id"], method) for r in matched)
            if not matched:
                notes_findings.append(finding("note_links", note["note_id"], "ref",
                    "No matching BOM occurrence at this variant/reference/revision", evidence={"note_ids": [note["note_id"]]}))

        findings.extend(graph_findings(rows, variants))
        findings.extend(observation_findings(rows))
        for f in findings:
            if not f["evidence"]:
                f["evidence"] = {"row_ids": [f["entity_id"]]} if f["entity_id"] in raw_by_id else {}
            applicable = [n for n, rid, _ in links if rid == f["entity_id"]]
            if applicable:
                f["evidence"]["note_ids"] = sorted(set(f["evidence"].get("note_ids", []) + applicable))
        flagged = {f["entity_id"] for f in findings if f["status"] == "open" and f["severity"] in {"WARN", "ERROR"}}
        for row in rows:
            row["quality_status"] = "needs_review" if row["row_id"] in flagged else "checked"

        invalidate(db)
        for v in variants:
            db.execute("INSERT INTO variants VALUES (?,?,?,?,?)", tuple(v.values()))
        # Keep malformed-domain rows inspectable; placeholder catalog entries are
        # explicitly flagged, never silently considered real variant metadata.
        for row in rows:
            db.execute("INSERT OR IGNORE INTO variants(variant_id) VALUES (?)", (row["variant_id"],))
            db.execute("INSERT OR IGNORE INTO parts VALUES (?,?)", (row["item_ref"], row["item_revision"]))
            columns = ",".join(row)
            db.execute(f"INSERT INTO bom_rows ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        for change in corrections:
            db.execute("INSERT INTO corrections(row_id,field,original_value,normalized_value,rule,evidence_json) VALUES (?,?,?,?,?,?)",
                (change["row_id"], change["field"], change["original_value"], change["normalized_value"], change["rule"], encode(change["evidence"])))
        for note in normalized_notes:
            db.execute("INSERT INTO notes.normalized_notes VALUES (?,?,?,?,?,?,?,?)", tuple(note.values()))
        for note_id, claims in extracted.items():
            for c in claims:
                db.execute("INSERT INTO notes.claims(note_id,kind,value_json,span_start,span_end,quote,method,status) VALUES (?,?,?,?,?,?,?,?)",
                           (note_id, c["kind"], encode(c["value"]), c["start"], c["end"], c["quote"], c["method"], c["status"]))
        db.executemany("INSERT INTO notes.links VALUES (?,?,?)", links)
        for schema, issues in (("main", findings), ("notes", notes_findings)):
            for f in issues:
                db.execute(f"INSERT INTO {schema}.findings(rule,severity,status,entity_id,field,message,evidence_json) VALUES (?,?,?,?,?,?,?)",
                           (f["rule"], f["severity"], f["status"], f["entity_id"], f["field"], f["message"], encode(f["evidence"])))
        db.execute("INSERT INTO reconciliation VALUES (1,?,?,?,?,?)", (*gen, RULE_VERSION, run_id, timestamp()))
        errors = sum(f["severity"] == "ERROR" and f["status"] == "open" for f in findings + notes_findings)
        warnings = sum(f["severity"] == "WARN" and f["status"] == "open" for f in findings + notes_findings)
        db.execute("INSERT OR REPLACE INTO meta VALUES ('eligible',?)",
                   ("1" if not errors and raw_rows and raw_notes and variants else "0",))
        result = {"bom_rows": len(rows), "notes": len(raw_notes), "corrections": len(corrections),
                  "errors": errors, "warnings": warnings, "generations": gen}
    LOG.info("reconciliation_completed", extra={"details": {**result, "run_id": run_id, "duration_ms": round((time.monotonic()-start)*1000)}})
    return result
