"""Fail-closed runner for short-lived generated Python helpers; EP-09.03."""

import ast
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import cast

SANDBOX_ROOT = Path("/opt/acoa-sandbox")
SECRETS_ROOT = Path("/run/secrets")
MAX_SOURCE_BYTES = 32_768
MAX_INPUT_BYTES = 65_536
MAX_OUTPUT_BYTES = 65_536
MAX_TIMEOUT_SECONDS = 10
FORBIDDEN_CALLS = frozenset(
    {"breakpoint", "compile", "eval", "exec", "input", "open", "__import__"}
)


class SandboxRequestError(ValueError):
    pass


def _has_default_route(route_file: Path = Path("/proc/net/route")) -> bool:
    try:
        rows = route_file.read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return True
    return any(
        len(columns := row.split()) >= 4 and columns[1] == "00000000" and int(columns[3], 16) & 1
        for row in rows
    )


def _root_is_read_only() -> bool:
    probe = SANDBOX_ROOT / ".write-probe"
    try:
        probe.write_bytes(b"probe")
    except OSError:
        return True
    probe.unlink(missing_ok=True)
    return False


def _secrets_are_absent() -> bool:
    try:
        return not SECRETS_ROOT.exists() or next(SECRETS_ROOT.iterdir(), None) is None
    except OSError:
        return False


def self_check() -> dict[str, object]:
    checks = {
        "sandbox_marker": os.environ.get("ACOA_GENERATED_CODE_SANDBOX") == "1",
        "non_root": hasattr(os, "getuid") and os.getuid() != 0,
        "network_disabled": not _has_default_route(),
        "read_only_root": _root_is_read_only(),
        "secrets_absent": _secrets_are_absent(),
    }
    return {"ok": all(checks.values()), "checks": checks}


def _request(payload: object) -> tuple[str, str, int, int]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "source",
        "input",
        "timeout_seconds",
        "max_output_bytes",
    }:
        raise SandboxRequestError("invalid_request_shape")
    source = payload["source"]
    timeout = payload["timeout_seconds"]
    output_limit = payload["max_output_bytes"]
    if payload["schema"] != "acoa-generated-tool/1" or not isinstance(source, str):
        raise SandboxRequestError("invalid_request_schema")
    source_bytes = source.encode("utf-8")
    input_json = json.dumps(payload["input"], sort_keys=True, separators=(",", ":"))
    if not source_bytes or len(source_bytes) > MAX_SOURCE_BYTES:
        raise SandboxRequestError("source_limit")
    if len(input_json.encode("utf-8")) > MAX_INPUT_BYTES:
        raise SandboxRequestError("input_limit")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= MAX_TIMEOUT_SECONDS
    ):
        raise SandboxRequestError("timeout_limit")
    if (
        isinstance(output_limit, bool)
        or not isinstance(output_limit, int)
        or not 1 <= output_limit <= MAX_OUTPUT_BYTES
    ):
        raise SandboxRequestError("output_limit")
    _validate_source(source)
    return source, input_json, timeout, output_limit


def _validate_source(source: str) -> None:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        raise SandboxRequestError("invalid_python") from None
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
        raise SandboxRequestError("imports_forbidden")
    if any(
        isinstance(node, ast.Attribute) and node.attr.startswith("__") for node in ast.walk(tree)
    ):
        raise SandboxRequestError("dunder_access_forbidden")
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in FORBIDDEN_CALLS
        for node in ast.walk(tree)
    ):
        raise SandboxRequestError("dangerous_builtin_forbidden")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "transform" or len(functions[0].args.args) != 1:
        raise SandboxRequestError("transform_contract_required")
    if any(not isinstance(node, ast.FunctionDef) for node in tree.body):
        raise SandboxRequestError("top_level_execution_forbidden")


def _limits(timeout_seconds: int, output_bytes: int) -> None:
    resource_module = import_module("resource")
    set_limit = cast(Callable[[int, tuple[int, int]], None], resource_module.setrlimit)
    for name, limits in (
        ("RLIMIT_CPU", (timeout_seconds, timeout_seconds)),
        ("RLIMIT_FSIZE", (output_bytes, output_bytes)),
        ("RLIMIT_NOFILE", (16, 16)),
        ("RLIMIT_NPROC", (1, 1)),
    ):
        set_limit(cast(int, getattr(resource_module, name)), limits)


def run_request(payload: object) -> dict[str, object]:
    try:
        source, input_json, timeout, output_limit = _request(payload)
    except SandboxRequestError as error:
        return {"state": "rejected", "reason": str(error)}
    safe_builtin_names = (
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "filter",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    )
    runner = (
        "import builtins\nimport json\n"
        + f"_names = {safe_builtin_names!r}\n"
        + "_safe = {name: getattr(builtins, name) for name in _names}\n"
        + "_namespace = {'__builtins__': _safe}\n"
        + f"exec(compile({source!r}, '<generated-tool>', 'exec'), _namespace)\n"
        + "_value = _namespace['transform'](json.loads(input()))\n"
        + "print(json.dumps(_value, sort_keys=True, separators=(',', ':')))\n"
    )
    try:
        with tempfile.TemporaryDirectory(prefix="acoa-tool-") as directory:
            script = Path(directory) / "tool.py"
            script.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(script)],
                input=input_json.encode("utf-8"),
                capture_output=True,
                timeout=timeout + 1,
                check=False,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONIOENCODING": "utf-8"},
                preexec_fn=lambda: _limits(timeout, output_limit),
            )
    except subprocess.TimeoutExpired:
        return {"state": "failed", "reason": "timeout"}
    except OSError:
        return {"state": "failed", "reason": "runner_error"}
    if completed.returncode != 0:
        return {"state": "failed", "reason": "tool_failed"}
    if len(completed.stdout) > output_limit:
        return {"state": "failed", "reason": "output_limit"}
    try:
        output = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return {"state": "failed", "reason": "invalid_output"}
    if not isinstance(output, dict):
        return {"state": "failed", "reason": "output_object_required"}
    return {"state": "succeeded", "output": output}


def main() -> int:
    command = tuple(sys.argv[1:])
    if command == ("self-check",):
        result = self_check()
    elif command == ("run",):
        try:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + MAX_SOURCE_BYTES + 4096)
            result = run_request(json.loads(raw))
        except (TypeError, ValueError):
            result = {"state": "rejected", "reason": "invalid_json"}
    else:
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("ok") is True or result.get("state") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
