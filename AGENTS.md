# Agent instructions

## Purpose and current state

This is the Cognyx Forward Deployed Engineer take-home project: a small working
tool that ingests synthetic multi-variant BOM data and technical notes, normalizes
them, and explains sub-assembly reuse opportunities and data inconsistencies.
The brief recommends no more than four hours of preparation. Favor a working,
well-prioritized demonstration with evidence and clear limitations.

The repository currently contains a Python scaffold, not an implemented demo.
Do not describe planned capabilities as shipped.

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
- The scaffold pins Python 3.9 in `.python-version`, declares Python >=3.9,
  and uses `uv_build`. Revisit runtime/tooling choices explicitly before changing them.
- The current scaffold smoke check is:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -c 'from cognyx_takehome import main; main()'`.
- Once dependencies are installed with `uv sync`, the declared entry point is
  `uv run cognyx-takehome`. Do not treat an import smoke check as packaging validation.
- No test suite or lint configuration exists yet. Add meaningful checks with the
  implemented behavior; record the commands here when the workflow changes.
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
