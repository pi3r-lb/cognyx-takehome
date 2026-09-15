# Agent instructions

## Purpose and current state

This is the Cognyx Forward Deployed Engineer take-home project: a small working
tool that ingests synthetic multi-variant BOM data and technical notes, normalizes
them, and explains sub-assembly reuse opportunities and data inconsistencies.
The brief recommends no more than four hours of preparation. Favor a working,
well-prioritized demonstration with evidence and clear limitations.

The repository contains a working local Dagster ingestion pipeline, two SQLite
application stores, evidence-preserving normalization/corrections, quality checks,
CLI commands, logging, synthetic CSV fixtures and integration tests. Reuse analysis
and general NLP are not implemented. Do not describe planned capabilities as shipped.

## Documentation is in Obsidian

Repository: `/Users/pierre.delabelliere/projects/cognyx-takehome`

Canonical documentation directory:
`/Users/pierre.delabelliere/Obsidian/pierre-dlb/cognyx-takehome`

At the start of every task, read these notes in that directory:

1. `00 - Intro.md`
2. `01 - Brief.md`
3. `02 - Project Hub.md`
4. `HANDOFF.md`, starting with the latest entry
5. Relevant entries in `03 - Decisions.md` and `04 - Discussions.md`

Keep product and technical documentation, plans, trade-offs, discussion outcomes,
business assumptions, and demo preparation in that directory. Use Markdown and
Obsidian wiki links between notes. Preserve the original intro and brief.
The repository README is a short evaluator-facing entry point; keep agent
instructions here. Do not create a competing documentation tree in the repository.

The Obsidian CLI (`/opt/homebrew/bin/obsidian`) is enabled and was verified against
this project vault on 2026-09-14. Use it for supported vault operations. Consult
`obsidian --help` for syntax; put the command first and explicitly specify
`vault=pierre-dlb` and the vault-relative `path=cognyx-takehome/<note>.md`.
For example:

```sh
obsidian read vault=pierre-dlb 'path=cognyx-takehome/02 - Project Hub.md'
obsidian append vault=pierre-dlb 'path=cognyx-takehome/HANDOFF.md' 'content=Markdown entry'
```

Quote arguments containing spaces and use `\n` in CLI content values for newlines.
Verify writes by reading the target note back. The CLI needs access to the running
Obsidian app; use the environment's approval mechanism if sandbox access blocks it.
Direct Markdown edits in the canonical directory are also appropriate when simpler
or when the CLI does not support the operation. Keep references as Obsidian wiki
links. Do not create temporary Python scripts just to write or append routine
documentation. This user preference applies across sessions; either method must
still respect the environment's write permissions described below.

Record decisions in `03 - Decisions.md` with context, alternatives, rationale,
consequences, and status. Distinguish user decisions, agent implementation choices,
and proposals awaiting discussion. Record consequential discussions and unresolved
questions in `04 - Discussions.md`, including both technical and business matters.
Never present an inferred preference or a fictional metric as a confirmed fact.

## Mandatory handoff for every change

After each coherent change set, and before handing work back, append an entry to
the vault's `HANDOFF.md`. Documentation-only changes count. Use the template in
that file and record:

- Timestamp with timezone, agent identity, and task/user intent.
- What changed, with exact repository paths or vault note names.
- Why it changed, with links to decisions and discussion outcomes.
- Commands/checks run and actual results; explicitly identify untested work.
- Known limitations, blockers, and the concrete next step.
- Git status/commit reference if applicable; do not invent commit history.

Every agent working on this project follows this workflow. If multiple agents
are assigned, give each the vault path and a bounded area of ownership. Coordinate
appends to shared notes so that no entry is overwritten. Keep code in the repository
and documentation in the vault. Do not delegate unless requested or authorized by
the current task's governing instructions.

The vault is outside the default repository write sandbox. Read access does not
imply tool-level write permission. Prepare the exact documentation changes first,
then use the environment's approval mechanism if needed to write them. If access
is blocked, report the pending handoff explicitly; do not silently skip it or
claim it was saved.

## Development workflow

- Inspect the working tree before editing; preserve existing user changes.
- Keep changes small and inspectable, and record material AI-assisted choices.
- Follow the existing Python package layout under `src/cognyx_takehome/`.
- The project pins Python 3.12, declares >=3.12,<3.15, and uses `uv_build`.
  Dagster and dagster-webserver are pinned; commit `uv.lock` with dependency changes.
- Install with `uv sync --locked`; smoke-check the installed CLI with
  `uv run cognyx-takehome --help` and `uv run cognyx-takehome status`.
  Validate packaging with `uv build`, not only an import check.
- See README.md for ingest/server/reconcile commands. The local application stores
  are `.local/cognyx/bom.db` and `technical_notes.db`; Dagster metadata/logs are
  separate beneath that directory. Runtime files must stay untracked.
- Generate the checked-in synthetic fixtures with:
  `uv run python -m cognyx_takehome.generate_data`.
- Run all tests with `uv run --locked python -m unittest discover -s tests -v`.
  Fixture tests validate authored scenarios; ingestion tests use temporary SQLite
  stores; Dagster tests exercise real checks, failures and downstream gating.
  No reuse-analysis engine or lint configuration exists yet.
- Keep raw inputs immutable. Apply corrections only in derived rows with rule
  and source evidence. Full-note extraction templates are deliberately bounded.
  Default append must not silently count re-exports; override replaces one family
  atomically and invalidates derived state across both stores.
- Distinguish completed imports, incomplete reconciliation, unresolved WARN findings,
  and blocking ERROR checks. A successful run does not mean engineering approval.
- `data/manifest.json` defines CSV and quantity semantics. Keep the raw input
  files separate from `data/expected/findings.json`, which is an evaluation oracle
  and must never be an input to the future analyzer.
- Use synthetic data for the exercise. Preserve source references and make
  normalization, uncertainty, and inconsistency findings explainable.
- Distinguish observed reuse from candidate reusability requiring engineering
  validation. Label invented costs, metrics, and savings as assumptions.
- Account for the brief's eventual in-network deployment constraint when making
  architecture decisions; distinguish demo behavior from production proposals.

## Skills and delivery

GStack is installed locally at `/Users/pierre.delabelliere/gstack`, exposed through
`/Users/pierre.delabelliere/.claude/skills/gstack` and sibling skill directories.
Read the applicable `SKILL.md` before using a skill and use it when relevant to the
task. Do not assume a slash command is registered in every agent runtime. Keep
project documentation and handoffs in the vault even when a skill has a different
default artifact location. Do not copy or reinstall the skill suite unnecessarily.

The brief eventually requires a shareable Git repository, short README, AI-work
trace, a pre-session email, and a demo. The private Obsidian vault alone is not a
shareable submission. Decide and record how to include a suitable trace when
preparing delivery. Email preparation is distinct from authorization to send it.
