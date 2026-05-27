from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from typing import Any

try:  # pragma: no cover - optional dependency in minimal envs
    from opentelemetry import trace
except Exception:  # pragma: no cover
    class _NoopSpan:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class _NoopTracer:
        def start_as_current_span(self, _name: str) -> _NoopSpan:
            return _NoopSpan()

    class _NoopTrace:
        def get_tracer(self, _name: str) -> _NoopTracer:
            return _NoopTracer()

    trace = _NoopTrace()  # type: ignore[assignment]

from wikimaker_openai import GenerationPlan, AnalysisPlan, VerificationPlan, run_pipeline
from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import write_discovery_views, _source_stub_name, _wiki_set_dir_name
from wikimaker_browser import write_browser_frontend
from wikimaker_health import build_wiki_health, write_health_report
from wikimaker_observability import configure_adk_tracing, run_adk_self_eval
from wikimaker_privacy import browser_network_posture, classify_endpoint_privacy
from wikimaker_profiles import apply_prompt_profiles
from wikimaker_scanner import scan_corpus
from wikimaker_state import diff_snapshots, load_snapshot, save_snapshot
from wikimaker_telemetry import build_telemetry, write_telemetry


def ensure_workspace(config: WikiMakerConfig) -> None:
    config.output_root.mkdir(parents=True, exist_ok=True)
    config.state_root.mkdir(parents=True, exist_ok=True)
    config.telemetry_root.mkdir(parents=True, exist_ok=True)
    Path(config.adk_eval_dir).expanduser().mkdir(parents=True, exist_ok=True)
    Path(config.adk_trace_db).expanduser().parent.mkdir(parents=True, exist_ok=True)
    (config.output_root / "sources").mkdir(parents=True, exist_ok=True)
    (config.output_root / "wiki-sets").mkdir(parents=True, exist_ok=True)
    (config.output_root / "browser").mkdir(parents=True, exist_ok=True)


def write_change_report(
    config: WikiMakerConfig,
    scan: dict[str, Any],
    diff: dict[str, list[str]],
    pipeline: dict[str, Any],
) -> Path:
    analysis = pipeline.get("analysis", {})
    generation = pipeline.get("generation", {})
    verification = pipeline.get("verification", {})
    report = [
        "# WikiMaker Change Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Corpus root: {config.corpus_root}",
        f"Output root: {config.output_root}",
        "",
        "## Diff summary",
        f"- Added: {len(diff['added'])}",
        f"- Changed: {len(diff['changed'])}",
        f"- Removed: {len(diff['removed'])}",
        f"- Unchanged: {len(diff['unchanged'])}",
        "",
        "## LLM pipeline",
        f"- LLM used: `{pipeline.get('llm_used')}`",
        f"- Pipeline errors: `{pipeline.get('errors', [])}`",
        f"- Endpoint privacy: `{pipeline.get('privacy', {}).get('classification', 'unknown')}` / `{pipeline.get('privacy', {}).get('risk', 'unknown')}`",
        "",
        "## Analysis",
        "```json",
        json.dumps(analysis, indent=2, sort_keys=True),
        "```",
        "",
        "## Generation",
        "```json",
        json.dumps(generation, indent=2, sort_keys=True),
        "```",
        "",
        "## Verification",
        "```json",
        json.dumps(verification, indent=2, sort_keys=True),
        "```",
        "",
        "## Files scanned",
    ]
    for rel_path, record in sorted(scan.get("files", {}).items()):
        title = record.get("title", rel_path)
        report.append(f"- `{rel_path}` — {title}")
    path = config.output_root / "_change_report.md"
    path.write_text("\n".join(report) + "\n", encoding="utf-8")
    return path


