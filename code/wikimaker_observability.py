from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional observability dependency
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
    OTEL_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - depends on environment
    trace = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    OTEL_AVAILABLE = False
    OTEL_IMPORT_ERROR = exc



try:  # pragma: no cover - optional ADK evaluation dependency chain
    from google.adk.evaluation.base_eval_service import EvaluateConfig, EvaluateRequest, InferenceConfig, InferenceRequest
    from google.adk.evaluation.eval_case import EvalCase, Invocation
    from google.adk.evaluation.eval_metrics import EvalMetric, PrebuiltMetrics
    from google.adk.evaluation.in_memory_eval_sets_manager import InMemoryEvalSetsManager
    from google.adk.evaluation.local_eval_service import LocalEvalService
    from google.adk.telemetry.setup import OTelHooks, maybe_set_otel_providers
    from google.adk.telemetry.sqlite_span_exporter import SqliteSpanExporter
    from google.genai import types as genai_types

    ADK_OBSERVABILITY_AVAILABLE = True
    ADK_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on environment
    EvaluateConfig = None  # type: ignore[assignment]
    EvaluateRequest = None  # type: ignore[assignment]
    InferenceConfig = None  # type: ignore[assignment]
    InferenceRequest = None  # type: ignore[assignment]
    EvalCase = None  # type: ignore[assignment]
    Invocation = None  # type: ignore[assignment]
    EvalMetric = None  # type: ignore[assignment]
    PrebuiltMetrics = None  # type: ignore[assignment]
    InMemoryEvalSetsManager = None  # type: ignore[assignment]
    LocalEvalService = None  # type: ignore[assignment]
    OTelHooks = None  # type: ignore[assignment]
    maybe_set_otel_providers = None  # type: ignore[assignment]
    SqliteSpanExporter = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]
    ADK_OBSERVABILITY_AVAILABLE = False
    ADK_AVAILABLE = False
    ADK_OBSERVABILITY_IMPORT_ERROR = exc
else:
    ADK_OBSERVABILITY_IMPORT_ERROR = None


def configure_adk_tracing(config: dict[str, Any]) -> dict[str, Any]:
    """Configure ADK/OpenTelemetry tracing for this run.

    The tracing backend uses ADK's telemetry setup plus a local SQLite span
    exporter so we can inspect traces after a run without external services.
    """

    trace_db = str(config.get("adk_trace_db") or "")
    enabled = bool(config.get("enable_adk_tracing", True))
    result = {
        "enabled": False,
        "available": ADK_OBSERVABILITY_AVAILABLE,
        "trace_db": trace_db,
        "error": None,
    }

    if not enabled:
        result["error"] = "ADK tracing disabled in config."
        return result
    if not OTEL_AVAILABLE:
        result["error"] = f"OpenTelemetry unavailable; tracing disabled: {OTEL_IMPORT_ERROR}"
        return result
    if not ADK_AVAILABLE:
        result["error"] = "ADK unavailable; cannot configure tracing."
        return result
    if not ADK_OBSERVABILITY_AVAILABLE:
        result["error"] = f"ADK observability unavailable: {ADK_OBSERVABILITY_IMPORT_ERROR}"
        return result

    if not trace_db:
        result["error"] = "Missing adk_trace_db path."
        return result

    trace_path = Path(trace_db).expanduser()
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    if not trace_path.exists():
        trace_path.touch()

    hooks = OTelHooks(span_processors=[BatchSpanProcessor(SqliteSpanExporter(db_path=str(trace_path)))])
    resource = Resource.create(
        {
            "service.name": "wikimaker",
            "service.version": str(config.get("version", "alpha-v0001")),
            "wikimaker.provider": str(config.get("provider", "google")),
        }
    )
    maybe_set_otel_providers([hooks], otel_resource=resource)
    result["enabled"] = True
    return result


def build_eval_prompt(scan: dict[str, Any], diff: dict[str, list[str]]) -> str:
    compact = compact_scan_for_prompt(scan, diff, limit=12)
    return json.dumps(compact, indent=2, sort_keys=True)


def _collect_async_generator(async_gen):
    async def _collect():
        items = []
        async for item in async_gen:
            items.append(item)
        return items

    return asyncio.run(_collect())


def _get_any_attr(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def run_adk_self_eval(scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Local-only mode does not currently expose the ADK evaluation path."""

    return {
        "enabled": False,
        "available": False,
        "used": False,
        "error": "ADK evaluation is disabled in local-only Osaurus mode.",
        "eval_set_id": "wikimaker-self-check",
        "metric": "response_match_score",
    }
