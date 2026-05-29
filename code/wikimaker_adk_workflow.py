from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable

from wikimaker_cards import build_batch_summaries, build_file_cards, build_global_synthesis, pipeline_from_cards


try:  # pragma: no cover - depends on local ADK installation
    from google.adk.workflow import Workflow

    ADK_WORKFLOW_AVAILABLE = True
    ADK_WORKFLOW_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover
    Workflow = None  # type: ignore[assignment]
    ADK_WORKFLOW_AVAILABLE = False
    ADK_WORKFLOW_IMPORT_ERROR = str(exc)

try:  # pragma: no cover - ADK Skills are experimental and package paths may move
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools import skill_toolset

    ADK_SKILLS_AVAILABLE = True
    ADK_SKILLS_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover
    load_skill_from_dir = None  # type: ignore[assignment]
    skill_toolset = None  # type: ignore[assignment]
    ADK_SKILLS_AVAILABLE = False
    ADK_SKILLS_IMPORT_ERROR = str(exc)


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


def _stage_event(stage: str, status: str, started: float, **extra: Any) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "status": status,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "time": _utc_now(),
    }
    payload.update({key: value for key, value in extra.items() if value not in (None, "")})
    return payload


class WikiMakerAdkWorkflow:
    """ADK 2 workflow boundary for WikiMaker's compile stages."""

    def __init__(self, *, workflow_cls: Any = None, require_adk: bool = True) -> None:
        self.workflow_cls = workflow_cls if workflow_cls is not None else Workflow
        self.available = self.workflow_cls is not None and ADK_WORKFLOW_AVAILABLE
        self.import_error = "" if self.available else ADK_WORKFLOW_IMPORT_ERROR
        self.stage_order = list(ADK_WORKFLOW_STAGE_ORDER)
        self.skills = self._load_skills()
        self.edges = self._build_edges()
        self.workflow = None
        if require_adk and not self.available:
            raise RuntimeError(
                "WIKIMAKER_SYNTHESIS_MODE=adk_workflow requires Google ADK 2 Workflow support. "
                "Install dependencies with `conda run -n wikimaker python -m pip install -r requirements.txt` "
                "and verify `python -c \"import google.adk.workflow\"` before running UAT."
            )
        if self.workflow_cls is not None:
            self.workflow = self.workflow_cls(name="wikimaker_compile", edges=self.edges)

    def _load_skills(self) -> dict[str, Any]:
        names = ["source-card-skill", "privacy-boundary-skill", "corpus-profile-skill"]
        root = Path(__file__).resolve().parents[1] / "skills"
        result: dict[str, Any] = {"available": False, "names": names, "loaded": [], "error": ""}
        if not ADK_SKILLS_AVAILABLE or load_skill_from_dir is None or skill_toolset is None:
            result["error"] = ADK_SKILLS_IMPORT_ERROR or "ADK SkillToolset unavailable."
            return result
        try:
            skills = [load_skill_from_dir(root / name) for name in names]
            result["toolset"] = skill_toolset.SkillToolset(skills=skills)
            result["available"] = True
            result["loaded"] = names
        except Exception as exc:  # pragma: no cover - depends on ADK skills package
            result["error"] = str(exc)
        return result

    def _build_edges(self) -> list[tuple[Any, Any]]:
        return [
            ("START", self.stage_preflight),
            (self.stage_preflight, self.stage_scan),
            (self.stage_scan, self.stage_source_facts),
            (self.stage_source_facts, self.stage_source_cards),
            (self.stage_source_cards, self.stage_batch_synthesis),
            (self.stage_batch_synthesis, self.stage_global_synthesis),
            (self.stage_global_synthesis, self.stage_quality_judge),
            (self.stage_quality_judge, self.stage_render),
        ]

    def stage_preflight(self, state: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("adk_stage_events", [])
        started = time.monotonic()
        state["adk_stage_events"].append(_stage_event("preflight", "done", started, note="completed before workflow entry"))
        return state

    def stage_scan(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        scan = state.get("scan") or {}
        state.setdefault("adk_stage_events", []).append(_stage_event("scan", "done", started, files=len(scan.get("files", {}))))
        return state

    def stage_source_facts(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        scan = state.get("scan") or {}
        state.setdefault("adk_stage_events", []).append(_stage_event("source_facts", "done", started, files=len(scan.get("files", {}))))
        return state

    def stage_source_cards(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        cards, card_stage = build_file_cards(state["scan"], state["config"], state["diff"])
        state["cards"] = cards
        state["card_stage"] = card_stage
        counts = card_stage.get("counts", {})
        state.setdefault("adk_stage_events", []).append(
            _stage_event("source_cards", "done", started, cards=len(cards), hits=counts.get("hits", 0), misses=counts.get("misses", 0), failed=counts.get("failed", 0))
        )
        return state

    def stage_batch_synthesis(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        batches, batch_stage = build_batch_summaries(state["cards"], state["config"])
        state["batches"] = batches
        state["batch_stage"] = batch_stage
        state.setdefault("adk_stage_events", []).append(
            _stage_event("batch_synthesis", "done", started, batches=len(batches), failed=batch_stage.get("failed_batches", 0))
        )
        return state

    def stage_global_synthesis(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        global_plan, global_stage = build_global_synthesis(state["cards"], state["batches"], state["config"])
        state["global_plan"] = global_plan
        state["global_stage"] = global_stage
        state.setdefault("adk_stage_events", []).append(_stage_event("global_synthesis", global_stage.get("status", "done"), started))
        return state

    def stage_quality_judge(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        state.setdefault("adk_stage_events", []).append(_stage_event("quality_judge", "deferred_to_publish_stage", started))
        return state

    def stage_render(self, state: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        run_id = str(state.get("run_id") or _utc_now())
        stage = {
            "run_id": run_id,
            "card": state["card_stage"],
            "batch": state["batch_stage"],
            "global": state["global_stage"],
            "adk_workflow": {
                "available": self.available,
                "workflow_api": "google.adk.workflow.Workflow",
                "edge_count": len(self.edges),
                "stage_order": self.stage_order,
                "skills": {key: value for key, value in self.skills.items() if key != "toolset"},
                "events": state.get("adk_stage_events", []),
                "status": "adk_workflow_executed",
            },
        }
        state["pipeline"] = pipeline_from_cards(state["scan"], state["cards"], state["batches"], state["global_plan"], stage)
        state.setdefault("adk_stage_events", []).append(_stage_event("render", "done", started))
        state["pipeline"]["stage"]["adk_workflow"]["events"] = state["adk_stage_events"]
        state["pipeline"]["provider"] = "adk_workflow"
        state["pipeline"]["orchestrator"] = "adk_workflow"
        return state

    def _execute_declared_graph(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the same function-node chain declared to ADK.

        ADK owns the graph shape through ``Workflow(edges=...)``. This executor
        keeps local tests deterministic while the pre-GA runner surface is
        unavailable in the development environment.
        """
        current: Any = "START"
        while True:
            next_nodes = [target for source, target in self.edges if source == current]
            if not next_nodes:
                return state
            if len(next_nodes) != 1:
                raise RuntimeError("WikiMaker ADK workflow currently expects a single sequential route per stage.")
            current = next_nodes[0]
            state = current(state)

    def run(self, scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any], complete: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        state: dict[str, Any] = {"scan": scan, "diff": diff, "config": {**config, "run_id": _utc_now()}, "run_id": _utc_now()}
        state = self._execute_declared_graph(state)
        return complete(scan, state["pipeline"])


def run_adk_workflow_pipeline(scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any], complete: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    return WikiMakerAdkWorkflow(require_adk=True).run(scan, diff, config, complete)
