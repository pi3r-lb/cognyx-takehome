# Cognyx take-home

A take-home project exploring sub-assembly reuse across train variants using
synthetic bill-of-materials data and technical notes.

**Status:** repository initialization. The current Python scaffold prints a greeting;
data ingestion, normalization, and reuse analysis are not implemented yet.

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
