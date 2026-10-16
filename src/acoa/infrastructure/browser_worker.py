"""Fail-closed entry point for the isolated browser worker container; EP-08.02."""

import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

EXPECTED_PLAYWRIGHT_VERSION = "1.64.0"
SANDBOX_ROOT = Path("/opt/acoa-browser")
SECRETS_ROOT = Path("/run/secrets")


def _has_default_route(route_file: Path = Path("/proc/net/route")) -> bool:
    try:
        rows = route_file.read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return True
    for row in rows:
        columns = row.split()
        if len(columns) >= 4 and columns[1] == "00000000" and int(columns[3], 16) & 1:
            return True
    return False


def _secrets_are_absent() -> bool:
    try:
        return not SECRETS_ROOT.exists() or next(SECRETS_ROOT.iterdir(), None) is None
    except OSError:
        return False


def _root_is_read_only() -> bool:
    probe = SANDBOX_ROOT / ".write-probe"
    try:
        probe.write_bytes(b"probe")
    except OSError:
        return True
    probe.unlink(missing_ok=True)
    return False


def _playwright_version() -> str | None:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return None


def _browser_runtime_is_available() -> bool:
    probe = (
        "from playwright.sync_api import sync_playwright; "
        "p=sync_playwright().start(); "
        "b=p.chromium.launch(headless=True); "
        "page=b.new_page(); page.set_content('<title>ACOA sandbox</title>'); "
        "assert page.title() == 'ACOA sandbox'; b.close(); p.stop()"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def self_check() -> dict[str, object]:
    checks = {
        "sandbox_marker": os.environ.get("ACOA_BROWSER_SANDBOX") == "1",
        "non_root": hasattr(os, "getuid") and os.getuid() != 0,
        "network_disabled": not _has_default_route(),
        "read_only_root": _root_is_read_only(),
        "secrets_absent": _secrets_are_absent(),
        "playwright_version": _playwright_version() == EXPECTED_PLAYWRIGHT_VERSION,
        "browser_runtime": _browser_runtime_is_available(),
    }
    return {"ok": all(checks.values()), "checks": checks}


def main() -> int:
    if tuple(sys.argv[1:]) != ("self-check",):
        return 2
    result = self_check()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
