from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def build_wiki_health(scan: dict[str, Any], pipeline: dict[str, Any], graph: dict[str, Any] | None = None) -> dict[str, Any]:
    files = scan.get("files", {})
    generation = pipeline.get("generation", {})
    source_pages = [page for page in generation.get("source_pages", []) if isinstance(page, dict)]
    graph = graph or {}
    source_paths = {str(path) for path in files}
    represented = {str(page.get("path")) for page in source_pages if page.get("path")}
    missing_source_pages = sorted(source_paths - represented)

    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    source_nodes = [node for node in nodes if node.get("type") == "source"]
    orphan_pages = sorted(str(node.get("path")) for node in source_nodes if not node.get("backlinks") and not node.get("outlinks") and node.get("path"))
    underlinked_pages = sorted(str(node.get("path")) for node in source_nodes if int(node.get("backlinks", 0) or 0) + int(node.get("outlinks", 0) or 0) <= 1 and node.get("path"))

    missing_provenance: list[str] = []
    for rel_path, record in files.items():
        if not isinstance(record, dict):
            continue
        has_source_url = bool(str(record.get("source_url") or "").strip())
        has_source_links = bool(record.get("source_links"))
        if not has_source_url and not has_source_links:
            missing_provenance.append(str(rel_path))

    role_counts = Counter(str(page.get("page_role") or "knowledge_page") for page in source_pages)
    topicless_pages = sorted(str(page.get("path")) for page in source_pages if page.get("path") and not page.get("topics") and not page.get("entities"))
    findings: list[dict[str, Any]] = []
    if missing_source_pages:
        findings.append({"severity": "high", "message": f"{len(missing_source_pages)} source files are not represented by generated source pages.", "paths": missing_source_pages[:20]})
    if missing_provenance:
        findings.append({"severity": "medium", "message": f"{len(missing_provenance)} source files have no original/source links recorded.", "paths": missing_provenance[:20]})
    if orphan_pages:
        findings.append({"severity": "medium", "message": f"{len(orphan_pages)} generated pages are graph orphans.", "paths": orphan_pages[:20]})
    if topicless_pages:
        findings.append({"severity": "low", "message": f"{len(topicless_pages)} generated pages have no topics or entities.", "paths": topicless_pages[:20]})

    return {
        "counts": {
            "source_files": len(source_paths),
            "source_pages": len(source_pages),
            "missing_source_pages": len(missing_source_pages),
            "missing_provenance": len(missing_provenance),
            "orphan_pages": len(orphan_pages),
            "underlinked_pages": len(underlinked_pages),
            "topicless_pages": len(topicless_pages),
            "roles": dict(role_counts),
        },
        "missing_source_pages": missing_source_pages,
        "missing_provenance": missing_provenance,
        "orphan_pages": orphan_pages,
        "underlinked_pages": underlinked_pages,
        "topicless_pages": topicless_pages,
        "findings": findings,
        "status": "needs_attention" if findings else "healthy",
    }


def write_health_report(output_root: Path, health: dict[str, Any]) -> Path:
    lines = [
        "# WikiMaker Health Check",
        "",
        f"Status: `{health.get('status', 'unknown')}`",
        "",
        "## Counts",
    ]
    for key, value in (health.get("counts") or {}).items():
        if isinstance(value, dict):
            lines.append(f"- {key}: `{value}`")
        else:
            lines.append(f"- {key}: {value}")
    lines.extend(["", "## Findings"])
    findings = health.get("findings") or []
    if findings:
        for finding in findings:
            lines.append(f"- **{finding.get('severity', 'unknown')}**: {finding.get('message', '')}")
            for path in finding.get("paths", [])[:10]:
                lines.append(f"  - `{path}`")
    else:
        lines.append("- _None_")
    path = output_root / "_health.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
