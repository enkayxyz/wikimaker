from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from wikimaker_openai import _chat_completions, _require_local_llm_config


def build_quality_metrics(scan: dict[str, Any], pipeline: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    files = scan.get("files", {})
    source_files = len(files)
    generation = pipeline.get("generation", {}) if isinstance(pipeline.get("generation"), dict) else {}
    analysis = pipeline.get("analysis", {}) if isinstance(pipeline.get("analysis"), dict) else {}
    verification = pipeline.get("verification", {}) if isinstance(pipeline.get("verification"), dict) else {}
    source_pages = [page for page in generation.get("source_pages", []) if isinstance(page, dict)]
    graph_edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    graph_nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    pipeline_errors = [str(item) for item in pipeline.get("errors", [])]
    coverage_ratio = (len(source_pages) / source_files) if source_files else 1.0
    edge_density = (len(graph_edges) / source_files) if source_files else 0.0
    schema_fallback = any("schema" in item.lower() or "fallback" in item.lower() for item in pipeline_errors)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": source_files,
        "generated_source_pages": len(source_pages),
        "coverage_ratio": round(coverage_ratio, 4),
        "wiki_sets": len(generation.get("wiki_set_pages", []) or []),
        "topic_clusters": len(analysis.get("topic_clusters", []) or []),
        "entity_clusters": len(analysis.get("entity_clusters", []) or []),
        "graph_nodes": len(graph_nodes),
        "graph_edges": len(graph_edges),
        "edge_density": round(edge_density, 4),
        "pipeline_error_count": len(pipeline_errors),
        "schema_or_fallback_error": schema_fallback,
        "verification_approved": bool(verification.get("approved")),
        "verification_confidence": float(verification.get("confidence") or 0.0),
        "sample_files": int(pipeline.get("sample_files", 0) or 0),
    }


def deterministic_quality(metrics: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    source_files = int(metrics.get("source_files", 0) or 0)
    coverage_ratio = float(metrics.get("coverage_ratio", 0.0) or 0.0)
    edge_density = float(metrics.get("edge_density", 0.0) or 0.0)
    if source_files and coverage_ratio < 0.8:
        findings.append("LLM generated source-page coverage is below 80% of scanned files.")
    if source_files >= 10 and int(metrics.get("graph_edges", 0) or 0) == 0:
        findings.append("LLM generated zero graph edges for a multi-file corpus.")
    elif source_files >= 100 and edge_density < 0.05:
        findings.append("LLM graph edge density is very low for a large corpus.")
    if metrics.get("schema_or_fallback_error"):
        findings.append("At least one LLM stage used schema/fallback recovery.")
    if not metrics.get("verification_approved"):
        findings.append("LLM verification did not approve the generated wiki plan.")
    if float(metrics.get("verification_confidence", 0.0) or 0.0) < 0.4:
        findings.append("LLM verification confidence is low.")

    status = "healthy"
    if findings:
        status = "fail" if coverage_ratio < 0.5 or metrics.get("schema_or_fallback_error") else "warn"
    return {
        "status": status,
        "findings": findings,
        "recommendation": (
            "Do not trust the generated wiki structure yet. Rerun with a stronger local model, larger sample window, or improved corpus profiles."
            if status == "fail"
            else "Review low-confidence areas before relying on links and wiki sets."
            if status == "warn"
            else "No aggregate quality issues detected."
        ),
    }


def run_redacted_quality_judge(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not config.get("enable_quality_judge", True):
        return {"used": False, "status": "disabled", "findings": [], "recommendation": "Quality judge disabled."}
    judge_model = str(config.get("quality_judge_model") or config.get("review_model") or config.get("analysis_model") or "").strip()
    if not judge_model:
        return {"used": False, "status": "skipped", "findings": ["No quality judge model configured."], "recommendation": "Set WIKIMAKER_QUALITY_JUDGE_MODEL or WIKIMAKER_REVIEW_MODEL."}
    try:
        provider, base_url, api_key = _require_local_llm_config(config)
        prompt = (
            "You are WikiMaker's privacy-preserving quality judge. You receive only aggregate run metrics, "
            "never source text, filenames, titles, snippets, or personal data. Return strict JSON with keys "
            "status (healthy|warn|fail), findings (array of short strings), recommendation (short string). "
            "Flag weak LLM output when coverage, graph edges, schema validity, or verification confidence are poor.\n\n"
            f"AGGREGATE_METRICS_JSON:\n{json.dumps(metrics, indent=2, sort_keys=True)}"
        )
        text = _chat_completions(
            provider,
            base_url,
            api_key,
            judge_model,
            [
                {"role": "system", "content": "Judge only aggregate WikiMaker quality metrics. Do not ask for or infer private content."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        parsed = json.loads(text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("judge response was not a JSON object")
        return {
            "used": True,
            "status": str(parsed.get("status") or "warn"),
            "findings": [str(item) for item in parsed.get("findings", []) if str(item).strip()] if isinstance(parsed.get("findings"), list) else [],
            "recommendation": str(parsed.get("recommendation") or "").strip(),
        }
    except Exception as exc:
        fallback = deterministic_quality(metrics)
        return {
            "used": False,
            "status": fallback["status"],
            "findings": [*fallback["findings"], f"Quality judge failed: {exc}"],
            "recommendation": fallback["recommendation"],
        }


def build_quality_report(scan: dict[str, Any], pipeline: dict[str, Any], graph: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    metrics = build_quality_metrics(scan, pipeline, graph)
    deterministic = deterministic_quality(metrics)
    judge = run_redacted_quality_judge(metrics, config)
    status_order = {"healthy": 0, "warn": 1, "fail": 2}
    final_status = max([deterministic.get("status", "warn"), judge.get("status", "warn")], key=lambda item: status_order.get(str(item), 1))
    return {
        "status": final_status,
        "metrics": metrics,
        "deterministic": deterministic,
        "judge": judge,
        "privacy": {
            "source_text_shared": False,
            "filenames_shared": False,
            "titles_shared": False,
            "snippets_shared": False,
            "judge_input": "aggregate_counts_only",
        },
    }


def write_quality_report(output_root: Path, quality: dict[str, Any]) -> Path:
    lines = [
        "# WikiMaker LLM Quality",
        "",
        f"Status: `{quality.get('status', 'unknown')}`",
        "",
        "## Privacy boundary",
        "- Source text shared with judge: `False`",
        "- Filenames shared with judge: `False`",
        "- Titles shared with judge: `False`",
        "- Snippets shared with judge: `False`",
        "- Judge input: aggregate counts only",
        "",
        "## Aggregate metrics",
    ]
    for key, value in (quality.get("metrics") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Deterministic findings"])
    deterministic = quality.get("deterministic") or {}
    findings = deterministic.get("findings") or []
    if findings:
        lines.extend(f"- {item}" for item in findings)
    else:
        lines.append("- _None_")
    lines.append(f"- Recommendation: {deterministic.get('recommendation', '')}")
    lines.extend(["", "## Judge findings"])
    judge = quality.get("judge") or {}
    lines.append(f"- Used judge model: `{judge.get('used')}`")
    lines.append(f"- Judge status: `{judge.get('status', 'unknown')}`")
    judge_findings = judge.get("findings") or []
    if judge_findings:
        lines.extend(f"- {item}" for item in judge_findings)
    else:
        lines.append("- _None_")
    lines.append(f"- Recommendation: {judge.get('recommendation', '')}")
    path = output_root / "_llm_quality.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
