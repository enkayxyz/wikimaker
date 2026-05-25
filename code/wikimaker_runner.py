from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from opentelemetry import trace

from wikimaker_openai import GenerationPlan, AnalysisPlan, VerificationPlan, run_pipeline
from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import write_discovery_views, _source_stub_name, _wiki_set_dir_name
from wikimaker_browser import write_browser_frontend
from wikimaker_observability import configure_adk_tracing, run_adk_self_eval
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


def write_source_stubs(config: WikiMakerConfig, scan: dict[str, Any], diff: dict[str, list[str]], generation: dict[str, Any]) -> list[Path]:
    written: list[Path] = []
    generation_pages = generation.get("source_pages", [])
    generation_by_path = {page.get("path"): page for page in generation_pages if isinstance(page, dict)}

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


def write_root_index(config: WikiMakerConfig, pipeline: dict[str, Any]) -> Path:
    analysis = pipeline.get("analysis", {})
    generation = pipeline.get("generation", {})
    verification = pipeline.get("verification", {})
    path = config.output_root / "_root_index.md"
    lines = [
        "# WikiMaker Root Index",
        "",
        generation.get("root_index_summary") or analysis.get("corpus_summary") or "WikiMaker output index.",
        "",
        "## Navigation",
        "- [_Dashboard](_dashboard.md)",
        "- [_Stats](_stats.md)",
        "- [_Search index](_search.md)",
        "- [_Browser UI](browser/index.html)",
        "- [_Graph data](_graph.json)",
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
    return "__".join(part.replace(":", "_").replace("?", "_").replace("*", "_").replace("/", "_") for part in Path(rel_path).parts)


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

    with tracer.start_as_current_span("wikimaker.run") as root_span:
        root_span.set_attribute("wikimaker.corpus_root", str(config.corpus_root))
        root_span.set_attribute("wikimaker.output_root", str(config.output_root))
        root_span.set_attribute("wikimaker.provider", config.provider)
        root_span.set_attribute("wikimaker.use_adk", bool(config.use_adk))
        root_span.set_attribute("wikimaker.enable_adk_eval", bool(config.enable_adk_eval))
        root_span.set_attribute("wikimaker.dry_run", bool(config.dry_run))

        with tracer.start_as_current_span("wikimaker.scan"):
            previous = load_snapshot(config.state_root)
            scan = scan_corpus(config.corpus_root, progress_every=int(config.as_dict().get("progress_every", 0) or 0))
            current = {"generated_at": datetime.now(timezone.utc).isoformat(), "files": scan.get("files", {})}
            diff = diff_snapshots(previous, current)

        with tracer.start_as_current_span("wikimaker.pipeline"):
            pipeline = run_pipeline(scan, diff, config.as_dict())

        with tracer.start_as_current_span("wikimaker.telemetry"):
            telemetry = build_telemetry(config.telemetry_dict(), diff, scan)
            telemetry["pipeline"] = {
                "llm_used": pipeline.get("llm_used"),
                "errors": pipeline.get("errors", []),
                "analysis_confidence": pipeline.get("analysis", {}).get("confidence"),
                "generation_confidence": pipeline.get("generation", {}).get("confidence"),
                "verification_confidence": pipeline.get("verification", {}).get("confidence"),
            }
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
        else:
            with tracer.start_as_current_span("wikimaker.publish"):
                report_path = write_change_report(config, scan, diff, pipeline)
                root_index_path = write_root_index(config, pipeline)
                source_stub_paths = write_source_stubs(config, scan, diff, pipeline.get("generation", {}))
                wiki_set_paths = write_wiki_set_pages(config, pipeline, scan)
                folder_doc_paths = write_folder_docs(config, scan, diff, pipeline)
                discovery_paths = write_discovery_views(config, scan, diff, pipeline)
                browser_path = write_browser_frontend(config, scan, diff, pipeline)
                discovery_paths["browser"] = browser_path
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
                "dashboard": str(discovery_paths.get("dashboard", "")) if discovery_paths else "",
                "stats": str(discovery_paths.get("stats", "")) if discovery_paths else "",
                "search": str(discovery_paths.get("search", "")) if discovery_paths else "",
                "graph": str(discovery_paths.get("graph", "")) if discovery_paths else "",
                "browser": str(discovery_paths.get("browser", "")) if discovery_paths else "",
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
            },
            "analysis": pipeline.get("analysis", {}),
            "generation": pipeline.get("generation", {}),
            "verification": pipeline.get("verification", {}),
        }
        return result