def _relationship_maps(source_pages: list[dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    lookup: dict[str, str] = {}
    title_by_path: dict[str, str] = {}
    for page in source_pages:
        rel_path = str(page.get("path") or "").strip()
        title = str(page.get("title") or Path(rel_path).stem or rel_path).strip()
        if rel_path:
            title_by_path[rel_path] = title
        for candidate in (rel_path, title, Path(rel_path).stem):
            key = "".join(ch for ch in str(candidate).lower() if ch.isalnum())
            if key and rel_path:
                lookup.setdefault(key, rel_path)
    links_to: dict[str, list[str]] = {str(page.get("path")): [] for page in source_pages if page.get("path")}
    linked_from: dict[str, list[str]] = {str(page.get("path")): [] for page in source_pages if page.get("path")}
    for page in source_pages:
        rel_path = str(page.get("path") or "").strip()
        source_title = title_by_path.get(rel_path, rel_path)
        if not rel_path:
            continue
        for item in page.get("related_pages", []) or []:
            key = "".join(ch for ch in str(item).lower() if ch.isalnum())
            target_path = lookup.get(key)
            if not target_path or target_path == rel_path:
                continue
            target_title = title_by_path.get(target_path, target_path)
            if target_title not in links_to[rel_path]:
                links_to[rel_path].append(target_title)
            if source_title not in linked_from[target_path]:
                linked_from[target_path].append(source_title)
    return links_to, linked_from


def write_source_stubs(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], generation: dict[str, Any]) -> list[Path]:
    written: list[Path] = []
    generation_pages = generation.get("source_pages", [])
    generation_by_path = {page.get("path"): page for page in generation_pages if isinstance(page, dict)}
    links_to, linked_from = _relationship_maps([page for page in generation_pages if isinstance(page, dict)])

    for rel_path, record in sorted(scan.get("files", {}).items()):
        if record.get("error"):
            continue
        page = generation_by_path.get(rel_path, {})
        out_path = config.output_root / "sources" / _source_stub_name(rel_path)
        content = [
            f"# {page.get('title') or record.get('title') or Path(rel_path).stem}",
            "",
            f"- Source markdown: `{rel_path}`",
            f"- SHA256: `{record.get('sha256')}`",
            f"- Size: `{record.get('size')}`",
            f"- Status: `{_status_for(rel_path, diff)}`",
            f"- Platform: `{record.get('platform') or page.get('platform') or ''}`",
            f"- Corpus kind: `{record.get('source_kind') or page.get('source_kind') or ''}`",
            f"- Corpus family: `{record.get('corpus_kind') or page.get('corpus_kind') or ''}`",
            f"- Page role: `{page.get('page_role') or ''}`",
            f"- Extracted at: `{record.get('extracted_at') or page.get('extracted_at') or ''}`",
            f"- Original source URL: `{record.get('source_url') or page.get('source_url') or ''}`",
            "",
            "## Navigation",
            "- [Root index](../_root_index.md)",
            "- [Dashboard](../_dashboard.md)",
            "- [Stats](../_stats.md)",
            "- [Search index](../_search.md)",
            "- [Browser UI](../browser/index.html)",
            "",
            "## Summary",
            page.get("summary") or f"Source page for {record.get('title') or Path(rel_path).stem}.",
            "",
            "## Key snippets",
        ]
        key_snippets = page.get("key_snippets") or []
        if key_snippets:
            content.extend(f"- {snippet}" for snippet in key_snippets)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Headings",
        ])
        headings = record.get("headings") or []
        if headings:
            content.extend(f"- {h}" for h in headings)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Raw source markdown",
        ])
        source_paths = page.get("source_paths") or [rel_path]
        if source_paths:
            content.extend(f"- `{src}`" for src in source_paths)
        else:
            content.append(f"- `{rel_path}`")
        content.extend([
            "",
            "## External references",
        ])
        source_links = list(page.get("external_links") or [])
        if not source_links:
            source_links = list(record.get("source_links") or [])
        if source_links:
            content.extend(f"- {link}" for link in source_links)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Tags",
        ])
        tags = page.get("tags") or []
        if tags:
            content.extend(f"- {tag}" for tag in tags)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Topics",
        ])
        topics = page.get("topics") or []
        if topics:
            content.extend(f"- {topic}" for topic in topics)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Entities",
        ])
        entities = page.get("entities") or []
        if entities:
            content.extend(f"- {entity}" for entity in entities)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Links to",
        ])
        links_to_items = links_to.get(rel_path, [])
        if links_to_items:
            content.extend(f"- {item}" for item in links_to_items)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Linked from",
        ])
        linked_from_items = linked_from.get(rel_path, [])
        if linked_from_items:
            content.extend(f"- {item}" for item in linked_from_items)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Related pages",
        ])
        related_pages = page.get("related_pages") or []
        if related_pages:
            content.extend(f"- {item}" for item in related_pages)
        else:
            content.append("- _None found_")
        content.extend([
            "",
            "## Used in",
        ])
        used_in = page.get("used_in") or []
        if used_in:
            content.extend(f"- {item}" for item in used_in)
        else:
            content.append("- _None found_")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(content) + "\n", encoding="utf-8")
        written.append(out_path)
    return written


