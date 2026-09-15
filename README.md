# Cognyx take-home

A take-home project exploring sub-assembly reuse across train variants using
synthetic bill-of-materials data and technical notes.

**Status:** reproducible synthetic data and fixture checks are available. The main
console command still prints a greeting; ingestion, normalization, and reuse
analysis are not implemented yet.

## Synthetic pilot data

The checked-in [data](data/) covers three fictional train variants and selected
cabin-lighting, HVAC-filter, and passenger-information assemblies:

- [bom.csv](data/bom.csv): 118 raw parent-child records with stable source IDs.
- [technical_notes.csv](data/technical_notes.csv): 20 French, English, and mixed notes.
- [variants.csv](data/variants.csv): three variant roots and the snapshot scope.
- [manifest.json](data/manifest.json): provenance, field semantics, counts, and hashes.
- [expected/findings.json](data/expected/findings.json): 21 evaluation scenarios;
  **never use this answer key as analyzer input**.

Version 2 focuses on **finding new uses for existing designs**. There are eight
distinct assembly designs across nine variant placements. Only LGT-100 is already
shared (REG-A/B, with a reference typo in B). Four directional candidate comparisons
ask whether an existing donor could replace a different design at a future tender:

| Existing donor | Target | Evidence and outstanding check |
| --- | --- | --- |
| LGT-200 on REG-C | LGT-100 on REG-A/B | Same mount/supply, different diffuser; verify target-interior photometry. |
| FLT-150 on REG-B | FLT-100 on REG-A | Same filter/interface, folding handle; verify maintenance handling. |
| FLT-200 on REG-C | FLT-100 on REG-A | Cold-rated cassette covers the nominal temperature need; verify target-duct airflow/sealing. |
| CAB-240 on REG-A | CAB-245 on REG-B | Same electrical interface, sealed versus vented door; verify thermal behavior in the hotter target bay. |

These are unapproved engineering-review candidates, not aliases to merge. Reverse
substitution can fail on glare, clearance, temperature, or door requirements. The
110 V cabinet remains a negative example against the 24 V designs. All designs
already exist on their listed variants; novelty is their proposed use elsewhere.

All names, identifiers, dimensions, and technical statements are invented; these
are not Alstom data or validated engineering designs. The data intentionally mixes
reference typos, units, decimal formats, duplicate rows, missing values, and a
conflicting dimension. It also includes valid differences that must remain:
voltage, revision, and material. Observed reuse is distinct from a candidate
requiring engineering approval. No costs or savings are asserted.

CSV files are UTF-8 with comma delimiters and headers. Quantities are **per parent**;
train-level counts multiply child quantities. Blank quantities mean unknown.
The generator uses only the Python 3.9 standard library and runs offline:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m cognyx_takehome.generate_data
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Regeneration replaces the named dataset files deterministically. Use
`--output /tmp/cognyx-data-preview` to generate a separate copy. Fixture checks
verify reproducibility, source links, hierarchy, and the authored scenarios;
they do not validate an analysis engine.

## Scaffold check

From the repository root with Python 3.9 or later:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -c 'from cognyx_takehome import main; main()'
```

Expected output: `Hello from cognyx-takehome!`

The package declares a `cognyx-takehome` console command and uses `uv_build`.
Dependency installation and the installed command have not yet been validated.

## Working on the project

All agents follow [AGENTS.md](AGENTS.md). Decisions, discussions, technical and
business documentation, and the change-by-change `HANDOFF.md` live in the local
Obsidian directory:

`/Users/pierre.delabelliere/Obsidian/pierre-dlb/cognyx-takehome`

Start with `02 - Project Hub.md` there. This private vault is not included in the
repository; evaluator-facing setup, examples, and the shareable AI-work trace will
be completed with the demo.
