"""Local CLI. UI and CLI share persistent Dagster run history and application data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .observability import configure
from .storage import status


def runtime(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    home = directory / "dagster"
    home.mkdir(exist_ok=True)
    config = home / "dagster.yaml"
    if not config.exists():
        config.write_text("telemetry:\n  enabled: false\n", encoding="utf-8")
    os.environ["DAGSTER_HOME"] = str(home)
    os.environ["COGNYX_DATA_DIR"] = str(directory)
    configure(directory)
    return directory


def parser():
    root = argparse.ArgumentParser(description="Ingest BOM/notes locally with traceable Dagster data checks.")
    root.add_argument("--data-dir", default=os.environ.get("COGNYX_DATA_DIR", ".local/cognyx"))
    commands = root.add_subparsers(dest="command", required=True)
    server = commands.add_parser("server", help="Start the local Dagster dashboard (foreground).")
    server.add_argument("--port", type=int, default=3000)
    mcp = commands.add_parser("mcp", help="Read-only BOM and notes MCP for local assistants.")
    mcp_commands = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_start = mcp_commands.add_parser("start", help="Serve MCP over stdio; the client owns this process.")
    mcp_start.add_argument("--data-dir", default=argparse.SUPPRESS)
    ingest_parser = commands.add_parser("ingest", help="Add inputs; identical records are skipped.")
    inputs = ingest_parser.add_subparsers(dest="kind", required=True)
    for kind in ("bom", "technical-notes"):
        command = inputs.add_parser(kind)
        command.add_argument("path", type=Path)
        command.add_argument("--override", action="store_true", help="Atomically replace this input family; preserve the other family.")
        command.add_argument("--data-dir", default=argparse.SUPPRESS)
        if kind == "bom":
            command.add_argument("--variants", type=Path, required=True)
    for name, help_text in (("status", "Show input counts, freshness and outstanding issues."),
                            ("findings", "Print quality findings with row/note evidence."),
                            ("reconcile", "Rebuild derived data and run checks against current inputs.")):
        commands.add_parser(name, help=help_text)
    for command in commands.choices.values():
        command.add_argument("--data-dir", default=argparse.SUPPRESS)
    return root


def main():
    args = parser().parse_args()
    if args.command == "mcp":
        # MCP stdout is protocol-only; do not initialize Dagster or create stores.
        from .mcp import serve
        serve(args.data_dir)
        return
    directory = runtime(args.data_dir)
    if args.command in {"status", "findings"}:
        snapshot = status(directory)
        print(json.dumps(snapshot["findings"] if args.command == "findings" else
                         {k: v for k, v in snapshot.items() if k != "findings"}, ensure_ascii=False, indent=2))
        return
    if args.command == "server":
        command = [str(Path(sys.executable).with_name("dagster")), "dev", "-m", "cognyx_takehome.definitions",
                   "--host", "127.0.0.1", "--port", str(args.port)]
        raise SystemExit(subprocess.call(command))
    # Import after setting env so code-location defaults match this invocation.
    import dagster as dg
    from .definitions import defs
    run_config = {"resources": {"store": {"config": {"directory": str(directory)}}}}
    job_name = "reconcile"
    if args.command == "ingest":
        asset_name = "bom_raw" if args.kind == "bom" else "technical_notes_raw"
        job_name = "ingest_bom" if args.kind == "bom" else "ingest_technical_notes"
        config = {"path": str(args.path.resolve()), "override": args.override}
        if args.kind == "bom":
            config["variants"] = str(args.variants.resolve())
        run_config["ops"] = {asset_name: {"config": config}}
    job = defs.resolve_job_def(job_name)
    with dg.DagsterInstance.get() as instance:
        result = job.execute_in_process(instance=instance, run_config=run_config, raise_on_error=False)
    snapshot = status(directory)
    print(json.dumps({"run_id": result.run_id, "success": result.success,
                      **{k: v for k, v in snapshot.items() if k != "findings"}}, ensure_ascii=False, indent=2))
    if not result.success:
        raise SystemExit(1)