def _safe_page_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip().lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "page"


def _matching_sources(source_pages: list[dict[str, Any]], label: str, field: str) -> list[dict[str, Any]]:
    normalized = label.strip().lower()
    matches = []
    for page in source_pages:
        values = [str(item).strip().lower() for item in page.get(field, []) or []]
        if normalized in values:
            matches.append(page)
    return matches


def write_knowledge_pages(config: WikiMakerConfig, pipeline: dict[str, Any], scan: dict[str, Any]) -> list[Path]:
    analysis = pipeline.get("analysis", {})
    generation = pipeline.get("generation", {})
    source_pages = [page for page in generation.get("source_pages", []) if isinstance(page, dict)]
    written: list[Path] = []

    def write_page(kind: str, label: str, matches: list[dict[str, Any]], extra_lines: list[str] | None = None) -> None:
        plural = {
            "entity": "entities",
            "topic": "topics",
            "duplicate": "duplicates",
            "contradiction": "contradictions",
        }.get(kind, f"{kind}s")
        out_dir = config.output_root / "wiki-sets" / f"_{plural}"
        out_path = out_dir / f"{_safe_page_name(label)}.md"
        lines = [
            f"# {label}",
            "",
            f"Purpose: synthesized {kind} page generated from source-summary metadata.",
            "",
            "## Synthesis",
        ]
        if matches:
            for page in matches[:12]:
                lines.append(f"- {page.get('summary') or page.get('title') or page.get('path')}")
        else:
            lines.append("- This page was detected as a corpus-level cluster but has sparse source-page metadata.")
        lines.extend([
            "",
            "## Sources",
        ])
        if matches:
            for page in matches[:30]:
                rel_path = str(page.get("path") or "")
                stub = _source_stub_name(rel_path) if rel_path else ""
                source_link = f"../../sources/{stub}" if stub else ""
                lines.append(f"- `{rel_path}`" + (f" — [source summary]({source_link})" if source_link else ""))
        else:
            lines.append("- _No direct sources matched by metadata._")
        lines.extend([
            "",
            "## Evidence / Truth trail",
        ])
        evidence = [snippet for page in matches for snippet in (page.get("key_snippets") or [])]
        if evidence:
            lines.extend(f"- {item}" for item in evidence[:20])
        else:
            lines.append("- _No evidence snippets were provided by the model._")
        lines.extend([
            "",
            "## Related pages",
        ])
        related = []
        for page in matches:
            related.extend(str(item) for item in page.get("related_pages", []) or [])
        if related:
            lines.extend(f"- {item}" for item in sorted(dict.fromkeys(related))[:20])
        else:
            lines.append("- _None found_")
        lines.extend([
            "",
            "## Duplicates / Near-duplicates",
        ])
        duplicates = analysis.get("duplicate_clusters") or []
        if duplicates:
            lines.extend(f"- {item}" for item in duplicates)
        else:
            lines.append("- _None found_")
        lines.extend([
            "",
            "## Evolution over time",
            "- Review source dates and folder ledgers for temporal changes.",
            "",
            "## Contradictions / Tensions",
        ])
        contradictions = analysis.get("contradiction_clusters") or []
        if contradictions:
            lines.extend(f"- {item}" for item in contradictions)
        else:
            lines.append("- _None found_")
        if extra_lines:
            lines.extend(["", *extra_lines])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(out_path)

    for topic in analysis.get("topic_clusters", []) or []:
        write_page("topic", str(topic), _matching_sources(source_pages, str(topic), "topics"))
    for entity in analysis.get("entity_clusters", []) or []:
        write_page("entity", str(entity), _matching_sources(source_pages, str(entity), "entities"))

    for cluster_kind, values in (("duplicate", analysis.get("duplicate_clusters") or []), ("contradiction", analysis.get("contradiction_clusters") or [])):
        for value in values:
            write_page(cluster_kind, str(value), source_pages, [f"## Cluster type", f"- {cluster_kind}"])
    return written


