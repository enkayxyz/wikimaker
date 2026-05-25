from __future__ import annotations

from html import escape
from pathlib import Path
import json
from typing import Any

from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import build_discovery_views, _source_stub_name, _wiki_set_dir_name


def _browser_payload(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> dict[str, Any]:
    discovery = build_discovery_views(scan, diff, pipeline)
    graph = discovery.get("graph", {})
    source_pages = []
    source_by_path = {page.get("path"): page for page in discovery.get("source_pages", []) if page.get("path")}
    source_node_by_path = {node.get("path"): node for node in graph.get("nodes", []) if node.get("type") == "source" and node.get("path")}

    for page in discovery.get("source_pages", []):
        rel_path = str(page.get("path") or "")
        node = source_node_by_path.get(rel_path, {})
        source_pages.append(
            {
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

    source_pages.sort(key=lambda item: (item.get("score", 0), item.get("backlinks", 0), item.get("outlinks", 0), item.get("title", "")), reverse=True)
    wiki_sets.sort(key=lambda item: (len(item.get("pages", [])), item.get("name", "")), reverse=True)

    return {
        "generated_at": discovery.get("generated_at"),
        "analysis": discovery.get("analysis", {}),
        "generation": discovery.get("generation", {}),
        "verification": discovery.get("verification", {}),
        "counts": {
            "files": len(scan.get("files", {})),
            "source_pages": len(source_pages),
            "wiki_sets": len(wiki_sets),
            "nodes": len(graph.get("nodes", [])),
            "edges": len(graph.get("edges", [])),
        },
        "diff": diff,
        "sources": source_pages,
        "wiki_sets": wiki_sets,
        "graph": graph,
        "paths": {
            "root_index": "../_root_index.md",
            "dashboard": "../_dashboard.md",
            "stats": "../_stats.md",
            "search": "../_search.md",
            "graph": "../_graph.json",
        },
    }


def _render_browser_html(payload: dict[str, Any]) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    generated_at = escape(str(payload.get("generated_at") or ""))
    sources_count = payload.get("counts", {}).get("source_pages", 0)
    wiki_sets_count = payload.get("counts", {}).get("wiki_sets", 0)
    nodes_count = payload.get("counts", {}).get("nodes", 0)
    edges_count = payload.get("counts", {}).get("edges", 0)

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>WikiMaker Browser</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #081120;
      --panel: rgba(12, 19, 35, 0.92);
      --panel-2: rgba(17, 25, 45, 0.92);
      --line: rgba(148, 163, 184, 0.2);
      --text: #e5eefb;
      --muted: #97a6c6;
      --accent: #7dd3fc;
      --accent-2: #a78bfa;
      --good: #4ade80;
      --warn: #fbbf24;
      --bad: #fb7185;
      --shadow: 0 18px 50px rgba(0, 0, 0, 0.32);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(125, 211, 252, 0.18), transparent 25%),
        radial-gradient(circle at top right, rgba(167, 139, 250, 0.16), transparent 22%),
        linear-gradient(180deg, #060b16 0%, #0b1324 100%);
      color: var(--text);
      min-height: 100vh;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    .hero {{
      display: grid;
      gap: 18px;
      grid-template-columns: 1.2fr 0.8fr;
      align-items: stretch;
      margin-bottom: 18px;
    }}
    .card {{
      background: linear-gradient(180deg, var(--panel), var(--panel-2));
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }}
    .hero-main {{ padding: 24px; }}
    .kicker {{ text-transform: uppercase; letter-spacing: .12em; color: var(--muted); font-size: 12px; margin-bottom: 10px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(2rem, 4vw, 3.5rem); }}
    .lead {{ color: var(--muted); font-size: 1.02rem; line-height: 1.55; max-width: 75ch; }}
    .meta {{ margin-top: 18px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .pill {{
      display: inline-flex; align-items: center; gap: 8px;
      padding: 8px 12px; border-radius: 999px;
      background: rgba(148, 163, 184, 0.10); border: 1px solid rgba(148, 163, 184, 0.18);
      color: var(--text); font-size: 13px;
    }}
    .pill strong {{ color: white; }}
    .hero-side {{ padding: 18px; display: grid; gap: 12px; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .stat {{ padding: 16px; border-radius: 16px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); }}
    .stat .num {{ font-size: 1.8rem; font-weight: 700; }}
    .stat .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .toolbar {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; margin: 18px 0; }}
    .searchbox {{
      width: 100%; padding: 16px 18px; border-radius: 16px; border: 1px solid var(--line);
      background: rgba(255,255,255,0.04); color: var(--text); font-size: 1rem;
    }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }}
    .nav a {{
      display: inline-flex; align-items: center; padding: 10px 12px; border-radius: 12px;
      background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
      color: var(--text);
    }}
    .layout {{ display: grid; grid-template-columns: 1.5fr 0.9fr; gap: 18px; align-items: start; }}
    .section {{ padding: 18px; }}
    .section h2 {{ margin: 0 0 12px; font-size: 1.15rem; }}
    .subtle {{ color: var(--muted); font-size: 0.95rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
    .item {{
      padding: 14px; border-radius: 16px; background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.07); cursor: pointer;
      transition: transform .15s ease, border-color .15s ease, background .15s ease;
    }}
    .item:hover {{ transform: translateY(-2px); border-color: rgba(125, 211, 252, 0.45); background: rgba(255,255,255,0.05); }}
    .item .title {{ font-weight: 700; margin-bottom: 6px; }}
    .item .body {{ color: var(--muted); font-size: 0.95rem; line-height: 1.45; }}
    .tagrow {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }}
    .tag {{ font-size: 12px; padding: 5px 8px; border-radius: 999px; background: rgba(125, 211, 252, 0.12); color: #bae6fd; border: 1px solid rgba(125, 211, 252, 0.18); }}
    .status {{ font-size: 12px; padding: 4px 8px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.12); }}
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
    th, td {{ padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; vertical-align: top; }}
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
    <div class="hero card">
      <div class="hero-main">
        <div class="kicker">WikiMaker browser frontend</div>
        <h1>Browse the corpus like a wiki, without losing provenance.</h1>
        <div class="lead">
          This local browser UI is generated from WikiMaker’s discovery artifacts. It highlights the most connected source pages,
          wiki sets, and graph relationships while keeping every page one click away from the underlying generated Markdown.
        </div>
        <div class="meta">
          <span class="pill"><strong>Generated</strong> {generated_at}</span>
          <span class="pill"><strong>Sources</strong> {sources_count}</span>
          <span class="pill"><strong>Wiki sets</strong> {wiki_sets_count}</span>
          <span class="pill"><strong>Nodes</strong> {nodes_count}</span>
          <span class="pill"><strong>Edges</strong> {edges_count}</span>
        </div>
      </div>
      <div class="hero-side card">
        <div class="stat-grid">
          <div class="stat"><div class="num" id="countSources">{sources_count}</div><div class="label">source pages</div></div>
          <div class="stat"><div class="num" id="countSets">{wiki_sets_count}</div><div class="label">wiki sets</div></div>
          <div class="stat"><div class="num" id="countNodes">{nodes_count}</div><div class="label">graph nodes</div></div>
          <div class="stat"><div class="num" id="countEdges">{edges_count}</div><div class="label">graph edges</div></div>
        </div>
        <div class="subtle">No outbound fetches. No remote fonts. Static, local-first browsing only.</div>
      </div>
    </div>

    <div class="toolbar">
      <input class="searchbox" id="search" placeholder="Filter by title, topic, entity, tag, path, or wiki set…" />
      <div class="nav">
        <a href="../_root_index.md">Root index</a>
        <a href="../_dashboard.md">Dashboard</a>
        <a href="../_stats.md">Stats</a>
        <a href="../_search.md">Search</a>
        <a href="../_graph.json">Graph JSON</a>
      </div>
    </div>

    <div class="layout">
      <div class="stack">
        <section class="card section">
          <h2>Source pages</h2>
          <div class="subtle">Ranked by graph importance, connection strength, and recency.</div>
          <div class="grid" id="sourceGrid"></div>
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
    const wikiSetGrid = document.getElementById('wikiSetGrid');
    const edgeTable = document.getElementById('edgeTable');
    const detailKv = document.getElementById('detailKv');
    const detailBody = document.getElementById('detailBody');
    const search = document.getElementById('search');

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

    function snippetList(items) {{
      if (!items || !items.length) return '<div class="subtle">None</div>';
      return `<div class="list">${{items.map(item => `<div class="item" style="cursor:default">${{esc(item)}}</div>`).join('')}}</div>`;
    }}

    function cardText(page) {{
      return [page.title, page.summary, page.path, ...(page.tags || []), ...(page.topics || []), ...(page.entities || []), ...(page.related_pages || []), ...(page.used_in || [])].join(' ').toLowerCase();
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
          <div class="tagrow">${{tagList([`Rank #${{page.rank || '?'}}`, `Score ${{page.score ?? 0}}`, page.status ? `Status: ${{page.status}}` : ''])}}</div>
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
          <h3>Metrics</h3>
          <div class="kv">
            <div>Status</div><strong>${{esc(page.status || 'new')}}</strong>
            <div>Score</div><strong>${{esc(page.score ?? 0)}}</strong>
            <div>Backlinks</div><strong>${{esc(page.backlinks ?? 0)}}</strong>
            <div>Outlinks</div><strong>${{esc(page.outlinks ?? 0)}}</strong>
            <div>Related</div><strong>${{esc(page.related_count ?? 0)}}</strong>
            <div>Used in</div><strong>${{esc(page.used_in_count ?? 0)}}</strong>
          </div>
        </div>
        <div class="detail-section">
          <h3>Summary</h3>
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
      const value = search.value || '';
      renderSourceCards(value);
      renderWikiSets(value);
    }});

    renderSourceCards('');
    renderWikiSets('');
    renderEdges();
    if (data.sources.length) showSource(data.sources[0]);
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
