# Cognyx take-home

A local Dagster pipeline that imports synthetic multi-variant BOM data and bilingual
technical notes into **two SQLite databases**, normalizes supported values, and
records quality findings with source evidence. Python 3.12 and `uv` are required.

## Run the demo

From the repository root:

```sh
uv sync --locked
uv run cognyx-takehome ingest bom data/bom.csv --variants data/variants.csv
uv run cognyx-takehome ingest technical-notes data/technical_notes.csv
uv run cognyx-takehome server
```

Open **http://127.0.0.1:3000**. In **Catalog**, inspect `reconciled` → **Checks** for
rule results and source evidence. The `reference_alias` and `duplicate_occurrence`
checks show supported corrections; `missing_values`, `attribute_conflicts`, and
`extraction_coverage` retain warnings. **Runs** shows CLI and dashboard executions.
The `ingest_all` job can run the complete fixture import from the dashboard.

The server runs in the foreground; stop it with Ctrl-C. CLI imports also work
without the server. Both use the same persistent Dagster instance. To use another
workspace, pass `--data-dir /path/to/workspace` to every command (including server).

```sh
uv run cognyx-takehome status
uv run cognyx-takehome findings
uv run cognyx-takehome reconcile
# Replace only BOM + variant inputs, preserving technical notes:
uv run cognyx-takehome ingest bom data/bom.csv --variants data/variants.csv --override
```

Default ingestion adds new records and skips identical records. Reused source IDs
with changed values fail explicitly. `--override` atomically replaces the selected
input family; raw source files remain archived in the import history. Empty or
malformed inputs cannot wipe the active dataset. Replacement invalidates and
rebuilds derived results, including corrections whose supporting notes disappeared.
Domain-invalid values remain in raw storage with findings. Blocking check failures
make the command exit nonzero; warnings do not. Notes-first ingestion is supported
and reports incomplete readiness until BOM inputs arrive.

## Local outputs

All runtime files are ignored by Git under `.local/cognyx/`:

| File | Content |
| --- | --- |
| `bom.db` | Raw BOM/variants, normalized parts and occurrences, corrections, findings, reconciliation versions |
| `technical_notes.db` | Raw notes, bounded extracted claims with exact text spans, links and findings |
| `logs/ingestion.jsonl` | Rotating JSON logs: UTC time, run ID, event, source hash, counts, duration and failures |
| `dagster/` | Dagster configuration, run/event history and compute logs |

Original source bytes, raw spellings, CSV positions and import provenance remain
available. `bom_rows` includes every normalized occurrence and its review status.
`included=0` identifies the evidenced export duplicate. `eligible_bom_rows` excludes
flagged occurrences and is empty while inputs are incomplete or blocking errors
exist. It is a data-quality convenience view, **not an engineering approval**.

To inspect a correction directly:

```sh
sqlite3 .local/cognyx/bom.db "SELECT row_id,field,original_value,normalized_value,evidence_json FROM corrections WHERE rule='reference_alias';"
```

## What is demonstrated

The fixtures contain 118 BOM rows, three variants and 20 French/English/mixed notes.
The pipeline preserves all raw rows and excludes one documented duplicate from
117 included occurrences. It resolves the 13-row lighting-reference alias only
with matching note/revision/manufacturer evidence, normalizes decimal commas and
units, and preserves legitimate uses of the same part under different parents.

A blank quantity stays unknown. The 25 mm versus 20 mm bolt conflict remains
unresolved. Fan revisions remain separate. Case-equivalent supplier spelling is
corrected only where explicit scoped evidence supports it. Unsupported O/0 matches
are suggestions, never automatic substitutions.

Note extraction recognizes a small set of **whole, explicit declaration templates**
and retains contextual passages. Every note is marked partial or unprocessed;
this is not general NLP. Negated/qualified correction prose is not executed.
Numerics accept decimal dot/comma with up to 18 digits; unsupported forms are
flagged. Normalized decimal values use exact text storage in SQLite and Python
`Decimal` arithmetic. Quantity units and component dimensions are independent.

All engineering data is invented. The fixture describes reuse candidates, but
**reuse ranking and engineering compatibility analysis are not implemented**.
The evaluation oracle at `data/expected/findings.json` is used only by fixture tests,
never by the ingestion runtime. See `data/manifest.json` for source semantics.

## Verification and AI-work trace

```sh
uv run --locked python -m unittest discover -s tests -v
uv build
uv run python -m cognyx_takehome.generate_data --output /tmp/cognyx-data-preview
```

Tests cover fixture reproducibility, raw preservation, unit/identity checks,
transaction rollback, idempotency, import order, evidence removal, misleading note
text, re-export duplication, and real Dagster checks blocking downstream execution.
The package wheel and source distribution build locally. Tested on macOS ARM64;
production deployment and other platforms are unverified.

Codex implemented the pipeline from the user-approved design with GStack planning
and review guidance. An independent review found correction-context, re-export,
incomplete-input and unit-consistency defects; regression tests cover their fixes.
The source, tests and this account provide a shareable trace. Detailed design,
decisions, review results and handoffs live in the canonical Obsidian project vault;
all agents follow [AGENTS.md](AGENTS.md).

Runtime uses local files and no cloud NLP service. The generated Dagster instance
configuration disables telemetry and the dashboard binds to loopback. This local
development setup is not a production deployment: authentication, access controls,
backup/migration operations, network-isolation validation and multi-user operation
remain future work. Use local disk, not a network filesystem, for attached SQLite
transactions. Dagster owns its own metadata databases in addition to the two
application databases above.