def write_privacy_report(config: WikiMakerConfig, scan: dict[str, Any], pipeline: dict[str, Any]) -> Path:
    privacy = pipeline.get("privacy") or classify_endpoint_privacy(config.openai_base_url)
    external_links = sum(len(record.get("source_links") or []) for record in scan.get("files", {}).values() if isinstance(record, dict))
    browser = browser_network_posture(has_active_fetches=False, external_links=external_links)
    lines = [
        "# WikiMaker Privacy and Model Boundary",
        "",
        "## Model endpoint",
        f"- Base URL: `{privacy.get('base_url', '')}`",
        f"- Host: `{privacy.get('host', '')}`",
        f"- Classification: `{privacy.get('classification', 'unknown')}`",
        f"- Network scope: `{privacy.get('network_scope', 'unknown')}`",
        f"- Risk: `{privacy.get('risk', 'unknown')}`",
        f"- Allowed by default: `{privacy.get('allowed_by_default')}`",
        f"- Reason: {privacy.get('reason', '')}",
        f"- Remote override enabled: `{config.allow_remote_llm}`",
        "",
        "## Browser network posture",
        f"- Classification: `{browser['classification']}`",
        f"- Active outbound fetches: `{browser['active_outbound_fetches']}`",
        f"- Passive external reference links: {browser['external_reference_links']}",
        f"- Reason: {browser['reason']}",
        "",
        "## Prompt profiles",
        f"- Profile source: `{scan.get('prompt_profiles', {}).get('source_path', '') or 'built-in defaults'}`",
        f"- Loaded local profile file: `{scan.get('prompt_profiles', {}).get('loaded')}`",
        "",
        "No remote fonts, image lookups, analytics, or hidden browser fetches are generated by WikiMaker.",
    ]
    path = config.output_root / "_privacy.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_root_index(config: WikiMakerConfig, pipeline: dict[str, Any]) -> Path:
    analysis = pipeline.get("analysis", {})
    generation = pipeline.get("generation", {})
    verification = pipeline.get("verification", {})
    source_pages = [page for page in generation.get("source_pages", []) if isinstance(page, dict)]
    primary_pages = [page for page in source_pages if str(page.get("page_role") or "knowledge_page") in {"knowledge_page", "thread_page"}]
    navigation_pages = [page for page in source_pages if str(page.get("page_role") or "") in {"index_page", "ledger_page", "duplicate_page", "contradiction_page"}]
    role_counts: dict[str, int] = {}
    for page in source_pages:
        role = str(page.get("page_role") or "knowledge_page").strip() or "knowledge_page"
        role_counts[role] = role_counts.get(role, 0) + 1
    path = config.output_root / "_root_index.md"
    lines = [
        "# WikiMaker Root Index",
        "",
        generation.get("root_index_summary") or analysis.get("corpus_summary") or "WikiMaker output index.",
        "",
        "## Jump table",
        "- [Navigation](#navigation)",
        "- [Corpus kinds](#corpus-kinds)",
        "- [Page roles](#page-roles)",
        "- [Source pages](#source-pages)",
        "- [Wiki sets](#wiki-sets)",
        "- [Verification](#verification)",
        "- [Reorg suggestions](#reorg-suggestions)",
        "",
        "## Navigation",
        "- [_Dashboard](_dashboard.md)",
        "- [_Stats](_stats.md)",
        "- [_Search index](_search.md)",
        "- [_Browser UI](browser/index.html)",
        "- [_Graph data](_graph.json)",
        "- [_Privacy boundary](_privacy.md)",
        "- [_Health check](_health.md)",
        "",
        "## Corpus kinds",
    ]
    corpus_kinds = analysis.get("corpus_kinds") or []
    if corpus_kinds:
        lines.extend(f"- {item}" for item in corpus_kinds)
    else:
        lines.append("- _Unknown_")
    lines.extend([
        "",
        "## Page roles",
        f"- Primary source pages: {len(primary_pages)}",
        f"- Navigation pages: {len(navigation_pages)}",
    ])
    for role in sorted(role_counts):
        lines.append(f"- {role}: {role_counts[role]}")
    lines.extend([
        "",
        "## Source pages",
        "| Title | Provenance | Source markdown | Stub | External/source link |",
        "| --- | --- | --- | --- | --- |",
    ])
    if source_pages:
        provenance_rank = {"knowledge_page": 0, "thread_page": 1, "index_page": 2, "ledger_page": 3, "duplicate_page": 4, "contradiction_page": 5}
        for page in sorted(source_pages, key=lambda item: (provenance_rank.get(str(item.get("page_role") or ""), 99), str(item.get("title") or ""))):
            rel_path = str(page.get("path") or "").strip()
            title = str(page.get("title") or Path(rel_path).stem or rel_path)
            role = str(page.get("page_role") or "knowledge_page").strip() or "knowledge_page"
            source_kind = str(page.get("source_kind") or "").strip()
            platform = str(page.get("platform") or "").strip()
            status = str(page.get("status") or "").strip()
            provenance_bits = [role.replace("_", " ").title()]
            if source_kind:
                provenance_bits.append(source_kind.replace("_", " "))
            if platform:
                provenance_bits.append(platform)
            if status:
                provenance_bits.append(status)
            provenance = ", ".join(bit for bit in provenance_bits if bit)
            stub_name = _source_stub_name(rel_path) if rel_path else ""
            stub_link = f"[source stub](sources/{stub_name})" if stub_name else "_None_"
            source_markdown = f"`{rel_path}`" if rel_path else "_Unknown_"
            source_link = str(page.get("source_url") or page.get("external_link") or page.get("original_source_url") or "").strip()
            if source_link:
                source_link_cell = f"[{source_link}]({source_link})"
            else:
                source_link_cell = "_None_"
            lines.append(f"| {title} | {provenance} | {source_markdown} | {stub_link} | {source_link_cell} |")
    else:
        lines.append("| _None_ | _None_ | _None_ | _None_ | _None_ |")
    lines.extend([
        "",
        "## Wiki sets",
    ])
    for wiki_set in generation.get("wiki_set_pages", []):
        if not isinstance(wiki_set, dict):
            continue
        lines.append(f"- **{wiki_set.get('name', 'unnamed')}** — {wiki_set.get('purpose', '')}")
    lines.extend([
        "",
        "## Verification",
        f"- Approved: `{verification.get('approved')}`",
        f"- Confidence: `{verification.get('confidence')}`",
        "",
        "## Reorg suggestions",
    ])
    suggestions = analysis.get("reorg_suggestions") or []
    if suggestions:
        lines.extend(f"- {item}" for item in suggestions)
    else:
        lines.append("- _None_")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_wiki_set_pages(config: WikiMakerConfig, pipeline: dict[str, Any], scan: dict[str, Any]) -> list[Path]:
    generation = pipeline.get("generation", {})
    source_pages = generation.get("source_pages", [])
    written: list[Path] = []

    for wiki_set in generation.get("wiki_set_pages", []):
        if not isinstance(wiki_set, dict):
            continue
        set_name = str(wiki_set.get("name", "unnamed")).strip() or "unnamed"
        out_dir = config.output_root / "wiki-sets" / _wiki_set_dir_name(set_name)
        out_path = out_dir / "_index.md"
        page_titles = [str(page) for page in (wiki_set.get("pages") or [])]
        matching_sources = [page for page in source_pages if isinstance(page, dict) and page.get("title") in page_titles]
        lines = [
            f"# {set_name}",
            "",
            wiki_set.get("purpose") or "Wiki set index.",
            "",
            "## Pages",
        ]
        if page_titles:
            lines.extend(f"- {title}" for title in page_titles)
        else:
            lines.append("- _None_")
        lines.extend([
            "",
            "## Source pages",
        ])
        if matching_sources:
            for source in matching_sources:
                lines.append(f"- `{source.get('path')}` — {source.get('summary', '')}")
        else:
            lines.append("- _None_")
        lines.extend([
            "",
            "## Links",
            "- Source overview is in the individual source-summary pages.",
        ])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(out_path)

    return written


