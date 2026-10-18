"""Create a local Gmail OAuth token without printing credentials or token material."""

import argparse
import os
from importlib import import_module
from pathlib import Path
from typing import Any

SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorize the local ACOA Gmail pilot.")
    parser.add_argument("--client-secrets", type=Path, required=True)
    parser.add_argument("--token-output", type=Path, required=True)
    return parser.parse_args()


def installed_app_flow() -> Any:
    try:
        return import_module("google_auth_oauthlib.flow").InstalledAppFlow
    except (ImportError, AttributeError) as error:
        raise SystemExit(
            "Install the pinned deployment/gmail-requirements.txt dependencies first."
        ) from error


def write_token(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()
    if not args.client_secrets.is_file():
        raise SystemExit("The explicit desktop OAuth client-secrets file does not exist.")
    if args.token_output.exists():
        raise SystemExit("The token output already exists; it will not be overwritten.")
    flow = installed_app_flow().from_client_secrets_file(str(args.client_secrets), SCOPES)
    credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
    if set(credentials.scopes or ()) != set(SCOPES):
        raise SystemExit("Google did not grant the exact required Gmail scopes.")
    write_token(args.token_output, credentials.to_json())
    print(f"OAuth token stored at {args.token_output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
