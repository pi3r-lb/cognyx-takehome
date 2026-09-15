# Cognyx take-home

A local Dagster pipeline that imports synthetic multi-variant BOM data and bilingual
technical notes into **two SQLite databases**, normalizes supported values, and
records quality findings with source evidence. A read-only local MCP exposes BOM
and note retrieval to compatible agents. Python 3.12 and `uv` are required.

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

## Connect an agent to the MCP

The agent must support **local stdio MCP servers** and run on a machine with
access to this checkout and its databases. The agent starts the server itself:
there is no HTTP URL, port or separate terminal process to keep running.
The Dagster dashboard does not need to be running.

First, from the repository root, install the CLI and check the data:

```sh
uv sync --locked
uv run --locked cognyx-takehome status
```

If data has not been loaded, run the two ingestion commands under
[Run the demo](#run-the-demo). Startup requires both input families, current
reconciliation and no blocking errors. Warnings are allowed and returned with
the evidence.

### Codex

From the repository root, register the server:

```sh
codex mcp add cognyx -- "$PWD/.venv/bin/cognyx-takehome" \
  mcp start --data-dir "$PWD/.local/cognyx"
codex mcp list
```

This stores absolute paths, so later agent sessions can start from another
directory. Restart the agent/session after adding the server; in the Codex
terminal UI, use `/mcp` to check the connection.
See the [official Codex MCP setup documentation](https://developers.openai.com/codex/mcp/).

### Claude Code

From the repository root, register the server for this project:

```sh
claude mcp add --transport stdio --scope local cognyx -- \
  "$PWD/.venv/bin/cognyx-takehome" mcp start \
  --data-dir "$PWD/.local/cognyx"
claude mcp get cognyx
```

The `local` scope keeps the configuration private to you and available in this
project. Use `--scope user` instead if you want it available in all your projects.
Start a new Claude Code session in this repository and use `/mcp` to check the
connection. See the [official Claude Code MCP setup documentation](https://code.claude.com/docs/en/mcp).

Both examples use absolute paths and the macOS/Linux virtual-environment layout;
Windows is not validated.

### Verify and use the connection

Ask the agent: **“Use the cognyx MCP to call get_dataset_info and list the variants.”**
With the supplied fixture, expect 118 raw BOM rows, 20 notes and three variants.
The server exposes six tools:

| Tool | Purpose |
| --- | --- |
| `get_dataset_info` | Dataset version, variants, quality counts and supported filters |
| `search_bom` | Search part occurrences by keywords and structured fields |
| `get_bom_row` | Original/normalized values, corrections and source evidence for one row |
| `get_assembly` | Assembly or train-root structure for an exact variant/reference/revision |
| `search_notes` | Original-note keyword search, optionally filtered by declared variant |
| `get_note` | Exact original note text, in bounded segments with source citations |

Example prompt:

> Use the cognyx MCP to investigate whether FLT-150 revision A from REG-B could
> be a reuse candidate for REG-A. Start with get_dataset_info and pass its
> dataset_version as expected_version in subsequent calls. Retrieve the BOM
> structures and technical notes across all variants; search French and English
> terms where needed. Cite BOM row IDs and exact note passages. Separate observed
> facts, conditions and unresolved checks; do not claim engineering approval.

Note search matches literal keywords, ignoring case and accents; it does not
translate. A variant filter selects the note's declared variant, so leave it
unset when collecting cross-variant evidence. Follow pagination/text-segment
continuations and preserve warnings.

If the connection fails, check executable/data paths and the client's server
stderr. `DATABASE_UNAVAILABLE` means the stores cannot be read;
`NOT_READY` means inputs, reconciliation or blocking findings need attention.
After correcting the inputs, run `uv run --locked cognyx-takehome reconcile`.
`DATASET_CHANGED` means the agent must fetch a new version and restart its
comparison. Running `mcp start` manually may appear idle: it is waiting for MCP
messages, not presenting an interactive shell.

The server reads locally and makes no model calls. Retrieved evidence is passed
to the chosen agent and is subject to that agent's data-handling configuration.

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