def write_folder_docs(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> list[Path]:
    generation = pipeline.get("generation", {})
    source_pages = generation.get("source_pages", [])
    source_by_path = {page.get("path"): page for page in source_pages if isinstance(page, dict)}
    files = scan.get("files", {})
    folders: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for rel_path, record in files.items():
        folder = str(Path(rel_path).parent)
        folders.setdefault(folder, []).append((rel_path, record))

    timestamp = datetime.now(timezone.utc).isoformat()
    written: list[Path] = []

    for folder, entries in sorted(folders.items()):
        out_dir = config.output_root / "folders" / ("root" if folder == "." else folder)
        gist_path = out_dir / "gist.md"
        ledger_path = out_dir / "ledger.md"
        folder_source_pages = [source_by_path[rel_path] for rel_path, _ in entries if rel_path in source_by_path]
        summary_lines = [
            f"# Folder gist: {folder}",
            "",
            f"Updated: {timestamp}",
            f"Files: {len(entries)}",
            "",
            "## Key files",
        ]
        for rel_path, record in entries[:12]:
            summary_lines.append(f"- `{rel_path}` — {record.get('title') or Path(rel_path).stem}")
        summary_lines.extend([
            "",
            "## Current understanding",
        ])
        if folder_source_pages:
            for page in folder_source_pages[:10]:
                summary_lines.append(f"- {page.get('summary')}")
        else:
            summary_lines.append("- _No source pages yet_")
        summary_lines.extend([
            "",
            "## Notes",
            "- Read-only source folder.",
            "- Generated wiki memory lives in the sibling output tree.",
        ])
        out_dir.mkdir(parents=True, exist_ok=True)
        gist_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

        changed = len([rel for rel, _ in entries if rel in diff.get("changed", [])])
        added = len([rel for rel, _ in entries if rel in diff.get("added", [])])
        removed = len([rel for rel, _ in entries if rel in diff.get("removed", [])])
        ledger_entry = [
            f"## {timestamp}",
            f"- files: {len(entries)}",
            f"- added: {added}, changed: {changed}, removed: {removed}",
            "- gist refreshed: yes",
            f"- source pages linked: {len(folder_source_pages)}",
            "",
        ]
        with ledger_path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(ledger_entry))

        written.extend([gist_path, ledger_path])

    return written


