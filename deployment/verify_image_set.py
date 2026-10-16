"""Verify the active source set and exact local Docker images for EP-10.01."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import cast

SCHEMA = "acoa-portable-images/1"
REQUIRED_SERVICES = frozenset(("postgres", "migration", "browser", "sandbox"))
LOCK_PATH = "deployment/images.lock.json"


class ImageSetError(ValueError):
    """A portable image-set check failed without exposing private configuration."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha256(value: object, *, prefix: str = "") -> str:
    text = value if isinstance(value, str) else ""
    raw = text.removeprefix(prefix)
    if len(raw) != 64 or any(character not in "0123456789abcdef" for character in raw):
        raise ImageSetError("The image lock contains an invalid SHA-256 value.")
    return text


def _manifest_entries(root: Path) -> tuple[tuple[str, str], ...]:
    root = root.resolve()
    lines = (root / "SHA256SUMS.md").read_text(encoding="utf-8").splitlines()[8:]
    entries: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for line in lines:
        digest, separator, relative_path = line.partition("  ")
        if not separator or not relative_path:
            raise ImageSetError("The active-file manifest has an invalid entry.")
        _require_sha256(digest)
        manifest_path = PurePosixPath(relative_path)
        if (
            manifest_path.is_absolute()
            or ".." in manifest_path.parts
            or "\\" in relative_path
            or relative_path in seen_paths
        ):
            raise ImageSetError("The active-file manifest contains an unsafe path.")
        seen_paths.add(relative_path)
        path = (root / Path(*manifest_path.parts)).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ImageSetError("The active-file manifest escapes the repository root.") from None
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != digest:
            raise ImageSetError(f"Active-file integrity failed for {relative_path}.")
        if relative_path != LOCK_PATH:
            entries.append((digest, relative_path))
    return tuple(entries)


def source_set_sha256(root: Path) -> str:
    """Hash verified manifest entries without creating a lock/manifest cycle."""
    content = "".join(f"{digest}  {path}\n" for digest, path in _manifest_entries(root))
    return _sha256_bytes(content.encode("utf-8"))


def load_image_lock(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ImageSetError("The portable image lock is unreadable or invalid.") from error
    if not isinstance(value, dict) or set(value) != {"schema", "source_set_sha256", "images"}:
        raise ImageSetError("The portable image lock has unsupported fields.")
    if value["schema"] != SCHEMA:
        raise ImageSetError("The portable image lock schema is unsupported.")
    _require_sha256(value["source_set_sha256"])
    images = value["images"]
    if not isinstance(images, dict) or set(images) != REQUIRED_SERVICES:
        raise ImageSetError("The portable image lock must cover every deployment image.")
    for record in images.values():
        if not isinstance(record, dict) or set(record) != {"reference", "image_id", "platform"}:
            raise ImageSetError("A portable image record has unsupported fields.")
        if not isinstance(record["reference"], str) or not record["reference"]:
            raise ImageSetError("Every portable image requires an explicit reference.")
        _require_sha256(record["image_id"], prefix="sha256:")
        if record["platform"] not in ("linux/amd64", "linux/arm64"):
            raise ImageSetError("Portable images require an explicit supported Linux platform.")
    return value


def _inspect_image(docker: str, reference: str) -> tuple[str, str]:
    command = [
        docker,
        "image",
        "inspect",
        reference,
        "--format",
        "{{.Id}} {{.Os}}/{{.Architecture}}",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ImageSetError("Docker image inspection could not be completed.") from error
    values = result.stdout.strip().split()
    if result.returncode or len(values) != 2:
        raise ImageSetError("A required locked image is unavailable to Docker.")
    return values[0], values[1]


def verify_image_set(root: Path, docker: str) -> dict[str, str]:
    lock = load_image_lock(root / LOCK_PATH)
    actual_source = source_set_sha256(root)
    if actual_source != lock["source_set_sha256"]:
        raise ImageSetError("The image lock belongs to a different verified source set.")
    images = cast(dict[str, dict[str, str]], lock["images"])
    for record in images.values():
        actual = _inspect_image(docker, record["reference"])
        if actual != (record["image_id"], record["platform"]):
            raise ImageSetError("A local image does not match the locked content identity.")
    canonical = json.dumps(images, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"source_set_sha256": actual_source, "image_set_sha256": _sha256_bytes(canonical)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--docker", default="docker")
    arguments = parser.parse_args()
    try:
        result = verify_image_set(arguments.root.resolve(), arguments.docker)
    except ImageSetError as error:
        parser.exit(1, f"image-set verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
