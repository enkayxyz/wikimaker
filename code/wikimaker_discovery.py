from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from wikimaker_config import WikiMakerConfig


def _parse_timestamp(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _link_label(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().title() or name


def _safe_anchor(value: str) -> str:
    return value.replace("/", "_").replace(" ", "-")


def _status_for_path(rel_path: str, diff: dict[str, list[str]]) -> str:
    for label in ("added", "changed", "removed", "unchanged"):
        if rel_path in diff.get(label, []):
            return label
    return "new"


def _source_pages(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    generation = pipeline.get("generation", {})
    pages = generation.get("source_pages", [])
    return [page for page in pages if isinstance(page, dict)]


def _wiki_sets(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    generation = pipeline.get("generation", {})
    pages = generation.get("wiki_set_pages", [])
    return [page for page in pages if isinstance(page, dict)]


def build_discovery_views(scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> dict[str, Any]:
    files = scan.get("files", {})
    source_pages = _source_pages(pipeline)
    wiki_sets = _wiki_sets(pipeline)
    analysis = pipeline.get("analysis", {})
    generation = pipeline.get("generation", {})
    verification = pipeline.get("verification", {})

    source_by_path = {page.get("path"): page for page in source_pages if page.get("path")}
    wiki_set_names = {str(item.get("name") or "").strip() for item in wiki_sets if item.get("name")}
    incoming = Counter()
    outgoing = Counter()
    graph_edges: list[dict[str, Any]] = []

    def add_edge(source: str, target: str, edge_type: str) -> None:
        if not source or not target:
            return
        graph_edges.append({"source": source, "target": target, "type": edge_type})
        outgoing[source] += 1
        incoming[target] += 1

    for page in source_pages:
        source_id = f"source:{page.get('path')}"
        for rel in _clean_list(page.get("related_pages")):
            add_edge(source_id, f"source:{rel}", "related")
        for use in _clean_list(page.get("used_in")):
            add_edge(source_id, f"wiki-set:{use}", "used_in")

    for wiki_set in wiki_sets:
        set_id = f"wiki-set:{wiki_set.get('name')}"
        for title in _clean_list(wiki_set.get("pages")):
            for page in source_pages:
                if page.get("title") == title:
                    add_edge(set_id, f"source:{page.get('path')}", "contains")

    node_rows: list[dict[str, Any]] = []
    for rel_path, record in sorted(files.items()):
        page = source_by_path.get(rel_path, {})
        source_id = f"source:{rel_path}"
        label = page.get("title") or record.get("title") or Path(rel_path).stem
        node_rows.append(
            {
                "id": source_id,
                "label": label,
                "type": "source",
                "path": rel_path,
                "status": _status_for_path(rel_path, diff),
                "source_kind": page.get("source_kind") or record.get("source_kind") or "",
                "platform": page.get("platform") or record.get("platform") or "",
                "backlinks": int(incoming.get(source_id, 0)),
                "outlinks": int(outgoing.get(source_id, 0)),
                "mtime_ns": record.get("mtime_ns", 0),
            }
        )

    for wiki_set in wiki_sets:
        set_name = str(wiki_set.get("name") or "").strip()
        if not set_name:
            continue
        set_id = f"wiki-set:{set_name}"
        node_rows.append(
            {
                "id": set_id,
                "label": set_name,
                "type": "wiki_set",
                "purpose": wiki_set.get("purpose") or "",
                "backlinks": int(incoming.get(set_id, 0)),
                "outlinks": int(outgoing.get(set_id, 0)),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis": analysis,
        "generation": generation,
        "verification": verification,
        "source_pages": source_pages,
        "wiki_sets": wiki_sets,
        "graph": {
            "nodes": node_rows,
            "edges": graph_edges,
        },
    }


def write_discovery_views(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> dict[str, Path]:
    discovery = build_discovery_views(scan, diff, pipeline)
    output_root = config.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    source_pages = discovery["source_pages"]
    wiki_sets = discovery["wiki_sets"]
    files = scan.get("files", {})
    graph = discovery["graph"]

    by_path = {page.get("path"): page for page in source_pages if page.get("path")}
    by_title = {page.get("title"): page for page in source_pages if page.get("title")}

    all_source_paths = sorted(files)
    connected_rows = sorted(
        [node for node in graph["nodes"] if node.get("type") == "source"],
        key=lambda item: (item.get("backlinks", 0), item.get("outlinks", 0), item.get("label", "")),
        reverse=True,
    )
    recent_rows = sorted(
        [node for node in graph["nodes"] if node.get("type") == "source"],
        key=lambda item: (item.get("mtime_ns", 0), item.get("label", "")),
        reverse=True,
    )

    corpus_kinds = _clean_list(discovery["analysis"].get("corpus_kinds"))
    topic_clusters = _clean_list(discovery["analysis"].get("topic_clusters"))
    entity_clusters = _clean_list(discovery["analysis"].get("entity_clusters"))
    duplicate_clusters = _clean_list(discovery["analysis"].get("duplicate_clusters"))
    contradiction_clusters = _clean_list(discovery["analysis"].get("contradiction_clusters"))
    reorg_suggestions = _clean_list(discovery["analysis"].get("reorg_suggestions"))

    dashboard_lines = [
        "# WikiMaker Dashboard",
        "",
        discovery["generation"].get("dashboard_summary") or discovery["analysis"].get("corpus_summary") or "Corpus discovery overview.",
        "",
        "## Snapshot",
        f"- Files scanned: {len(files)}",
        f"- Source pages: {len(source_pages)}",
        f"- Wiki sets: {len(wiki_sets)}",
        f"- Corpus kinds: {len(corpus_kinds)}",
        f"- Topics: {len(topic_clusters)}",
        f"- Entities: {len(entity_clusters)}",
        f"- Duplicate clusters: {len(duplicate_clusters)}",
        f"- Contradiction clusters: {len(contradiction_clusters)}",
        "",
        "## Navigation",
        "- [_Root index](_root_index.md)",
        "- [_Stats](_stats.md)",
        "- [_Search index](_search.md)",
        "- [_Graph data](_graph.json)",
        "",
        "## Corpus kinds",
    ]
    if corpus_kinds:
        dashboard_lines.extend(f"- {item}" for item in corpus_kinds)
    else:
        dashboard_lines.append("- _Unknown_")
    dashboard_lines.extend([
        "",
        "## Most connected source pages",
    ])
    if connected_rows:
        dashboard_lines.append("| Page | Backlinks | Outlinks | Status |")
        dashboard_lines.append("| --- | --- | --- | --- |")
        for row in connected_rows[:12]:
            safe_page_path = row['path'].replace('/', '__')
            dashboard_lines.append(
                f"| [{row['label']}](sources/{safe_page_path}) | {row['backlinks']} | {row['outlinks']} | {row['status']} |"
            )
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Recent additions / updates",
    ])
    if recent_rows:
        dashboard_lines.append("| Page | Status | Path |")
        dashboard_lines.append("| --- | --- | --- |")
        for row in recent_rows[:12]:
            dashboard_lines.append(f"| {row['label']} | {row['status']} | `{row['path']}` |")
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Topics",
    ])
    if topic_clusters:
        dashboard_lines.extend(f"- {item}" for item in topic_clusters)
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Entities",
    ])
    if entity_clusters:
        dashboard_lines.extend(f"- {item}" for item in entity_clusters)
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Duplicate clusters",
    ])
    if duplicate_clusters:
        dashboard_lines.extend(f"- {item}" for item in duplicate_clusters)
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Contradiction clusters",
    ])
    if contradiction_clusters:
        dashboard_lines.extend(f"- {item}" for item in contradiction_clusters)
    else:
        dashboard_lines.append("- _None_")

    dashboard_lines.extend([
        "",
        "## Reorganization suggestions",
    ])
    if reorg_suggestions:
        dashboard_lines.extend(f"- {item}" for item in reorg_suggestions)
    else:
        dashboard_lines.append("- _None_")

    stats_lines = [
        "# WikiMaker Stats",
        "",
        discovery["generation"].get("stats_summary") or "Corpus statistics and health view.",
        "",
        "## Counts",
        f"- Files scanned: {len(files)}",
        f"- Source pages: {len(source_pages)}",
        f"- Wiki sets: {len(wiki_sets)}",
        f"- Graph nodes: {len(graph['nodes'])}",
        f"- Graph edges: {len(graph['edges'])}",
        f"- Distinct source kinds: {len(corpus_kinds)}",
        f"- Distinct topics: {len(topic_clusters)}",
        f"- Distinct entities: {len(entity_clusters)}",
        "",
        "## Verification",
        f"- Approved: `{discovery['verification'].get('approved')}`",
        f"- Confidence: `{discovery['verification'].get('confidence')}`",
        "",
        "## Corpus kinds",
    ]
    if corpus_kinds:
        stats_lines.extend(f"- {item}" for item in corpus_kinds)
    else:
        stats_lines.append("- _Unknown_")
    stats_lines.extend([
        "",
        "## Growth hot spots",
        f"- Most connected page: {connected_rows[0]['label']} ({connected_rows[0]['backlinks']} backlinks)" if connected_rows else "- _None_",
        f"- Most recent page: {recent_rows[0]['label']}" if recent_rows else "- _None_",
    ])

    search_lines = [
        "# WikiMaker Search Index",
        "",
        "Use this page as a simple jump table until a richer search UI exists.",
        "",
        "## Source pages",
        "| Title | Path | Status | Links |",
        "| --- | --- | --- | --- |",
    ]
    for rel_path in all_source_paths:
        record = files[rel_path]
        page = by_path.get(rel_path, {})
        title = page.get("title") or record.get("title") or Path(rel_path).stem
        status = _status_for_path(rel_path, diff)
        link_count = len(_clean_list(page.get("related_pages"))) + len(_clean_list(page.get("used_in")))
        search_lines.append(f"| {title} | `{rel_path}` | {status} | {link_count} |")
    search_lines.extend([
        "",
        "## Wiki sets",
        "| Name | Purpose | Pages |",
        "| --- | --- | --- |",
    ])
    for wiki_set in wiki_sets:
        pages = ", ".join(_clean_list(wiki_set.get("pages"))[:8]) or "_None_"
        search_lines.append(f"| {wiki_set.get('name', '')} | {wiki_set.get('purpose', '')} | {pages} |")

    dashboard_path = output_root / "_dashboard.md"
    stats_path = output_root / "_stats.md"
    search_path = output_root / "_search.md"
    graph_path = output_root / "_graph.json"

    dashboard_path.write_text("\n".join(dashboard_lines) + "\n", encoding="utf-8")
    stats_path.write_text("\n".join(stats_lines) + "\n", encoding="utf-8")
    search_path.write_text("\n".join(search_lines) + "\n", encoding="utf-8")
    graph_path.write_text(json.dumps(discovery["graph"], indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "dashboard": dashboard_path,
        "stats": stats_path,
        "search": search_path,
        "graph": graph_path,
    }