def _source_stub_name(rel_path: str) -> str:
    parts = [part.replace(":", "_").replace("?", "_").replace("*", "_").replace("/", "_") for part in Path(rel_path).parts]
    candidate = "__".join(parts)
    if len(candidate) <= 160:
        return candidate
    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]
    if len(parts) == 1:
        prefix = [parts[0][:48]]
    elif len(parts) == 2:
        prefix = [parts[0][:24], parts[1][:80]]
    else:
        prefix = [parts[0][:24], parts[1][:24], parts[-1][:80]]
    shortened = "__".join(prefix + [digest])
    return shortened[:160]


def _status_for(rel_path: str, diff: dict[str, list[str]]) -> str:
    for label in ("added", "changed", "removed", "unchanged"):
        if rel_path in diff.get(label, []):
            return label
    return "new"


def _write_dry_run_preview(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], pipeline: dict[str, Any]) -> Path:
    telemetry_preview = config.telemetry_root / "dry_run_preview.md"
    lines = [
        "# WikiMaker Dry Run Preview",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Corpus root: {config.corpus_root}",
        f"Output root: {config.output_root}",
        f"State root: {config.state_root}",
        "",
        "## Summary",
        f"- Files scanned: {len(scan.get('files', {}))}",
        f"- Added: {len(diff['added'])}",
        f"- Changed: {len(diff['changed'])}",
        f"- Removed: {len(diff['removed'])}",
        f"- Unchanged: {len(diff['unchanged'])}",
        f"- LLM used: `{pipeline.get('llm_used')}`",
        f"- Pipeline errors: `{pipeline.get('errors', [])}`",
        f"- Endpoint privacy: `{pipeline.get('privacy', {}).get('classification', 'unknown')}` / `{pipeline.get('privacy', {}).get('risk', 'unknown')}`",
        f"- Prompt profile source: `{scan.get('prompt_profiles', {}).get('source_path', '') or 'built-in defaults'}`",
        "",
        "## File-by-file preview",
        "| Status | Path | Title | Headings | Links |",
        "| --- | --- | --- | --- | --- |",
    ]
    files = scan.get("files", {})
    for rel_path, record in sorted(files.items()):
        status = _status_for(rel_path, diff)
        title = str(record.get("title") or Path(rel_path).stem).replace("|", "\\|")
        headings = str(len(record.get("headings") or []))
        links = str(len(record.get("source_links") or []))
        lines.append(f"| {status} | `{rel_path}` | {title} | {headings} | {links} |")
    lines.extend([
        "",
        "## Analysis",
        "```json",
        json.dumps(pipeline.get("analysis", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Generation",
        "```json",
        json.dumps(pipeline.get("generation", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Verification",
        "```json",
        json.dumps(pipeline.get("verification", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Notes",
        "- Dry run does not write wiki output files or update the corpus snapshot.",
        "- Use the preview to check the file list, status distribution, and planned wiki structure before applying changes.",
    ])
    telemetry_preview.parent.mkdir(parents=True, exist_ok=True)
    telemetry_preview.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return telemetry_preview


def run(config: WikiMakerConfig) -> dict[str, Any]:
    ensure_workspace(config)
    tracing_state = configure_adk_tracing(config.as_dict())
    tracer = trace.get_tracer("wikimaker")
    endpoint_privacy = classify_endpoint_privacy(config.openai_base_url)

    with tracer.start_as_current_span("wikimaker.run") as root_span:
        root_span.set_attribute("wikimaker.corpus_root", str(config.corpus_root))
        root_span.set_attribute("wikimaker.output_root", str(config.output_root))
        root_span.set_attribute("wikimaker.provider", config.provider)
        root_span.set_attribute("wikimaker.endpoint_privacy", str(endpoint_privacy.get("classification", "unknown")))
        root_span.set_attribute("wikimaker.use_adk", bool(config.use_adk))
        root_span.set_attribute("wikimaker.enable_adk_eval", bool(config.enable_adk_eval))
        root_span.set_attribute("wikimaker.dry_run", bool(config.dry_run))

        with tracer.start_as_current_span("wikimaker.scan"):
            previous = load_snapshot(config.state_root)
            scan = scan_corpus(config.corpus_root, progress_every=int(config.as_dict().get("progress_every", 0) or 0))
            scan = apply_prompt_profiles(scan, corpus_root=config.corpus_root, profile_path=config.prompt_profile_path or None)
            current = {"generated_at": datetime.now(timezone.utc).isoformat(), "files": scan.get("files", {})}
            diff = diff_snapshots(previous, current)

        with tracer.start_as_current_span("wikimaker.pipeline"):
            pipeline = run_pipeline(scan, diff, config.as_dict())
            pipeline["privacy"] = endpoint_privacy

        with tracer.start_as_current_span("wikimaker.telemetry"):
            telemetry = build_telemetry(config.telemetry_dict(), diff, scan)
            telemetry["pipeline"] = {
                "llm_used": pipeline.get("llm_used"),
                "errors": pipeline.get("errors", []),
                "analysis_confidence": pipeline.get("analysis", {}).get("confidence"),
                "generation_confidence": pipeline.get("generation", {}).get("confidence"),
                "verification_confidence": pipeline.get("verification", {}).get("confidence"),
            }
            telemetry["privacy"] = endpoint_privacy
            telemetry["prompt_profiles"] = scan.get("prompt_profiles", {})
            telemetry["observability"] = {
                "tracing": tracing_state,
            }
            telemetry_path = write_telemetry(config.telemetry_root, telemetry)

        if config.dry_run:
            with tracer.start_as_current_span("wikimaker.preview"):
                preview_path = _write_dry_run_preview(config, scan, diff, pipeline)
            report_path = preview_path
            root_index_path = None
            source_stub_paths: list[Path] = []
            snapshot_path = None
            wiki_set_paths: list[Path] = []
            folder_doc_paths: list[Path] = []
            discovery_paths: dict[str, Path] = {}
            knowledge_page_paths: list[Path] = []
            privacy_path = None
            health_path = None
        else:
            with tracer.start_as_current_span("wikimaker.publish"):
                report_path = write_change_report(config, scan, diff, pipeline)
                root_index_path = write_root_index(config, pipeline)
                source_stub_paths = write_source_stubs(config, scan, diff, pipeline.get("generation", {}))
                wiki_set_paths = write_wiki_set_pages(config, pipeline, scan)
                knowledge_page_paths = write_knowledge_pages(config, pipeline, scan)
                folder_doc_paths = write_folder_docs(config, scan, diff, pipeline)
                discovery_paths = write_discovery_views(config, scan, diff, pipeline)
                browser_path = write_browser_frontend(config, scan, diff, pipeline)
                discovery_paths["browser"] = browser_path
                privacy_path = write_privacy_report(config, scan, pipeline)
                graph_data = json.loads(discovery_paths["graph"].read_text(encoding="utf-8")) if discovery_paths.get("graph") else {}
                health = build_wiki_health(scan, pipeline, graph_data)
                health_path = write_health_report(config.output_root, health)
                snapshot_path = save_snapshot(config.state_root, current)

        if config.enable_adk_eval:
            with tracer.start_as_current_span("wikimaker.eval"):
                eval_result = run_adk_self_eval(scan, diff, pipeline, config.as_dict())
        else:
            eval_result = {
                "enabled": False,
                "available": False,
                "used": False,
                "error": "ADK evaluation disabled in config.",
                "eval_set_id": "wikimaker-self-check",
                "metric": "response_match_score",
            }

        telemetry["observability"]["evaluation"] = eval_result
        telemetry_path = write_telemetry(config.telemetry_root, telemetry)

        result = {
            "config": config.as_dict(),
            "scan": {
                "total_files": len(scan.get("files", {})),
                "added": len(diff["added"]),
                "changed": len(diff["changed"]),
                "removed": len(diff["removed"]),
                "unchanged": len(diff["unchanged"]),
            },
            "paths": {
                "telemetry": str(telemetry_path),
                "report": str(report_path),
                "root_index": str(root_index_path) if root_index_path else "",
                "snapshot": str(snapshot_path) if snapshot_path else "",
                "source_stubs": [str(p) for p in source_stub_paths],
                "wiki_set_pages": [str(p) for p in wiki_set_paths],
                "folder_docs": [str(p) for p in folder_doc_paths],
                "knowledge_pages": [str(p) for p in knowledge_page_paths],
                "dashboard": str(discovery_paths.get("dashboard", "")) if discovery_paths else "",
                "stats": str(discovery_paths.get("stats", "")) if discovery_paths else "",
                "search": str(discovery_paths.get("search", "")) if discovery_paths else "",
                "graph": str(discovery_paths.get("graph", "")) if discovery_paths else "",
                "browser": str(discovery_paths.get("browser", "")) if discovery_paths else "",
                "privacy": str(privacy_path) if privacy_path else "",
                "health": str(health_path) if health_path else "",
                "adk_trace_db": config.adk_trace_db,
                "adk_eval_dir": config.adk_eval_dir,
            },
            "observability": {
                "tracing": tracing_state,
                "evaluation": eval_result,
            },
            "llm": {
                "used": pipeline.get("llm_used"),
                "errors": pipeline.get("errors", []),
                "privacy": endpoint_privacy,
            },
            "analysis": pipeline.get("analysis", {}),
            "generation": pipeline.get("generation", {}),
            "verification": pipeline.get("verification", {}),
        }
        return result
