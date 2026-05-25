from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import html
import json
import re
from typing import Any

from wikimaker_config import WikiMakerConfig
from wikimaker_state import hash_text


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


def _normalise_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or "item"


def _source_stub_name(rel_path: str) -> str:
    return "__".join(_safe_segment(part) for part in Path(rel_path).parts)


def _wiki_set_dir_name(name: str) -> str:
    return _safe_segment(name)


def _escape_md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")


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
    source_lookup: dict[str, str] = {}
    wiki_set_lookup: dict[str, str] = {}

    def add_edge(source: str, target: str, edge_type: str) -> None:
        if not source or not target:
            return
        edge = {"source": source, "target": target, "type": edge_type}
        if edge in graph_edges:
            return
        graph_edges.append(edge)
        outgoing[source] += 1
        incoming[target] += 1

    for page in source_pages:
        source_path = str(page.get('path') or '').strip()
        source_title = str(page.get('title') or '').strip()
        source_stem = Path(source_path).stem if source_path else ''
        source_id = f"source:{source_path}"
        for candidate in (source_path, source_title, source_stem):
            if candidate:
                source_lookup.setdefault(_normalise_lookup(candidate), source_id)

    for wiki_set in wiki_sets:
        set_name = str(wiki_set.get('name') or '').strip()
        if set_name:
            wiki_set_lookup.setdefault(_normalise_lookup(set_name), f"wiki-set:{set_name}")
    for page in source_pages:
        source_path = str(page.get('path') or '').strip()
        source_id = f"source:{source_path}"
        for rel in _clean_list(page.get("related_pages")):
            related_id = source_lookup.get(_normalise_lookup(rel))
            if related_id:
                add_edge(source_id, related_id, "related")
        for use in _clean_list(page.get("used_in")):
            set_id = wiki_set_lookup.get(_normalise_lookup(use)) or f"wiki-set:{use}"
            add_edge(source_id, set_id, "used_in")

    for wiki_set in wiki_sets:
        set_name = str(wiki_set.get('name') or '').strip()
        set_id = f"wiki-set:{set_name}"
        for title in _clean_list(wiki_set.get("pages")):
            page_id = source_lookup.get(_normalise_lookup(title))
            if page_id:
                add_edge(set_id, page_id, "contains")

    node_rows: list[dict[str, Any]] = []
    mtime_values = [int(record.get("mtime_ns", 0) or 0) for record in files.values() if isinstance(record, dict) and record.get("mtime_ns") is not None]
    min_mtime = min(mtime_values) if mtime_values else 0
    max_mtime = max(mtime_values) if mtime_values else 0
    span = max(max_mtime - min_mtime, 1)

    source_page_by_path = {str(page.get("path") or ""): page for page in source_pages if page.get("path")}
    source_page_by_id = {f"source:{path}": page for path, page in source_page_by_path.items()}
    source_related_counts = {f"source:{page.get('path')}": len(_clean_list(page.get("related_pages"))) for page in source_pages if page.get("path")}
    source_used_in_counts = {f"source:{page.get('path')}": len(_clean_list(page.get("used_in"))) for page in source_pages if page.get("path")}

    scored_source_rows: list[dict[str, Any]] = []
    for rel_path, record in sorted(files.items()):
        page = source_by_path.get(rel_path, {})
        source_id = f"source:{rel_path}"
        label = page.get("title") or record.get("title") or Path(rel_path).stem or rel_path
        backlinks = int(incoming.get(source_id, 0))
        outlinks = int(outgoing.get(source_id, 0))
        related_count = int(source_related_counts.get(source_id, 0))
        used_in_count = int(source_used_in_counts.get(source_id, 0))
        recency_score = 0.0
        if record.get("mtime_ns") is not None:
            recency_score = max(0.0, 1.0 - ((max_mtime - int(record.get("mtime_ns", 0) or 0)) / span))
        score = round((backlinks * 4.0) + (outlinks * 1.5) + (related_count * 2.5) + (used_in_count * 2.0) + (recency_score * 2.0), 3)
        scored_source_rows.append(
            {
                "id": source_id,
                "label": label,
                "type": "source",
                "path": rel_path,
                "status": _status_for_path(rel_path, diff),
                "source_kind": page.get("source_kind") or record.get("source_kind") or "",
                "platform": page.get("platform") or record.get("platform") or "",
                "backlinks": backlinks,
                "outlinks": outlinks,
                "related_count": related_count,
                "used_in_count": used_in_count,
                "score": score,
                "mtime_ns": record.get("mtime_ns", 0),
            }
        )

    scored_source_rows.sort(key=lambda item: (item.get("score", 0.0), item.get("backlinks", 0), item.get("outlinks", 0), item.get("label", "")), reverse=True)
    for rank, node in enumerate(scored_source_rows, start=1):
        node["rank"] = rank
        node_rows.append(node)

    for wiki_set in wiki_sets:
        set_name = str(wiki_set.get("name") or "").strip()
        if not set_name:
            continue
        set_id = f"wiki-set:{set_name}"
        pages = _clean_list(wiki_set.get("pages"))
        node_rows.append(
            {
                "id": set_id,
                "label": set_name,
                "type": "wiki_set",
                "purpose": wiki_set.get("purpose") or "",
                "page_count": len(pages),
                "backlinks": int(incoming.get(set_id, 0)),
                "outlinks": int(outgoing.get(set_id, 0)),
                "score": round((len(pages) * 2.0) + (int(incoming.get(set_id, 0)) * 2.0) + (int(outgoing.get(set_id, 0)) * 1.0), 3),
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
        "- [_Dashboard](_dashboard.md)",
        "- [_Stats](_stats.md)",
        "- [_Search index](_search.md)",
        "- [_Browser UI](browser/index.html)",
        "- [_Graph data](_graph.json)",


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
            label = _escape_md_cell(row['label'])
            dashboard_lines.append(
                f"| [{label}](sources/{safe_page_path}) | {row['backlinks']} | {row['outlinks']} | {row['status']} |"
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
            dashboard_lines.append(f"| {_escape_md_cell(row['label'])} | {row['status']} | `{row['path']}` |")
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
        title = _escape_md_cell(page.get("title") or record.get("title") or Path(rel_path).stem)
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
        pages = ", ".join(_escape_md_cell(item) for item in _clean_list(wiki_set.get("pages"))[:8]) or "_None_"
        search_lines.append(f"| {_escape_md_cell(wiki_set.get('name', ''))} | {_escape_md_cell(wiki_set.get('purpose', ''))} | {pages} |")

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
