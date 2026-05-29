from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any


TELEMETRY_FILENAME = "latest.json"
_PATH_KEYS = {
    "corpus_root": "configured corpus",
    "output_root": "generated output",
    "state_root": "state root redacted",
    "telemetry_root": "telemetry root redacted",
    "adk_trace_db": "adk trace db redacted",
    "adk_eval_dir": "adk eval dir redacted",
    "prompt_profile_path": "prompt profile path redacted",
}


def sanitize_public_config(config: dict[str, Any]) -> dict[str, Any]:
    public = dict(config)
    for key, replacement in _PATH_KEYS.items():
        if key in public and public[key]:
            public[key] = replacement
    if public.get("api_key"):
        public["api_key"] = "redacted"
    return public


def build_telemetry(config: dict[str, Any], diff: dict[str, list[str]], scan: dict[str, Any]) -> dict[str, Any]:
    files = scan.get("files", {})
    total = len(files)
    changed = len(diff.get("changed", []))
    added = len(diff.get("added", []))
    removed = len(diff.get("removed", []))
    unchanged = len(diff.get("unchanged", []))
    coverage = 0.0 if total == 0 else round((total - len([v for v in files.values() if v.get("error")])) / total, 4)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": sanitize_public_config(config),
        "scan": {
            "total_files": total,
            "added": added,
            "changed": changed,
            "removed": removed,
            "unchanged": unchanged,
            "coverage_ratio": coverage,
        },
        "diff": diff,
        "observability": {
            "adk_enabled": bool(config.get("use_adk")),
            "pass_1": "scan_and_analyze",
            "pass_2": "verify_and_refine",
        },
        "notes": [
            "scaffold_phase",
            "source-summary-stubs-enabled",
            "full_llm_synthesis_pending",
            "discovery-views-enabled",
        ],
    }


def write_telemetry(telemetry_root: Path, telemetry: dict[str, Any]) -> Path:
    telemetry_root.mkdir(parents=True, exist_ok=True)
    path = telemetry_root / TELEMETRY_FILENAME
    path.write_text(json.dumps(telemetry, indent=2, sort_keys=True), encoding="utf-8")
    return path
