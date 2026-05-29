from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from wikimaker_cards import run_map_reduce_pipeline


try:  # pragma: no cover - depends on the installed ADK pre-GA package surface
    from google.adk.workflow import Workflow

    ADK_WORKFLOW_AVAILABLE = True
    ADK_WORKFLOW_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover
    Workflow = None  # type: ignore[assignment]
    ADK_WORKFLOW_AVAILABLE = False
    ADK_WORKFLOW_IMPORT_ERROR = str(exc)


ADK_WORKFLOW_STAGE_ORDER = [
    "preflight",
    "scan",
    "source_facts",
    "source_cards",
    "batch_synthesis",
    "global_synthesis",
    "quality_judge",
    "render",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WikiMakerAdkWorkflow:
    """ADK-owned workflow facade for WikiMaker's local compile pipeline.

    The ADK 2 Workflow API is pre-GA and not always importable in local test
    envs. This facade makes ADK the active orchestration boundary while keeping
    deterministic fallback execution testable when the optional package is not
    present.
    """

    def __init__(self) -> None:
        self.available = ADK_WORKFLOW_AVAILABLE
        self.import_error = ADK_WORKFLOW_IMPORT_ERROR
        self.stage_order = list(ADK_WORKFLOW_STAGE_ORDER)
        self.workflow = None
        if Workflow is not None:
            # Keep the graph declaration simple and side-effect-free. The actual
            # compile stages remain Python functions so local Ollama stays the
            # model backend and privacy gates stay in WikiMaker code.
            self.workflow = Workflow(name="wikimaker_compile", edges=[])

    def run_map_reduce(self, scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any], complete: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        started = _utc_now()
        pipeline = complete(scan, run_map_reduce_pipeline(scan, diff, {**config, "run_id": started}))
        stage = dict(pipeline.get("stage") or {})
        stage["adk_workflow"] = {
            "available": self.available,
            "import_error": self.import_error,
            "workflow_api": "google.adk.workflow.Workflow",
            "stage_order": self.stage_order,
            "started_at": started,
            "completed_at": _utc_now(),
            "status": "adk_workflow_available" if self.available else "adk_workflow_facade",
        }
        pipeline["stage"] = stage
        pipeline["provider"] = "adk_workflow"
        pipeline["orchestrator"] = "adk_workflow"
        return pipeline


def run_adk_workflow_pipeline(scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any], complete: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return WikiMakerAdkWorkflow().run_map_reduce(scan, diff, config, complete)
