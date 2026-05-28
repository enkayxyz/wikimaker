from __future__ import annotations

from html import escape
from pathlib import Path
import json
import re
from typing import Any

from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import build_discovery_views, _source_stub_name, _wiki_set_dir_name
from wikimaker_privacy import browser_network_posture, classify_endpoint_privacy


def _browser_payload(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> dict[str, Any]:
    discovery = build_discovery_views(scan, diff, pipeline)
    graph = discovery.get("graph", {})
    files = scan.get("files", {})
    semantic_pages: list[dict[str, Any]] = []
    navigation_pages: list[dict[str, Any]] = []
    source_by_path = {page.get("path"): page for page in discovery.get("source_pages", []) if page.get("path")}
    source_node_by_path = {
        node.get("path"): node
        for node in graph.get("nodes", [])
        if node.get("type") == "source" and node.get("path")
    }
    source_lookup: dict[str, str] = {}

    def _normalise_lookup(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    for rel_path, page in source_by_path.items():
        title = str(page.get("title") or Path(str(rel_path)).stem or rel_path).strip()
        for candidate in (rel_path, title, Path(str(rel_path)).stem):
            key = _normalise_lookup(candidate)
            if key:
                source_lookup.setdefault(key, str(rel_path))

    links_to_by_path: dict[str, list[str]] = {rel_path: [] for rel_path in source_by_path}
    linked_from_by_path: dict[str, list[str]] = {rel_path: [] for rel_path in source_by_path}
    for rel_path, page in source_by_path.items():
        source_title = str(page.get("title") or Path(str(rel_path)).stem or rel_path).strip()
        for rel in page.get("related_pages", []) or []:
            target_path = source_lookup.get(_normalise_lookup(str(rel)))
            if target_path and target_path in source_by_path:
                target_page = source_by_path[target_path]
                target_title = str(target_page.get("title") or Path(str(target_path)).stem or target_path).strip()
                if target_title not in links_to_by_path[rel_path]:
                    links_to_by_path[rel_path].append(target_title)
                if source_title not in linked_from_by_path[target_path]:
                    linked_from_by_path[target_path].append(source_title)

    for page in discovery.get("source_pages", []):
        rel_path = str(page.get("path") or "")
        node = source_node_by_path.get(rel_path, {})
        page_role = str(page.get("page_role") or node.get("page_role") or "knowledge_page").strip().lower()
        page_payload = {
            **page,
            "source_stub": _source_stub_name(rel_path) if rel_path else "",
            "source_page_href": f"../sources/{_source_stub_name(rel_path)}" if rel_path else "",
            "rank": node.get("rank", 0),
            "score": node.get("score", 0),
            "backlinks": node.get("backlinks", 0),
            "outlinks": node.get("outlinks", 0),
            "related_count": node.get("related_count", 0),
            "used_in_count": node.get("used_in_count", 0),
            "status": node.get("status", "new"),
            "links_to": links_to_by_path.get(rel_path, list(page.get("related_pages", []) or [])),
            "linked_from": linked_from_by_path.get(rel_path, []),
        }
        if page_role in {"index_page", "ledger_page", "duplicate_page", "contradiction_page"}:
            navigation_pages.append(page_payload)
        else:
            semantic_pages.append(page_payload)

    source_nodes = [node for node in graph.get("nodes", []) if node.get("type") == "source" and node.get("path")]
    source_nodes.sort(
        key=lambda item: (
            0 if str(item.get("page_role") or "") in {"knowledge_page", "thread_page"} else 1,
            item.get("score", 0),
            item.get("backlinks", 0),
            item.get("outlinks", 0),
            item.get("mtime_ns", 0),
            item.get("label", ""),
        ),
        reverse=True,
    )

    library_pages: list[dict[str, Any]] = []
    for node in source_nodes:
        rel_path = str(node.get("path") or "")
        record = files.get(rel_path, {}) if isinstance(files, dict) else {}
        semantic = source_by_path.get(rel_path, {})
        title = str(semantic.get("title") or record.get("title") or node.get("label") or Path(rel_path).stem or rel_path).strip()
        summary = str(
            semantic.get("summary")
            or record.get("title")
            or (record.get("headings") or [""])[0]
            or "No summary available."
        ).strip()
        library_pages.append(
            {
                "path": rel_path,
                "title": title,
                "summary": summary,
                "source_url": str(semantic.get("source_url") or record.get("source_url") or "").strip(),
                "source_kind": str(semantic.get("source_kind") or record.get("source_kind") or "").strip(),
                "platform": str(semantic.get("platform") or record.get("platform") or "").strip(),
                "extracted_at": str(semantic.get("extracted_at") or record.get("extracted_at") or "").strip(),
                "page_role": str(semantic.get("page_role") or node.get("page_role") or "").strip(),
                "source_stub": _source_stub_name(rel_path),
                "source_page_href": f"../sources/{_source_stub_name(rel_path)}",
                "tags": semantic.get("tags", []),
                "topics": semantic.get("topics", []),
                "entities": semantic.get("entities", []),
                "related_pages": semantic.get("related_pages", []),
                "links_to": links_to_by_path.get(rel_path, list(semantic.get("related_pages", []) or [])),
                "linked_from": linked_from_by_path.get(rel_path, []),
                "used_in": semantic.get("used_in", []),
                "key_snippets": semantic.get("key_snippets", []),
                "breadcrumbs": semantic.get("breadcrumbs", []),
                "rank": node.get("rank", 0),
                "score": node.get("score", 0),
                "backlinks": node.get("backlinks", 0),
                "outlinks": node.get("outlinks", 0),
                "related_count": node.get("related_count", 0),
                "used_in_count": node.get("used_in_count", 0),
                "status": node.get("status", "new"),
                "mtime_ns": node.get("mtime_ns", 0),
            }
        )

    wiki_sets = []
    for wiki_set in discovery.get("wiki_sets", []):
        name = str(wiki_set.get("name") or "").strip()
        if not name:
            continue
        wiki_sets.append(
            {
                **wiki_set,
                "dir_name": _wiki_set_dir_name(name),
                "index_href": f"../wiki-sets/{_wiki_set_dir_name(name)}/_index.md",
            }
        )

    semantic_pages.sort(key=lambda item: (item.get("score", 0), item.get("backlinks", 0), item.get("outlinks", 0), item.get("title", "")), reverse=True)
    library_pages.sort(key=lambda item: (item.get("score", 0), item.get("backlinks", 0), item.get("outlinks", 0), item.get("mtime_ns", 0), item.get("title", "")), reverse=True)
    wiki_sets.sort(key=lambda item: (len(item.get("pages", [])), item.get("name", "")), reverse=True)

    analysis = discovery.get("analysis", {})
    generation = discovery.get("generation", {})
    external_links = sum(len(record.get("source_links") or []) for record in files.values() if isinstance(record, dict))
    topic_facets = sorted({str(item).strip() for page in discovery.get("source_pages", []) for item in (page.get("topics") or []) if str(item).strip()})
    entity_facets = sorted({str(item).strip() for page in discovery.get("source_pages", []) for item in (page.get("entities") or []) if str(item).strip()})
    people_facets = [
        entity
        for entity in entity_facets
        if 1 < len(entity.split()) <= 4 and any(ch.isupper() for ch in entity)
    ][:24]
    return {
        "generated_at": discovery.get("generated_at"),
        "analysis": analysis,
        "generation": generation,
        "verification": discovery.get("verification", {}),
        "privacy": {
            "model_endpoint": classify_endpoint_privacy(config.openai_base_url),
            "browser": browser_network_posture(has_active_fetches=False, external_links=external_links),
            "allow_remote_llm": config.allow_remote_llm,
            "prompt_profiles": scan.get("prompt_profiles", {}),
        },
        "facets": {
            "topics": topic_facets,
            "entities": entity_facets,
            "people": people_facets,
        },
        "counts": {
            "files": len(files),
            "semantic_source_pages": len(semantic_pages),
            "navigation_source_pages": len(navigation_pages),
            "library_pages": len(library_pages),
            "wiki_sets": len(wiki_sets),
            "topics": len(analysis.get("topic_clusters", []) or []),
            "entities": len(analysis.get("entity_clusters", []) or []),
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
        },
        "diff": diff,
        "sources": semantic_pages,
        "navigation_sources": navigation_pages,
        "library_pages": library_pages,
        "wiki_sets": wiki_sets,
        "graph": graph,
        "paths": {
            "root_index": "../_root_index.md",
            "dashboard": "../_dashboard.md",
            "stats": "../_stats.md",
            "search": "../_search.md",
            "graph": "../_graph.json",
            "privacy": "../_privacy.md",
            "health": "../_health.md",
            "llm_quality": "../_llm_quality.md",
            "browser_data": "data.json",
        },
    }


def _render_browser_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    generated_at = escape(str(payload.get("generated_at") or ""))
    semantic_sources_count = payload.get("counts", {}).get("semantic_source_pages", 0)
    navigation_sources_count = payload.get("counts", {}).get("navigation_source_pages", 0)
    library_pages_count = payload.get("counts", {}).get("library_pages", 0)
    wiki_sets_count = payload.get("counts", {}).get("wiki_sets", 0)
    topics_count = payload.get("counts", {}).get("topics", 0)
    entities_count = payload.get("counts", {}).get("entities", 0)
    nodes_count = payload.get("counts", {}).get("nodes", 0)
    edges_count = payload.get("counts", {}).get("edges", 0)
    corpus_summary = escape(str(payload.get("analysis", {}).get("corpus_summary") or payload.get("generation", {}).get("dashboard_summary") or ""))
    approved = payload.get("verification", {}).get("approved")
    confidence = payload.get("verification", {}).get("confidence")
    endpoint_privacy = payload.get("privacy", {}).get("model_endpoint", {})
    endpoint_classification = escape(str(endpoint_privacy.get("classification") or "unknown"))
    endpoint_risk = escape(str(endpoint_privacy.get("risk") or "unknown"))
    endpoint_scope = escape(str(endpoint_privacy.get("network_scope") or "unknown"))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>WikiMaker Browser</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f3;
      --panel: #ffffff;
      --surface: #f0f3ef;
      --line: #d9dfd7;
      --text: #202626;
      --muted: #66706c;
      --accent: #116b6f;
      --accent-2: #8a4b2d;
      --good: #207a4b;
      --warn: #9b650f;
      --bad: #b4233c;
      --shadow: 0 6px 18px rgba(32, 38, 38, 0.08);
      --pill-bg: #edf3f1;
      --pill-line: #d5dfdc;
    }}
    [data-theme="dark"] {{
      color-scheme: dark;
      --bg: #171918;
      --panel: #202321;
      --surface: #272b28;
      --line: #3b413d;
      --text: #edf2ee;
      --muted: #a3ada7;
      --accent: #6fc2bd;
      --accent-2: #e0a36e;
      --good: #82d29d;
      --warn: #e7bc5a;
      --bad: #ef7f91;
      --shadow: 0 6px 18px rgba(0, 0, 0, 0.24);
      --pill-bg: #26312f;
      --pill-line: #374641;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ max-width: 1500px; margin: 0 auto; padding: 18px 24px 24px; }}
    .hero {{
      display: grid;
      gap: 16px;
      grid-template-columns: minmax(0, 1fr) minmax(360px, 0.7fr);
      align-items: start;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .hero-main {{ padding: 0; }}
    .kicker {{ text-transform: uppercase; letter-spacing: .08em; color: var(--muted); font-size: 12px; margin-bottom: 10px; }}
    h1 {{ margin: 0 0 8px; font-size: 1.55rem; line-height: 1.2; }}
    .lead {{ color: var(--muted); font-size: 0.98rem; line-height: 1.45; max-width: 86ch; }}
    .meta {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 7px 10px; border-radius: 8px;
      background: var(--pill-bg); border: 1px solid var(--pill-line);
      color: var(--text); font-size: 13px;
    }}
    .pill strong {{ color: var(--text); }}
    .hero-side {{ padding: 0; display: grid; gap: 10px; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .stat {{ padding: 16px; border-radius: 8px; background: var(--surface); border: 1px solid var(--line); }}
    .stat .num {{ font-size: 1.8rem; font-weight: 700; }}
    .stat .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
    .toolbar {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; margin: 14px 0 16px; align-items: start; }}
    .searchbox {{
      width: 100%; padding: 14px 16px; border-radius: 8px; border: 1px solid var(--line);
      background: var(--surface); color: var(--text); font-size: 1rem;
    }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; align-items: center; }}
    .nav a {{
      display: inline-flex; align-items: center; padding: 10px 12px; border-radius: 8px;
      background: var(--surface); border: 1px solid var(--line);
      color: var(--text);
    }}
    .theme-toggle {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 12px; border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      cursor: pointer;
      font: inherit;
    }}
    .layout {{ display: grid; grid-template-columns: 1.5fr 0.9fr; gap: 18px; align-items: start; }}
    .section {{ padding: 18px; }}
    .section h2 {{ margin: 0 0 12px; font-size: 1.15rem; }}
    .subtle {{ color: var(--muted); font-size: 0.95rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
    .compact-list {{ display: grid; gap: 10px; }}
    .compact-item {{
      display: grid; gap: 6px;
      padding: 12px 14px; border-radius: 8px;
      background: var(--surface);
      border: 1px solid var(--line);
      cursor: pointer;
    }}
    .compact-item .title {{ font-weight: 650; }}
    .compact-item .body {{ color: var(--muted); font-size: 0.92rem; line-height: 1.45; }}
    .item {{
      padding: 14px; border-radius: 8px; background: var(--surface);
      border: 1px solid var(--line); cursor: pointer;
      transition: transform .15s ease, border-color .15s ease, background .15s ease;
    }}
    .item:hover {{ transform: translateY(-1px); border-color: var(--accent); background: var(--panel); }}
    .item .title {{ font-weight: 700; margin-bottom: 6px; }}
    .item .body {{ color: var(--muted); font-size: 0.95rem; line-height: 1.45; }}
    .tagrow {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }}
    .tag {{ font-size: 12px; padding: 5px 8px; border-radius: 8px; background: var(--pill-bg); color: var(--accent); border: 1px solid var(--pill-line); }}
    .status {{ font-size: 12px; padding: 4px 8px; border-radius: 8px; border: 1px solid var(--line); }}
    .status.added {{ color: var(--good); }}
    .status.changed {{ color: var(--warn); }}
    .status.removed {{ color: var(--bad); }}
    .panel {{ padding: 18px; position: sticky; top: 18px; }}
    .detail h2 {{ margin-top: 0; }}
    .kv {{ display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; font-size: 0.95rem; margin: 12px 0 16px; }}
    .kv div {{ color: var(--muted); }}
    .kv strong {{ color: var(--text); font-weight: 600; text-align: right; }}
    .detail-section {{ margin-top: 16px; }}
    .detail-section h3 {{ margin: 0 0 8px; font-size: 0.98rem; }}
    .list {{ display: grid; gap: 8px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 0.9rem; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; font-size: 0.9rem; }}
    .footer {{ margin: 18px 0 6px; color: var(--muted); font-size: 0.9rem; }}
    @media (max-width: 1100px) {{
      .hero, .layout, .toolbar {{ grid-template-columns: 1fr; }}
      .panel {{ position: static; }}
      .nav {{ justify-content: flex-start; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div class="hero-main">
        <div class="kicker">WikiMaker local wiki</div>
        <h1>WikiMaker</h1>
        <div class="lead">
          Browse generated wiki pages, source summaries, backlinks, graph edges, and provenance from one static local HTML file.
        </div>
        <div class="lead" style="margin-top:12px;">
          {corpus_summary or 'Local, static, provenance-first browsing.'}
        </div>
        <div class="meta">
          <span class="pill"><strong>Generated</strong> {generated_at}</span>
          <span class="pill"><strong>Wiki pages</strong> {semantic_sources_count}</span>
          <span class="pill"><strong>Library pages</strong> {library_pages_count}</span>
          <span class="pill"><strong>Wiki sets</strong> {wiki_sets_count}</span>
          <span class="pill"><strong>Topics</strong> {topics_count}</span>
          <span class="pill"><strong>Entities</strong> {entities_count}</span>
          <span class="pill"><strong>Verified</strong> {approved}</span>
          <span class="pill"><strong>Confidence</strong> {confidence}</span>
          <span class="pill"><strong>Model</strong> {endpoint_classification} / {endpoint_risk}</span>
        </div>
      </div>
      <div class="hero-side">
        <div class="stat-grid">
          <div class="stat"><div class="num" id="countSemantic">{semantic_sources_count}</div><div class="label">wiki pages</div></div>
          <div class="stat"><div class="num" id="countLibrary">{library_pages_count}</div><div class="label">library pages</div></div>
          <div class="stat"><div class="num" id="countSets">{wiki_sets_count}</div><div class="label">wiki sets</div></div>
          <div class="stat"><div class="num" id="countEdges">{edges_count}</div><div class="label">graph edges</div></div>
        </div>
        <div class="subtle">No outbound fetches. No remote fonts. Static, local-first browsing only. Model scope: {endpoint_scope}.</div>
      </div>
    </div>

    <div class="toolbar">
      <input class="searchbox" id="search" placeholder="Filter by title, topic, entity, tag, path, or wiki set…" />
      <div class="nav">
        <button class="theme-toggle" id="themeToggle" type="button">Toggle theme</button>
        <a href="../_root_index.md">Root index</a>
        <a href="../_dashboard.md">Dashboard</a>
        <a href="../_stats.md">Stats</a>
        <a href="../_search.md">Search</a>
        <a href="../_graph.json">Graph JSON</a>
        <a href="../_privacy.md">Privacy</a>
        <a href="../_llm_quality.md">LLM quality</a>
        <a href="../_health.md">Health</a>
      </div>
    </div>

    <div class="layout">
      <div class="stack">
        <section class="card section">
          <h2>Most connected pages</h2>
          <div class="subtle">Pages with the strongest graph signal and link density.</div>
          <div class="compact-list" id="connectedList"></div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Topics and entities</h2>
          <div class="subtle">Click a chip to filter the wiki by topic, person, or entity.</div>
          <div class="detail-section">
            <h3>People</h3>
            <div class="tagrow" id="peopleFacetRow"></div>
          </div>
          <div class="detail-section">
            <h3>Topics</h3>
            <div class="tagrow" id="topicFacetRow"></div>
          </div>
          <div class="detail-section">
            <h3>Entities</h3>
            <div class="tagrow" id="entityFacetRow"></div>
          </div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Recently changed</h2>
          <div class="subtle">The most recent source pages in the corpus.</div>
          <div class="compact-list" id="recentList"></div>
        </section>

        <section class="card section">
          <h2>Semantic source pages</h2>
          <div class="subtle">The generated wiki pages with summaries, topics, and cross-links.</div>
          <div class="grid" id="sourceGrid"></div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Source library</h2>
          <div class="subtle">Every scanned Markdown file, ranked by graph signal and recency. Filter to browse the corpus. Showing up to 200 cards at a time.</div>
          <div class="grid" id="libraryGrid"></div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Wiki sets</h2>
          <div class="subtle">Clusters and cross-corpus buckets generated by WikiMaker.</div>
          <div class="grid" id="wikiSetGrid"></div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Top graph edges</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Source</th><th>Type</th><th>Target</th></tr></thead>
              <tbody id="edgeTable"></tbody>
            </table>
          </div>
        </section>

        <section class="card section" style="margin-top:18px;">
          <h2>Settings / Privacy</h2>
          <div class="kv">
            <div>Model endpoint</div><strong id="privacyEndpoint"></strong>
            <div>Network scope</div><strong id="privacyScope"></strong>
            <div>Risk</div><strong id="privacyRisk"></strong>
            <div>Browser fetches</div><strong id="privacyFetches"></strong>
            <div>Prompt profiles</div><strong id="privacyProfiles"></strong>
          </div>
          <div class="subtle">Models are user-selectable, but endpoint classification shows when corpus prompts may leave this machine or LAN.</div>
        </section>
      </div>

      <aside class="card panel detail" id="detailPanel">
        <h2>Selection detail</h2>
        <div class="subtle">Click a card to inspect provenance, scores, and related items.</div>
        <div class="kv" id="detailKv">
          <div>Tip</div><strong>Choose a source page or wiki set</strong>
        </div>
        <div id="detailBody"></div>
      </aside>
    </div>

    <div class="footer">WikiMaker browser view — local, static, and provenance-first.</div>
  </div>

  <script id="wikimaker-data" type="application/json">{data_json}</script>
  <script>
    const data = JSON.parse(document.getElementById('wikimaker-data').textContent);
    const sourceGrid = document.getElementById('sourceGrid');
    const libraryGrid = document.getElementById('libraryGrid');
    const wikiSetGrid = document.getElementById('wikiSetGrid');
    const edgeTable = document.getElementById('edgeTable');
    const connectedList = document.getElementById('connectedList');
    const recentList = document.getElementById('recentList');
    const peopleFacetRow = document.getElementById('peopleFacetRow');
    const topicFacetRow = document.getElementById('topicFacetRow');
    const entityFacetRow = document.getElementById('entityFacetRow');
    const detailKv = document.getElementById('detailKv');
    const detailBody = document.getElementById('detailBody');
    const search = document.getElementById('search');
    const themeToggle = document.getElementById('themeToggle');
    const themeStorageKey = 'wikimaker-theme';
    const sourcePageByPath = Object.fromEntries((data.sources || []).map(page => [page.path, page]));

    function esc(value) {{
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }}

    function tagList(items) {{
      if (!items || !items.length) return '<span class="subtle">None</span>';
      return items.map(item => `<span class="tag">${{esc(item)}}</span>`).join('');
    }}

    function renderFacetRow(container, items) {{
      if (!items || !items.length) {{
        container.innerHTML = '<span class="subtle">None detected</span>';
        return;
      }}
      container.innerHTML = items.slice(0, 36).map(item => `<button class="theme-toggle facet-button" type="button" data-filter="${{esc(item)}}">${{esc(item)}}</button>`).join('');
      for (const button of container.querySelectorAll('.facet-button')) {{
        button.addEventListener('click', () => {{
          search.value = button.dataset.filter || '';
          renderAll(search.value);
        }});
      }}
    }}

    function applyTheme(theme) {{
      const resolved = theme === 'light' ? 'light' : 'dark';
      document.body.dataset.theme = resolved;
      themeToggle.textContent = resolved === 'light' ? 'Dark mode' : 'Light mode';
      themeToggle.setAttribute('aria-pressed', resolved === 'light' ? 'true' : 'false');
    }}

    const preferredTheme = (() => {{
      const stored = window.localStorage.getItem(themeStorageKey);
      if (stored === 'light' || stored === 'dark') return stored;
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }})();
    applyTheme(preferredTheme);
    themeToggle.addEventListener('click', () => {{
      const next = document.body.dataset.theme === 'light' ? 'dark' : 'light';
      window.localStorage.setItem(themeStorageKey, next);
      applyTheme(next);
    }});

    function snippetList(items) {{
      if (!items || !items.length) return '<div class="subtle">None</div>';
      return `<div class="list">${{items.map(item => `<div class="item" style="cursor:default">${{esc(item)}}</div>`).join('')}}</div>`;
    }}

    function cardText(page) {{
      return [page.title, page.summary, page.path, page.source_url, page.source_kind, page.platform, page.extracted_at, ...(page.tags || []), ...(page.topics || []), ...(page.entities || []), ...(page.related_pages || []), ...(page.used_in || []), ...(page.breadcrumbs || [])].join(' ').toLowerCase();
    }}

    function nodeText(node) {{
      return [node.label, node.path, node.source_kind, node.platform, node.status, node.score, node.backlinks, node.outlinks].join(' ').toLowerCase();
    }}

    function renderCompactList(container, rows, emptyText, kind) {{
      container.innerHTML = '';
      for (const row of rows) {{
        const div = document.createElement('div');
        div.className = 'compact-item';
        div.dataset.kind = kind;
        div.dataset.text = kind === 'node' ? nodeText(row) : cardText(row);
        div.innerHTML = kind === 'node'
          ? `
            <div class="title">${{esc(row.label || row.title || row.path)}}</div>
            <div class="body">${{esc(row.path || '')}}</div>
            <div class="tagrow">${{tagList([row.status ? `Status: ${{row.status}}` : '', `Backlinks: ${{row.backlinks ?? 0}}`, `Outlinks: ${{row.outlinks ?? 0}}`, row.source_kind ? `Kind: ${{row.source_kind}}` : ''].filter(Boolean))}}</div>
          `
          : `
            <div class="title">${{esc(row.title || row.path)}}</div>
            <div class="body">${{esc(row.summary || 'No summary available.')}}</div>
            <div class="tagrow">${{tagList([row.source_kind ? `Kind: ${{row.source_kind}}` : '', row.platform ? `Platform: ${{row.platform}}` : '', row.status ? `Status: ${{row.status}}` : ''].filter(Boolean))}}</div>
          `;
        div.addEventListener('click', () => {{
          const target = kind === 'node' ? (sourcePageByPath[row.path] || row) : row;
          showSource(target);
        }});
        container.appendChild(div);
      }}
      if (!rows.length) {{
        container.innerHTML = `<div class="subtle">${{esc(emptyText)}}</div>`;
      }}
    }}

    function connectedRows(filterText = '') {{
      const needle = filterText.trim().toLowerCase();
      return (data.graph.nodes || [])
        .filter(node => node.type === 'source')
        .filter(node => !needle || nodeText(node).includes(needle))
        .slice(0, 10);
    }}

    function recentRows(filterText = '') {{
      const needle = filterText.trim().toLowerCase();
      return (data.graph.nodes || [])
        .filter(node => node.type === 'source')
        .filter(node => !needle || nodeText(node).includes(needle))
        .slice()
        .sort((a, b) => (b.mtime_ns || 0) - (a.mtime_ns || 0))
        .slice(0, 10);
    }}

    function renderSourceCards(filterText = '') {{
      const needle = filterText.trim().toLowerCase();
      sourceGrid.innerHTML = '';
      const rows = data.sources.filter(page => !needle || cardText(page).includes(needle));
      for (const page of rows) {{
        const div = document.createElement('div');
        div.className = 'item';
        div.dataset.kind = 'source';
        div.dataset.text = cardText(page);
        div.innerHTML = `
          <div class="title">${{esc(page.title || page.path)}}</div>
          <div class="body">${{esc(page.summary || 'No summary available.')}}</div>
          <div class="tagrow">${{tagList([`Rank #${{page.rank || '?'}}`, `Score ${{page.score ?? 0}}`, page.status ? `Status: ${{page.status}}` : '', page.source_kind ? `Kind: ${{page.source_kind}}` : '', page.platform ? `Platform: ${{page.platform}}` : ''])}}</div>
          <div class="tagrow">${{tagList((page.topics || []).slice(0, 4))}}</div>
          <div class="tagrow">${{tagList((page.entities || []).slice(0, 4))}}</div>
        `;
        div.addEventListener('click', () => showSource(page));
        sourceGrid.appendChild(div);
      }}
      if (!rows.length) {{
        sourceGrid.innerHTML = '<div class="subtle">No source pages match your filter.</div>';
      }}
    }}

    function renderLibraryCards(filterText = '') {{
      const needle = filterText.trim().toLowerCase();
      libraryGrid.innerHTML = '';
      const rows = data.library_pages.filter(page => !needle || cardText(page).includes(needle)).slice(0, 200);
      for (const page of rows) {{
        const div = document.createElement('div');
        div.className = 'item';
        div.dataset.kind = 'library';
        div.dataset.text = cardText(page);
        div.innerHTML = `
          <div class="title">${{esc(page.title || page.path)}}</div>
          <div class="body">${{esc(page.summary || 'No summary available.')}}</div>
          <div class="tagrow">${{tagList([`Rank #${{page.rank || '?'}}`, `Score ${{page.score ?? 0}}`, page.status ? `Status: ${{page.status}}` : '', page.source_kind ? `Kind: ${{page.source_kind}}` : '', page.platform ? `Platform: ${{page.platform}}` : ''])}}</div>
          <div class="tagrow">${{tagList([page.path])}}</div>
        `;
        div.addEventListener('click', () => showSource(page));
        libraryGrid.appendChild(div);
      }}
      if (!rows.length) {{
        libraryGrid.innerHTML = '<div class="subtle">No corpus pages match your filter.</div>';
      }}
    }}

    function renderWikiSets(filterText = '') {{
      const needle = filterText.trim().toLowerCase();
      wikiSetGrid.innerHTML = '';
      const rows = data.wiki_sets.filter(item => !needle || cardText({{...item, title: item.name}}).includes(needle));
      for (const item of rows) {{
        const div = document.createElement('div');
        div.className = 'item';
        div.dataset.kind = 'wiki-set';
        div.dataset.text = cardText({{...item, title: item.name}});
        div.innerHTML = `
          <div class="title">${{esc(item.name)}}</div>
          <div class="body">${{esc(item.purpose || 'Wiki set')}}</div>
          <div class="tagrow">${{tagList([`Pages: ${{(item.pages || []).length}}`])}}</div>
          <div class="tagrow">${{tagList((item.pages || []).slice(0, 5))}}</div>
        `;
        div.addEventListener('click', () => showWikiSet(item));
        wikiSetGrid.appendChild(div);
      }}
      if (!rows.length) {{
        wikiSetGrid.innerHTML = '<div class="subtle">No wiki sets match your filter.</div>';
      }}
    }}

    function renderHomeLists(filterText = '') {{
      renderCompactList(connectedList, connectedRows(filterText), 'No connected pages match your filter.', 'node');
      renderCompactList(recentList, recentRows(filterText), 'No recent pages match your filter.', 'node');
    }}

    function renderEdges() {{
      edgeTable.innerHTML = '';
      for (const edge of (data.graph.edges || []).slice(0, 24)) {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td class="mono">${{esc(edge.source)}}</td><td>${{esc(edge.type)}}</td><td class="mono">${{esc(edge.target)}}</td>`;
        edgeTable.appendChild(tr);
      }}
      if (!(data.graph.edges || []).length) {{
        edgeTable.innerHTML = '<tr><td colspan="3" class="subtle">No edges available.</td></tr>';
      }}
    }}

    function renderPrivacy() {{
      const endpoint = data.privacy?.model_endpoint || {{}};
      const browser = data.privacy?.browser || {{}};
      document.getElementById('privacyEndpoint').textContent = endpoint.classification || 'unknown';
      document.getElementById('privacyScope').textContent = endpoint.network_scope || 'unknown';
      document.getElementById('privacyRisk').textContent = endpoint.risk || 'unknown';
      document.getElementById('privacyFetches').textContent = String(browser.active_outbound_fetches ?? false);
      document.getElementById('privacyProfiles').textContent = data.privacy?.prompt_profiles?.source_path || 'built-in defaults';
    }}

    function setDetailHeader(label, sublabel) {{
      detailKv.innerHTML = `<div>${{esc(label)}}</div><strong>${{esc(sublabel)}}</strong>`;
    }}

    function showSource(page) {{
      setDetailHeader(page.title || page.path, `Source page · Rank #${{page.rank || '?'}}`);
      detailBody.innerHTML = `
        <div class="detail-section">
          <h3>Links</h3>
          <div class="list">
            <a href="${{esc(page.source_page_href || '#')}}">Open generated source summary</a>
            <div class="subtle mono">${{esc(page.path || '')}}</div>
            ${{page.source_url ? `<a href="${{esc(page.source_url)}}" target="_blank" rel="noreferrer">Original source URL</a>` : '<div class="subtle">No original source URL recorded.</div>'}}
          </div>
        </div>
        <div class="detail-section">
          <h3>Provenance</h3>
          <div class="kv">
            <div>Source kind</div><strong>${{esc(page.source_kind || 'unknown')}}</strong>
            <div>Platform</div><strong>${{esc(page.platform || 'unknown')}}</strong>
            <div>Extracted at</div><strong>${{esc(page.extracted_at || 'unknown')}}</strong>
            <div>Status</div><strong>${{esc(page.status || 'new')}}</strong>
            <div>Score</div><strong>${{esc(page.score ?? 0)}}</strong>
            <div>Backlinks</div><strong>${{esc(page.backlinks ?? 0)}}</strong>
            <div>Outlinks</div><strong>${{esc(page.outlinks ?? 0)}}</strong>
            <div>Related</div><strong>${{esc(page.related_count ?? 0)}}</strong>
            <div>Used in</div><strong>${{esc(page.used_in_count ?? 0)}}</strong>
            <div>Links to</div><strong>${{esc((page.links_to || []).length)}}</strong>
            <div>Linked from</div><strong>${{esc((page.linked_from || []).length)}}</strong>
          </div>
        </div>
        <div class="detail-section">
          <h3>Wiki summary</h3>
          <div class="subtle">${{esc(page.summary || 'No summary available.')}}</div>
        </div>
        <div class="detail-section">
          <h3>Tags</h3>
          <div class="tagrow">${{tagList(page.tags || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Topics</h3>
          <div class="tagrow">${{tagList(page.topics || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Entities</h3>
          <div class="tagrow">${{tagList(page.entities || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Links to</h3>
          <div class="tagrow">${{tagList(page.links_to || page.related_pages || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Linked from</h3>
          <div class="tagrow">${{tagList(page.linked_from || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Related pages</h3>
          <div class="tagrow">${{tagList(page.related_pages || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Used in</h3>
          <div class="tagrow">${{tagList(page.used_in || [])}}</div>
        </div>
        <div class="detail-section">
          <h3>Key snippets</h3>
          ${{snippetList(page.key_snippets || [])}}
        </div>
      `;
    }}

    function showWikiSet(item) {{
      setDetailHeader(item.name || 'Wiki set', 'Wiki set');
      detailBody.innerHTML = `
        <div class="detail-section">
          <h3>Links</h3>
          <div class="list">
            <a href="${{esc(item.index_href || '#')}}">Open wiki set index</a>
          </div>
        </div>
        <div class="detail-section">
          <h3>Purpose</h3>
          <div class="subtle">${{esc(item.purpose || 'Wiki set')}}</div>
        </div>
        <div class="detail-section">
          <h3>Pages</h3>
          <div class="tagrow">${{tagList(item.pages || [])}}</div>
        </div>
      `;
    }}

    search.addEventListener('input', () => {{
      renderAll(search.value || '');
    }});

    function renderAll(value) {{
      renderHomeLists(value);
      renderSourceCards(value);
      renderLibraryCards(value);
      renderWikiSets(value);
    }}

    renderFacetRow(peopleFacetRow, data.facets?.people || []);
    renderFacetRow(topicFacetRow, data.facets?.topics || []);
    renderFacetRow(entityFacetRow, data.facets?.entities || []);
    renderAll('');
    renderEdges();
    renderPrivacy();
    if (data.library_pages.length) showSource(data.library_pages[0]);
    else if (data.sources.length) showSource(data.sources[0]);
  </script>
</body>
</html>"""


def write_browser_frontend(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> Path:
    payload = _browser_payload(config, scan, diff, pipeline)
    browser_dir = config.output_root / "browser"
    browser_dir.mkdir(parents=True, exist_ok=True)
    path = browser_dir / "index.html"
    path.write_text(_render_browser_html(payload), encoding="utf-8")
    (browser_dir / "data.json").write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
