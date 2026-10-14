"""EP-00.01 safety checks: K-01, E-09.01, E-10.03, ADR-001; F-08.01 boundary."""

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.bootstrap

SAFE_IMPORT_SCRIPT = """
import _thread
import os
import sys
import threading


def deny_background_work(*args, **kwargs):
    raise AssertionError("Package import attempted to start background work.")


def guard_import_effects(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in {
        "os.system", "os.posix_spawn", "os.spawn", "os.startfile"
    }:
        raise AssertionError(f"Package import attempted an external effect: {event}")
    if event == "open" and isinstance(args[0], (str, bytes)):
        name = os.path.basename(os.fsdecode(args[0])).lower()
        if name == ".env" or name.startswith(".env.") or (
            name.startswith(("credentials.", "token."))
            and name.endswith((".json", ".pickle", ".pkl"))
        ):
            raise AssertionError("Package import attempted to read private configuration.")


threading.Thread.start = deny_background_work
_thread.start_new_thread = deny_background_work
sys.addaudithook(guard_import_effects)

import acoa
import acoa.config

assert acoa.__file__, "The installed package must have a source file."
print(acoa.__name__)
"""


def run_isolated_import(working_directory: Path) -> subprocess.CompletedProcess[str]:
    """Import the installed package outside the repo without inherited credentials."""
    environment = {
        name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ
    }
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", SAFE_IMPORT_SCRIPT],
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_import_without_configuration_or_external_effects(tmp_path: Path) -> None:
    """A fresh process imports without network, subprocess, thread, or .env access."""
    result = run_isolated_import(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "acoa"
    assert result.stderr == ""


def test_installed_package_has_no_runtime_dependencies() -> None:
    """The bootstrap installs without any optional live integration dependency."""
    metadata = importlib.metadata.metadata("acoa")
    requirements = importlib.metadata.requires("acoa") or []

    assert metadata["Name"] == "acoa"
    assert metadata["Version"] == "0.1.0"
    assert all("extra == 'dev'" in requirement.replace('"', "'") for requirement in requirements)
