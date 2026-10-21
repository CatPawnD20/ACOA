"""Track per-application Codex token usage without reading conversation content."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

REPORT_SCHEMA_VERSION = "acoa-codex-application-usage/1"
STAGES = ("research", "analysis", "cv", "form", "submission")
APPLICATION_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
TOKEN_EVENT_MARKER = b'"type":"token_count"'
READ_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int
    cache_write_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> TokenUsage:
        fields = (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
        )
        counters: list[int] = []
        for name in fields:
            counter = value.get(name, 0)
            if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
                raise ValueError(f"Token counter {name} must be a nonnegative integer.")
            counters.append(counter)
        return cls(*counters)

    def subtract(self, earlier: TokenUsage) -> TokenUsage:
        current = asdict(self)
        previous = asdict(earlier)
        delta = {name: current[name] - previous[name] for name in current}
        if any(value < 0 for value in delta.values()):
            raise ValueError("Codex token counters moved backwards; the session boundary changed.")
        return TokenUsage.from_mapping(delta)


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    recorded_at: str
    usage: TokenUsage


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _codex_root() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def _session_identifier() -> str:
    identifier = os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
    if not identifier:
        raise RuntimeError("CODEX_SESSION_ID or CODEX_THREAD_ID is required.")
    return identifier


def find_session_file(session_id: str) -> Path:
    matches = list((_codex_root() / "sessions").rglob(f"*{session_id}.jsonl"))
    if not matches:
        raise FileNotFoundError(f"No Codex session log was found for {session_id}.")
    return max(matches, key=lambda path: path.stat().st_mtime_ns)


def _token_snapshot(line: bytes) -> UsageSnapshot | None:
    if TOKEN_EVENT_MARKER not in line:
        return None
    try:
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("type") != "event_msg":
            return None
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            return None
        info = payload.get("info")
        if not isinstance(info, dict):
            return None
        usage = info.get("total_token_usage")
        if not isinstance(usage, dict):
            return None
        return UsageSnapshot(str(event["timestamp"]), TokenUsage.from_mapping(usage))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def read_latest_usage(session_file: Path) -> UsageSnapshot:
    """Read backwards and parse only the newest token-count event."""
    with session_file.open("rb") as stream:
        position = stream.seek(0, os.SEEK_END)
        remainder = b""
        while position:
            size = min(READ_CHUNK_SIZE, position)
            position -= size
            stream.seek(position)
            remainder = stream.read(size) + remainder
            lines = remainder.splitlines()
            if position and lines:
                remainder = lines.pop(0)
            else:
                remainder = b""
            for line in reversed(lines):
                snapshot = _token_snapshot(line)
                if snapshot is not None:
                    return snapshot
    raise RuntimeError("The Codex session does not contain a token-count event yet.")


def _application_key(value: str) -> str:
    if not APPLICATION_KEY.fullmatch(value):
        raise ValueError("Application key must use lowercase letters, digits, and hyphens.")
    return value


def _label(value: str) -> str:
    if not value or value != value.strip() or len(value) > 200:
        raise ValueError("Application label must be trimmed and at most 200 characters.")
    return value


def _stage(value: str) -> str:
    if value not in STAGES:
        raise ValueError(f"Application stage must be one of: {', '.join(STAGES)}.")
    return value


def _outcome(value: str) -> str:
    if value not in ("submitted", "abandoned", "failed"):
        raise ValueError("Application outcome must be submitted, abandoned, or failed.")
    return value


def _report_path(output_root: Path, application_key: str) -> Path:
    return output_root / f"{_application_key(application_key)}.json"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Usage report does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Usage report must be a JSON object.")
    report = cast(dict[str, Any], value)
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("Usage report schema is not supported.")
    return report


def _current_snapshot(report: dict[str, Any]) -> UsageSnapshot:
    session_id = _session_identifier()
    if report["codex_session_id"] != session_id:
        raise ValueError("An application report cannot span multiple Codex sessions.")
    return read_latest_usage(find_session_file(session_id))


def _usage_from_report(value: dict[str, object]) -> TokenUsage:
    return TokenUsage.from_mapping(value)


def _close_current_stage(report: dict[str, Any], snapshot: UsageSnapshot) -> None:
    previous = _usage_from_report(report["last_snapshot"]["usage"])
    delta = snapshot.usage.subtract(previous)
    report["stages"].append(
        {
            "stage": report["current_stage"],
            "started_at": report["last_snapshot"]["recorded_at"],
            "completed_at": snapshot.recorded_at,
            "usage": asdict(delta),
        }
    )
    report["last_snapshot"] = {
        "recorded_at": snapshot.recorded_at,
        "usage": asdict(snapshot.usage),
    }


def start_report(output_root: Path, application_key: str, label: str, stage: str) -> dict[str, Any]:
    _application_key(application_key)
    _label(label)
    _stage(stage)
    path = _report_path(output_root, application_key)
    if path.exists():
        raise FileExistsError(f"Usage report already exists: {path}")
    session_id = _session_identifier()
    snapshot = read_latest_usage(find_session_file(session_id))
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "application_key": application_key,
        "label": label,
        "codex_session_id": session_id,
        "status": "active",
        "outcome": None,
        "started_at": utc_now(),
        "completed_at": None,
        "current_stage": stage,
        "baseline": {
            "recorded_at": snapshot.recorded_at,
            "usage": asdict(snapshot.usage),
        },
        "last_snapshot": {
            "recorded_at": snapshot.recorded_at,
            "usage": asdict(snapshot.usage),
        },
        "stages": [],
        "totals": None,
    }
    _write_report(path, report)
    return report


def advance_report(output_root: Path, application_key: str, stage: str) -> dict[str, Any]:
    _stage(stage)
    path = _report_path(output_root, application_key)
    report = _load_report(path)
    if report["status"] != "active":
        raise ValueError("Only an active usage report can advance stages.")
    if report["current_stage"] == stage:
        raise ValueError("The next stage must differ from the current stage.")
    _close_current_stage(report, _current_snapshot(report))
    report["current_stage"] = stage
    _write_report(path, report)
    return report


def finish_report(output_root: Path, application_key: str, outcome: str) -> dict[str, Any]:
    _outcome(outcome)
    path = _report_path(output_root, application_key)
    report = _load_report(path)
    if report["status"] != "active":
        raise ValueError("Only an active usage report can be completed.")
    snapshot = _current_snapshot(report)
    _close_current_stage(report, snapshot)
    baseline = _usage_from_report(report["baseline"]["usage"])
    report["totals"] = asdict(snapshot.usage.subtract(baseline))
    report["status"] = "completed"
    report["outcome"] = outcome
    report["completed_at"] = utc_now()
    report["current_stage"] = None
    _write_report(path, report)
    return report


def _summary(report: dict[str, Any], path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "application_key": report["application_key"],
        "status": report["status"],
        "current_stage": report["current_stage"],
        "outcome": report["outcome"],
        "stages": [
            {
                "stage": item["stage"],
                "total_tokens": item["usage"]["total_tokens"],
            }
            for item in report["stages"]
        ],
        "totals": report["totals"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("private/application-usage"))
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("application_key", type=_application_key)
    start.add_argument("--label", required=True, type=_label)
    start.add_argument("--stage", choices=STAGES, default="research")

    advance = commands.add_parser("advance")
    advance.add_argument("application_key", type=_application_key)
    advance.add_argument("--stage", choices=STAGES, required=True)

    finish = commands.add_parser("finish")
    finish.add_argument("application_key", type=_application_key)
    finish.add_argument("--outcome", choices=("submitted", "abandoned", "failed"), required=True)

    status = commands.add_parser("status")
    status.add_argument("application_key", type=_application_key)
    return parser


def main() -> int:
    args = _parser().parse_args()
    path = _report_path(args.output_root, args.application_key)
    if args.command == "start":
        report = start_report(args.output_root, args.application_key, args.label, args.stage)
    elif args.command == "advance":
        report = advance_report(args.output_root, args.application_key, args.stage)
    elif args.command == "finish":
        report = finish_report(args.output_root, args.application_key, args.outcome)
    else:
        report = _load_report(path)
    print(json.dumps(_summary(report, path), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
