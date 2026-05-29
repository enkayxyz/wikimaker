from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sys
import time
from typing import Any, Callable, TypeVar


T = TypeVar("T")
LLM_CALL_LOG = "llm_calls.jsonl"
CURRENT_CALL = "current.json"
_URL_RE = re.compile(r"https?://[^\s'\"<>]+")
_ABS_PATH_RE = re.compile(r"(/Users|/private|/Volumes|/home)/[^\s'\"<>]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _boolish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _telemetry_root(config: dict[str, Any]) -> Path:
    return Path(str(config.get("telemetry_root") or ".")).expanduser()


def _safe_meta(meta: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "call_id",
        "stage",
        "role",
        "model",
        "index",
        "total",
        "relative_path",
        "cache_status",
        "fallback_used",
        "prompt_chars",
        "response_chars",
        "timeout_seconds",
    }
    safe: dict[str, Any] = {}
    for key in allowed:
        if key in meta and meta[key] not in (None, ""):
            value = meta[key]
            if key == "relative_path":
                text = str(value)
                safe[key] = Path(text).name if Path(text).is_absolute() else text
            else:
                safe[key] = value
    return safe


def sanitize_error(value: Any) -> str:
    text = str(value or "")
    text = _URL_RE.sub("[endpoint]", text)
    text = _ABS_PATH_RE.sub("[path]", text)
    return text[:500]


def _append_jsonl(config: dict[str, Any], payload: dict[str, Any]) -> None:
    root = _telemetry_root(config)
    root.mkdir(parents=True, exist_ok=True)
    with (root / LLM_CALL_LOG).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_current(config: dict[str, Any], payload: dict[str, Any]) -> None:
    root = _telemetry_root(config)
    root.mkdir(parents=True, exist_ok=True)
    (root / CURRENT_CALL).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _console(event: str, payload: dict[str, Any]) -> None:
    meta = payload.get("meta", {})
    pieces = [f"llm {event}"]
    for key in ("stage", "role", "index", "total", "relative_path", "cache_status", "model", "timeout_seconds", "duration_ms", "status"):
        value = meta.get(key, payload.get(key))
        if value not in (None, ""):
            label = "timeout" if key == "timeout_seconds" else key
            pieces.append(f"{label}={value}")
    print(" ".join(str(piece) for piece in pieces), flush=True)


def monitored_call(config: dict[str, Any], meta: dict[str, Any], fn: Callable[[], T]) -> T:
    call_meta = _safe_meta(meta)
    call_id = str(call_meta.get("call_id") or f"{call_meta.get('stage', 'llm')}-{int(time.time() * 1000)}")
    call_meta["call_id"] = call_id
    start = {"event": "llm_call_start", "time": _utc_now(), "meta": call_meta}
    _append_jsonl(config, start)
    _write_current(config, {**start, "status": "running"})
    if _boolish(config.get("llm_debug")):
        _console("start", start)
    started = time.monotonic()
    try:
        result = fn()
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        fail = {
            "event": "llm_call_fail",
            "time": _utc_now(),
            "duration_ms": duration_ms,
            "status": "fail",
            "error": sanitize_error(exc),
            "meta": call_meta,
        }
        _append_jsonl(config, fail)
        _write_current(config, fail)
        if _boolish(config.get("llm_debug")):
            _console("fail", fail)
        raise
    duration_ms = int((time.monotonic() - started) * 1000)
    done_meta = dict(call_meta)
    if isinstance(result, str):
        done_meta["response_chars"] = len(result)
    done = {
        "event": "llm_call_done",
        "time": _utc_now(),
        "duration_ms": duration_ms,
        "status": "ok",
        "meta": done_meta,
    }
    _append_jsonl(config, done)
    _write_current(config, done)
    if _boolish(config.get("llm_debug")):
        _console("done", done)
    return result


def summarize_llm_calls(telemetry_root: Path) -> dict[str, Any]:
    path = telemetry_root / LLM_CALL_LOG
    if not path.exists():
        return {"total": 0, "failed": 0, "timeouts": 0, "done": 0, "total_duration_ms": 0}
    total = failed = timeouts = done = duration = 0
    current_stage = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        event = item.get("event")
        if event == "llm_call_start":
            total += 1
            current_stage = str((item.get("meta") or {}).get("stage") or current_stage)
        elif event == "llm_call_fail":
            failed += 1
            if "timeout" in str(item.get("error") or "").lower():
                timeouts += 1
            duration += int(item.get("duration_ms") or 0)
        elif event == "llm_call_done":
            done += 1
            duration += int(item.get("duration_ms") or 0)
    return {"total": total, "failed": failed, "timeouts": timeouts, "done": done, "total_duration_ms": duration, "current_stage": current_stage}
