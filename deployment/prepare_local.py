"""Generate local development passwords: EP-00.03; E-07; ADR-011/013."""

import argparse
import os
import secrets
from pathlib import Path

PASSWORD_FILES = (
    "postgres_admin_password",
    "postgres_migration_password",
    "postgres_app_password",
)


def create_password_file(path: Path) -> bool:
    """Create a random password exclusively, preserving any existing file."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as password_file:
        password_file.write(secrets.token_urlsafe(48) + "\n")
    return True


def prepare_local_secrets(directory: Path) -> int:
    """Create the development secret directory and count newly created files."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return sum(create_password_file(directory / name) for name in PASSWORD_FILES)


def main() -> None:
    """Parse an explicit output directory and report counts without secret values."""
    parser = argparse.ArgumentParser(description="Prepare ACOA local database passwords.")
    parser.add_argument(
        "--directory", type=Path, default=Path(__file__).resolve().parent / "secrets"
    )
    args = parser.parse_args()
    created = prepare_local_secrets(args.directory)
    print(f"Created {created} password files; existing files were preserved.")


if __name__ == "__main__":
    main()
