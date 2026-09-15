"""Cognyx local ingestion demonstration."""


def main() -> None:
    from .cli import main as cli_main
    cli_main()
