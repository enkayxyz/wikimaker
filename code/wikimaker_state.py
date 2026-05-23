from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
from typing import Any


STATE_FILENAME = "corpus_snapshot.json"


@dataclass(slots=True)
class FileRecord:
    path: str
    sha256: str
    size: int
    mtime_ns: int
    title: str
    headings: list[str]
    source_links: list[str]


def load_snapshot(state_root: Path) -> dict[str, Any]:
    path = state_root / STATE_FILENAME
    if not path.exists():
        return {"files": {}, "generated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(state_root: Path, snapshot: dict[str, Any]) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    path = state_root / STATE_FILENAME
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return path


def hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def diff_snapshots(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    prev_files = previous.get("files", {})
    curr_files = current.get("files", {})
    prev_keys = set(prev_files)
    curr_keys = set(curr_files)
    return {
        "added": sorted(curr_keys - prev_keys),
        "removed": sorted(prev_keys - curr_keys),
        "changed": sorted(
            path for path in (prev_keys & curr_keys)
            if prev_files[path].get("sha256") != curr_files[path].get("sha256")
        ),
        "unchanged": sorted(
            path for path in (prev_keys & curr_keys)
            if prev_files[path].get("sha256") == curr_files[path].get("sha256")
        ),
    }
