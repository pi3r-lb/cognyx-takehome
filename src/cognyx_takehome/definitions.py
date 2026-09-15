"""Dagster assets share the exact same storage/rules used by the CLI."""
import os
from pathlib import Path

import dagster as dg

from .observability import configure
from .pipeline import reconcile
from .storage import RULE_VERSION, database, ingest, status


class LocalStore(dg.ConfigurableResource):
    directory: str = ".local/cognyx"


class BomConfig(dg.Config):
    path: str = "data/bom.csv"
    variants: str = "data/variants.csv"
    override: bool = False


class NotesConfig(dg.Config):
    path: str = "data/technical_notes.csv"
    override: bool = False


def run_step(context, store, function, **kwargs):
    logger = configure(store.directory)
    context.log.info(f"{function.__name__}: local store {Path(store.directory).resolve()}")
    try:
        result = function(store.directory, run_id=context.run_id, **kwargs)
    except Exception:
        logger.exception("pipeline_step_failed", extra={"details": {"run_id": context.run_id, "step": function.__name__}})
        raise
    context.log.info(str(result))
    return result


@dg.asset(group_name="ingestion", description="Exact BOM and variant sources, append-safe and atomically replaceable.")
def bom_raw(context: dg.AssetExecutionContext, config: BomConfig, store: LocalStore):
    result = run_step(context, store, ingest, kind="bom", path=config.path,
                      variants_path=config.variants, override=config.override)
    return dg.MaterializeResult(metadata={"import": dg.MetadataValue.json(result),
                                          "database": dg.MetadataValue.path(str(Path(store.directory).resolve()/"bom.db"))})


@dg.asset(group_name="ingestion", description="Original bilingual technical notes with exact source bytes and provenance.")
def technical_notes_raw(context: dg.AssetExecutionContext, config: NotesConfig, store: LocalStore):
    result = run_step(context, store, ingest, kind="technical-notes", path=config.path, override=config.override)
    return dg.MaterializeResult(metadata={"import": dg.MetadataValue.json(result),
                                          "database": dg.MetadataValue.path(str(Path(store.directory).resolve()/"technical_notes.db"))})


@dg.asset(deps=[bom_raw, technical_notes_raw], group_name="quality", code_version=RULE_VERSION,
          description="Normalize independent source stores, extract bounded note claims, reconcile with auditable evidence.")
def reconciled(context: dg.AssetExecutionContext, store: LocalStore):
    result = run_step(context, store, reconcile)
    return dg.MaterializeResult(metadata={**result, "generations": dg.MetadataValue.json(list(result["generations"])),
        "scope": "Data quality and linked evidence; engineering reuse analysis is not implemented."})


def storage_check(store):
    with database(store.directory) as db:
        errors = []
        for schema in ("main", "notes"):
            errors.extend(f"{schema}: {r[0]}" for r in db.execute(f"PRAGMA {schema}.integrity_check") if r[0] != "ok")
            errors.extend(f"{schema}: {tuple(r)}" for r in db.execute(f"PRAGMA {schema}.foreign_key_check"))
        # SQLite cannot enforce a foreign key from one attached file to another.
        errors.extend(f"Dangling note/BOM link: {r[0]}" for r in db.execute(
            "SELECT l.row_id FROM notes.links l LEFT JOIN raw_bom_rows b ON b.row_id=l.row_id WHERE b.row_id IS NULL"))
    return dg.AssetCheckResult(passed=not errors, metadata={"errors": dg.MetadataValue.json(errors)})


@dg.asset_check(asset=bom_raw, blocking=True, name="sqlite_integrity")
def bom_storage_integrity(store: LocalStore):
    return storage_check(store)


@dg.asset_check(asset=technical_notes_raw, blocking=True, name="sqlite_integrity")
def notes_storage_integrity(store: LocalStore):
    return storage_check(store)


CHECK_RULES = (
    "input_completeness", "identity", "hierarchy", "numeric_values", "units", "missing_values",
    "attribute_conflicts", "possible_alias", "alias_evidence", "reference_alias", "supplier_alias",
    "duplicate_occurrence", "note_metadata", "note_links", "extraction_coverage",
)


@dg.multi_asset_check(specs=[dg.AssetCheckSpec(name=rule, asset="reconciled") for rule in CHECK_RULES])
def data_checks(store: LocalStore):
    snapshot = status(store.directory)
    for rule in CHECK_RULES:
        related = [f for f in snapshot["findings"] if f["rule"] == rule]
        unresolved = [f for f in related if f["status"] == "open"]
        severity = dg.AssetCheckSeverity.ERROR if any(f["severity"] == "ERROR" for f in unresolved) else dg.AssetCheckSeverity.WARN
        yield dg.AssetCheckResult(asset_key="reconciled", check_name=rule, passed=not unresolved,
            severity=severity, metadata={"unresolved": len(unresolved), "resolved": len(related)-len(unresolved),
                "evidence": dg.MetadataValue.json(related), "generations": dg.MetadataValue.json(snapshot["generations"])})


@dg.asset_check(asset=reconciled, blocking=True, name="safe_to_use")
def safe_to_use(store: LocalStore):
    snapshot = status(store.directory)
    no_errors = snapshot["reconciliation_current"] and snapshot["unresolved_errors"] == 0
    return dg.AssetCheckResult(passed=no_errors and snapshot["inputs_complete"],
        severity=dg.AssetCheckSeverity.WARN if no_errors else dg.AssetCheckSeverity.ERROR,
        metadata={"errors": snapshot["unresolved_errors"], "inputs_complete": snapshot["inputs_complete"],
        "warnings": snapshot["unresolved_warnings"], "current": snapshot["reconciliation_current"],
        "meaning": "No blocking integrity errors. Open warnings still require engineering/data review."})


@dg.asset(deps=[reconciled], group_name="quality", description="Gated summary; warnings remain visible and never imply engineering approval.")
def quality_summary(store: LocalStore):
    snapshot = status(store.directory)
    # Also guard callers that explicitly select only this asset and omit checks.
    if not snapshot["reconciliation_current"] or snapshot["unresolved_errors"]:
        raise dg.Failure("Reconciliation is stale or has blocking integrity errors. Run reconciliation and inspect findings.")
    return dg.MaterializeResult(metadata={**snapshot["counts"], "warnings": snapshot["unresolved_warnings"],
                                         "inputs_complete": snapshot["inputs_complete"],
                                         "status": "incomplete" if not snapshot["inputs_complete"] else
                                         "needs_review" if snapshot["unresolved_warnings"] else "checked"})


assets = [bom_raw, technical_notes_raw, reconciled, quality_summary]
checks = [bom_storage_integrity, notes_storage_integrity, data_checks, safe_to_use]
bom_job = dg.define_asset_job("ingest_bom", selection=dg.AssetSelection.assets(bom_raw, reconciled, quality_summary))
notes_job = dg.define_asset_job("ingest_technical_notes", selection=dg.AssetSelection.assets(technical_notes_raw, reconciled, quality_summary))
reconcile_job = dg.define_asset_job("reconcile", selection=dg.AssetSelection.assets(reconciled, quality_summary))
all_job = dg.define_asset_job("ingest_all", selection=dg.AssetSelection.all())
defs = dg.Definitions(assets=assets, asset_checks=checks, jobs=[bom_job, notes_job, reconcile_job, all_job],
    resources={"store": LocalStore(directory=os.environ.get("COGNYX_DATA_DIR", ".local/cognyx"))},
    executor=dg.in_process_executor)
