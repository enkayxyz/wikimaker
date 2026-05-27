from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class SourcePagePlan(BaseModel):
    path: str = Field(description="Relative source file path or stable source identifier")
    title: str = Field(description="Human-readable page title")
    page_role: str = Field(default="knowledge_page", description="Explicit role for the page: knowledge_page, thread_page, index_page, ledger_page, duplicate_page, or contradiction_page")
    summary: str = Field(description="Short source-summary of what the page contains")
    platform: str = Field(default="", description="Source platform or extractor label, if known")
    source_kind: str = Field(default="", description="Corpus kind such as bills or whatsapp, if known")
    extracted_at: str = Field(default="", description="Known extracted or source timestamp")
    source_url: str = Field(default="", description="Original source URL, if present")
    source_paths: list[str] = Field(default_factory=list, description="Direct source markdown paths used for this page")
    external_links: list[str] = Field(default_factory=list, description="Original URLs or external references")
    tags: list[str] = Field(default_factory=list, description="Broad tags attached to the page")
    topics: list[str] = Field(default_factory=list, description="Specific topics represented on the page")
    entities: list[str] = Field(default_factory=list, description="Named entities or actors mentioned on the page")
    related_pages: list[str] = Field(default_factory=list, description="Suggested internal links")
    used_in: list[str] = Field(default_factory=list, description="Higher-level wiki pages that use this source page")
    key_snippets: list[str] = Field(default_factory=list, description="Important quotes or evidence snippets")
    breadcrumbs: list[str] = Field(default_factory=list, description="Optional breadcrumb trail for navigation")


class WikiSetPlan(BaseModel):
    name: str = Field(description="Wiki set name")
    purpose: str = Field(description="What this wiki set is for")
    pages: list[str] = Field(default_factory=list, description="Canonical page names in this set")


class AnalysisPlan(BaseModel):
    corpus_summary: str = Field(default="", description="High-level summary of the corpus")
    corpus_kinds: list[str] = Field(default_factory=list, description="Detected corpus buckets such as bills and whatsapp")
    wiki_sets: list[WikiSetPlan] = Field(default_factory=list)
    source_page_candidates: list[SourcePagePlan] = Field(default_factory=list)
    topic_clusters: list[str] = Field(default_factory=list, description="Detected topic clusters across the corpus")
    entity_clusters: list[str] = Field(default_factory=list, description="Detected entity clusters across the corpus")
    duplicate_clusters: list[str] = Field(default_factory=list)
    contradiction_clusters: list[str] = Field(default_factory=list)
    reorg_suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GenerationPlan(BaseModel):
    wiki_set_pages: list[WikiSetPlan] = Field(default_factory=list)
    source_pages: list[SourcePagePlan] = Field(default_factory=list)
    root_index_summary: str = Field(default="")
    dashboard_summary: str = Field(default="", description="High-level corpus dashboard summary")
    stats_summary: str = Field(default="", description="Corpus stats summary")
    needed_followups: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class VerificationFinding(BaseModel):
    severity: str = Field(description="low|medium|high")
    message: str = Field(description="What is wrong or uncertain")
    source_path: str = Field(default="", description="Optional source path tied to the finding")


class VerificationPlan(BaseModel):
    approved: bool = Field(description="True if the generated plan is acceptable")
    findings: list[VerificationFinding] = Field(default_factory=list)
    changes_requested: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


ALLOWED_PAGE_ROLES = {
    "knowledge_page",
    "thread_page",
    "index_page",
    "ledger_page",
    "duplicate_page",
    "contradiction_page",
}


def _normalise_page_role(value: Any) -> str:
    role = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return role if role in ALLOWED_PAGE_ROLES else ""


def _infer_page_role(item: dict[str, Any]) -> str:
    explicit = _normalise_page_role(item.get("page_role") or item.get("role"))
    if explicit:
        return explicit
    text = " ".join(str(item.get(field) or "") for field in ("path", "title", "source_kind", "summary", "corpus_summary")).lower()
    if any(token in text for token in ("duplicate", "duplication", "mirror", "repeat")):
        return "duplicate_page"
    if any(token in text for token in ("contradiction", "conflict", "inconsistent", "dispute")):
        return "contradiction_page"
    if any(token in text for token in ("index", "table of contents", "toc", "overview")):
        return "index_page"
    if any(token in text for token in ("ledger", "log", "journal", "changelog", "change log")):
        return "ledger_page"
    if any(token in text for token in ("thread", "conversation", "chat", "message", "discussion")):
        return "thread_page"
    return "knowledge_page"


def _coerce_source_page_plan(page: SourcePagePlan | dict[str, Any]) -> SourcePagePlan:
    data = page.model_dump() if isinstance(page, SourcePagePlan) else dict(page)
    data["page_role"] = _normalise_page_role(data.get("page_role")) or _infer_page_role(data)
    return SourcePagePlan(**data)


def _canonical_corpus_kind(value: str) -> str:
    lowered = str(value or "").strip().lower().replace("/", "_").replace("-", "_")
    if any(token in lowered for token in ("invoice", "bill", "receipt", "statement", "document")):
        return "bills_documents"
    if any(token in lowered for token in ("whatsapp", "chat", "conversation", "thread", "message")):
        return "chats"
    if any(token in lowered for token in ("project", "task", "issue", "roadmap", "spec", "milestone", "artifact")):
        return "project_artifacts"
    if any(token in lowered for token in ("index", "ledger", "journal", "log", "toc")):
        return "index_ledger_pages"
    if lowered in {"mixed_notes", "notes", "note", "mixed note"}:
        return "mixed_notes"
    return lowered or "mixed_notes"


def _corpus_kind_guidance(corpus_kinds: list[str]) -> str:
    guidance_map = {
        "chats": "Chats: capture participants, thread structure, decisions, unresolved questions, and recurring entities.",
        "bills_documents": "Bills/documents: capture dates, amounts, vendors, document type, reference numbers, and any ambiguous totals.",
        "mixed_notes": "Mixed notes: group by topic, keep the source page's note-taking role explicit, and avoid over-merging unrelated notes.",
        "project_artifacts": "Project artifacts: identify task names, milestones, solution paths, blockers, and deliverables.",
        "index_ledger_pages": "Index/ledger pages: summarize structure, navigation role, coverage, and update history.",
    }
    ordered: list[str] = []
    for kind in corpus_kinds:
        canonical = _canonical_corpus_kind(kind)
        if canonical not in ordered:
            ordered.append(canonical)
    if not ordered:
        ordered = ["mixed_notes"]
    lines = ["Corpus-kind instructions:"]
    for kind in ordered:
        lines.append(f"- {guidance_map.get(kind, f'{kind}: preserve provenance and separate it from unrelated families.')}")
    return "\n".join(lines)


def _boolish(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _compact_scan_for_prompt(scan: dict[str, Any], diff: dict[str, list[str]], *, limit: int = 30) -> dict[str, Any]:
    files = scan.get("files", {})
    compact_files: list[dict[str, Any]] = []
    seen_kinds: list[str] = []
    for path in sorted(files)[:limit]:
        record = files[path]
        source_kind = str(record.get("source_kind") or "").strip()
        corpus_kind = _canonical_corpus_kind(record.get("corpus_kind") or source_kind)
        if corpus_kind and corpus_kind not in seen_kinds:
            seen_kinds.append(corpus_kind)
        compact_files.append(
            {
                "path": path,
                "title": record.get("title"),
                "sha256": record.get("sha256"),
                "headings": record.get("headings", [])[:8],
                "source_links": record.get("source_links", [])[:8],
                "size": record.get("size"),
                "line_count": record.get("line_count"),
                "source_kind": source_kind,
                "corpus_kind": corpus_kind,
            }
        )

    def _trim_list(values: list[str], max_items: int = 25) -> dict[str, Any]:
        return {"count": len(values), "items": values[:max_items]}

    return {
        "corpus_root": scan.get("corpus_root"),
        "file_count": len(files),
        "sample_limit": limit,
        "corpus_kinds": [item for item in dict.fromkeys([str(kind).strip() for kind in (scan.get("corpus_kinds") or seen_kinds) if str(kind).strip()])],
        "sample_files": compact_files,
        "diff": {
            "added": _trim_list(diff.get("added", [])),
            "changed": _trim_list(diff.get("changed", [])),
            "removed": _trim_list(diff.get("removed", [])),
            "unchanged": _trim_list(diff.get("unchanged", [])),
        },
    }


def _require_local_llm_config(config: dict[str, Any]) -> tuple[str, str, str]:
    provider = str(config.get("provider", "ollama") or "").strip().lower()
    base_url = str(config.get("openai_base_url", "") or os.environ.get("OPENAI_BASE_URL", "")).strip().rstrip("/")
    api_key = str(
        config.get("api_key", "")
        or os.environ.get("OPENAI_API_KEY", "")
        or os.environ.get("OSAURUS_API_KEY", "")
        or ""
    ).strip()
    if provider not in {"ollama", "osaurus", "openai-compatible", "openai"}:
        raise RuntimeError(f"Unsupported provider '{provider}'. Use ollama or openai-compatible.")
    if not base_url:
        raise RuntimeError("Missing OPENAI_BASE_URL. Set it in /Users/enkay/dev/wikimaker/.env.")
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip()
    if not host.startswith("192.168.86."):
        raise RuntimeError(
            f"Refusing non-local LLM endpoint '{base_url}'. WikiMaker real-corpus runs are restricted to the 192.168.86.* Ollama server."
        )
    if provider != "ollama" and not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY or OSAURUS_API_KEY in /Users/enkay/dev/wikimaker/.env.")
    return provider, base_url, api_key


def _chat_completions(provider: str, base_url: str, api_key: str, model: str, messages: list[dict[str, Any]], *, temperature: float = 0.2) -> str:
    if provider == "ollama":
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        }
        endpoint = f"{base_url}/api/chat"
    else:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        endpoint = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    http_timeout = 600 if provider == "ollama" else 180
    try:
        with urlopen(request, timeout=http_timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"OpenAI-compatible request failed: HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc

    data = json.loads(raw)
    if provider == "ollama":
        message = data.get("message") or {}
        content = message.get("content")
    else:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI-compatible response missing choices: {raw[:500]}")
        message = choices[0].get("message") or {}
        content = message.get("content")
    if not content:
        raise RuntimeError(f"OpenAI-compatible response missing message content: {raw[:500]}")
    return str(content)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def _parse_model_output(text: str, model_cls: type[T]) -> T:
    cleaned = _strip_code_fences(text)
    try:
        return model_cls.model_validate_json(cleaned)
    except Exception as exc:
        raise RuntimeError(f"Model response was not valid JSON for {model_cls.__name__}: {cleaned[:1000]}") from exc


def _analysis_prompt(scan_prompt: dict[str, Any]) -> str:
    corpus_kinds = [str(item) for item in scan_prompt.get("corpus_kinds", []) if item]
    return (
        "Stage 1: generate individual source-page plans for each Markdown file. "
        "Return strict JSON only. Infer the corpus kinds present, and classify every page with an explicit page_role using only knowledge_page, thread_page, index_page, ledger_page, duplicate_page, or contradiction_page. "
        "Capture the source page title, summary, platform, source kind, corpus kind, timestamps, links, tags, topics, entities, snippets, what higher-level pages may use it later, and a brief corpus summary. "
        "Preserve provenance and keep the output compact.\n\n"
        f"Detected corpus kinds: {', '.join(corpus_kinds) if corpus_kinds else 'mixed_notes'}\n\n"
        f"{_corpus_kind_guidance(corpus_kinds)}\n\n"
        f"SCAN_JSON:\n{json.dumps(scan_prompt, indent=2, sort_keys=True)}"
    )


def _generation_prompt(scan_prompt: dict[str, Any], analysis: AnalysisPlan) -> str:
    corpus_kinds = [str(item) for item in analysis.corpus_kinds or scan_prompt.get("corpus_kinds", []) if item]
    return (
        "Stage 2: identify commonality across the source pages and update the source-page plans with new insights. Return strict JSON only. "
        "Cluster related source pages into wiki sets, separate distinct corpora when needed, identify duplicates, contradictions, and evolving topics, propose wiki-set page names, draft concise root-index, dashboard, and stats summaries, and fill each source page's used-in links when relevant. "
        "Preserve backlinks, page roles, and evidence, and keep page_role assignments stable unless a page clearly changes role. "
        "Keep chats, bills/documents, mixed notes, project artifacts, and index/ledger pages separated when they would otherwise blur together.\n\n"
        f"Detected corpus kinds: {', '.join(corpus_kinds) if corpus_kinds else 'mixed_notes'}\n\n"
        f"{_corpus_kind_guidance(corpus_kinds)}\n\n"
        f"SCAN_JSON:\n{json.dumps(scan_prompt, indent=2, sort_keys=True)}\n\n"
        f"ANALYSIS_JSON:\n{json.dumps(analysis.model_dump(), indent=2, sort_keys=True)}"
    )


def _verification_prompt(scan_prompt: dict[str, Any], analysis: AnalysisPlan, generation: GenerationPlan) -> str:
    corpus_kinds = [str(item) for item in analysis.corpus_kinds or scan_prompt.get("corpus_kinds", []) if item]
    return (
        "Stage 3: update and synthesize the wiki from the discovered commonality. Return strict JSON only. "
        "Check whether the source-page plans and wiki-set plans preserve provenance, backlinks, duplicates, evolution, contradictions, local-only model assumptions, and corpus-aware branching. "
        "Flag unsupported claims, missing backlinks, missed files, or risky reorganization suggestions.\n\n"
        f"Detected corpus kinds: {', '.join(corpus_kinds) if corpus_kinds else 'mixed_notes'}\n\n"
        f"{_corpus_kind_guidance(corpus_kinds)}\n\n"
        f"SCAN_JSON:\n{json.dumps(scan_prompt, indent=2, sort_keys=True)}\n\n"
        f"ANALYSIS_JSON:\n{json.dumps(analysis.model_dump(), indent=2, sort_keys=True)}\n\n"
        f"GENERATION_JSON:\n{json.dumps(generation.model_dump(), indent=2, sort_keys=True)}"
    )


def run_pipeline(scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any]) -> dict[str, Any]:
    """Run WikiMaker through a local OpenAI-compatible inference server only."""

    provider, base_url, api_key = _require_local_llm_config(config)
    sample_files = int(config.get("sample_files", 5) or 5)
    analysis_model = str(config.get("analysis_model") or "").strip()
    generation_model = str(config.get("generation_model") or analysis_model).strip()
    review_model = str(config.get("review_model") or analysis_model).strip()
    if not analysis_model:
        raise RuntimeError("Missing WIKIMAKER_ANALYSIS_MODEL in /Users/enkay/dev/wikimaker/.env.")
    if not generation_model:
        raise RuntimeError("Missing WIKIMAKER_GENERATION_MODEL in /Users/enkay/dev/wikimaker/.env.")
    if not review_model:
        raise RuntimeError("Missing WIKIMAKER_REVIEW_MODEL in /Users/enkay/dev/wikimaker/.env.")

    scan_prompt = _compact_scan_for_prompt(scan, diff, limit=sample_files)
    errors: list[str] = []

    analysis_text = _chat_completions(
        provider,
        base_url,
        api_key,
        analysis_model,
        [
            {"role": "system", "content": "You are WikiMaker's analysis pass."},
            {"role": "user", "content": _analysis_prompt(scan_prompt)},
        ],
    )
    try:
        analysis_result = _parse_model_output(analysis_text, AnalysisPlan)
    except RuntimeError:
        raw_analysis: Any = {}
        try:
            raw_analysis = json.loads(analysis_text)
        except Exception:
            raw_analysis = {}
        if isinstance(raw_analysis, list):
            items = [item for item in raw_analysis if isinstance(item, dict)]
        elif isinstance(raw_analysis, dict):
            items = [raw_analysis]
        else:
            items = []
        source_pages: list[SourcePagePlan] = []
        seen_kinds: list[str] = []
        for idx, item in enumerate(items[:100]):
            source_kind = str(item.get("source_kind") or "").strip()
            if source_kind and source_kind not in seen_kinds:
                seen_kinds.append(source_kind)
            timestamp_value = ""
            timestamps = item.get("timestamps")
            if isinstance(timestamps, dict):
                timestamp_value = str(timestamps.get("date") or timestamps.get("timestamp") or "")
            snippets = item.get("snippets")
            key_snippets = [str(snippet) for snippet in snippets if snippet] if isinstance(snippets, list) else []
            links = item.get("links")
            external_links = [str(link) for link in links if link] if isinstance(links, list) else []
            role = _infer_page_role(item)
            source_pages.append(
                SourcePagePlan(
                    path=str(item.get("path") or item.get("source_page_title") or f"analysis-item-{idx + 1}"),
                    title=str(item.get("source_page_title") or item.get("title") or f"Source {idx + 1}"),
                    page_role=role,
                    summary=str(item.get("summary") or item.get("corpus_summary") or ""),
                    platform=str(item.get("platform") or ""),
                    source_kind=source_kind,
                    extracted_at=timestamp_value,
                    source_url=str(item.get("source_url") or ""),
                    source_paths=[],
                    external_links=external_links,
                    tags=[str(tag) for tag in (item.get("tags") or []) if tag] if isinstance(item.get("tags"), list) else [],
                    related_pages=[],
                    used_in=[],
                    key_snippets=key_snippets,
                )
            )
        wiki_sets = [
            WikiSetPlan(
                name=kind or "Primary set",
                purpose=f"Corpus bucket for {kind or 'the source documents'}",
                pages=[page.title for page in source_pages if page.source_kind == kind][:25],
            )
            for kind in (seen_kinds or ["Primary set"])
        ]
        analysis_result = AnalysisPlan(
            corpus_summary=str(
                (raw_analysis[0].get("corpus_summary") if isinstance(raw_analysis, list) and raw_analysis and isinstance(raw_analysis[0], dict) else "")
                or (raw_analysis.get("corpus_summary") if isinstance(raw_analysis, dict) else "")
                or "Local Ollama fallback analysis."
            ),
            corpus_kinds=seen_kinds,
            wiki_sets=wiki_sets,
            source_page_candidates=source_pages,
            topic_clusters=[str(item.get("topic") or item.get("topic_cluster") or "") for item in items if isinstance(item, dict) and (item.get("topic") or item.get("topic_cluster"))],
            entity_clusters=[str(item.get("entity") or item.get("entity_cluster") or "") for item in items if isinstance(item, dict) and (item.get("entity") or item.get("entity_cluster"))],
            duplicate_clusters=[],
            contradiction_clusters=[],
            reorg_suggestions=[],
            confidence=0.25,
        )
        errors.append("analysis output did not match schema; used fallback synthesis")

    analysis_result = AnalysisPlan(
        **{
            **analysis_result.model_dump(),
            "source_page_candidates": [_coerce_source_page_plan(page) for page in analysis_result.source_page_candidates],
        }
    )

    generation_text = _chat_completions(
        provider,
        base_url,
        api_key,
        generation_model,
        [
            {"role": "system", "content": "You are WikiMaker's generation pass."},
            {"role": "user", "content": _generation_prompt(scan_prompt, analysis_result)},
        ],
    )
    try:
        generation_result = _parse_model_output(generation_text, GenerationPlan)
    except RuntimeError:
        raw_generation: dict[str, Any] = {}
        try:
            parsed = json.loads(generation_text)
            if isinstance(parsed, dict):
                raw_generation = parsed
        except Exception:
            raw_generation = {}
        summary = raw_generation.get("analysis_summary", {}) if isinstance(raw_generation.get("analysis_summary"), dict) else {}
        generation_result = GenerationPlan(
            wiki_set_pages=[WikiSetPlan(**wiki_set.model_dump()) for wiki_set in analysis_result.wiki_sets],
            source_pages=list(analysis_result.source_page_candidates),
            root_index_summary=str(summary.get("corpus_summary") or raw_generation.get("root_index_summary") or analysis_result.corpus_summary or ""),
            dashboard_summary=str(raw_generation.get("dashboard_summary") or analysis_result.corpus_summary or ""),
            stats_summary=str(raw_generation.get("stats_summary") or ""),
            needed_followups=[str(item) for item in raw_generation.get("reorg_suggestions", []) if item],
            confidence=float(summary.get("confidence", analysis_result.confidence) or analysis_result.confidence),
        )
        errors.append("generation output did not match schema; used fallback synthesis")

    generation_result = GenerationPlan(
        **{
            **generation_result.model_dump(),
            "source_pages": [_coerce_source_page_plan(page) for page in generation_result.source_pages],
        }
    )

    verification_text = _chat_completions(
        provider,
        base_url,
        api_key,
        review_model,
        [
            {"role": "system", "content": "You are WikiMaker's verification pass."},
            {"role": "user", "content": _verification_prompt(scan_prompt, analysis_result, generation_result)},
        ],
    )
    try:
        verification_result = _parse_model_output(verification_text, VerificationPlan)
    except RuntimeError:
        verification_result = VerificationPlan(
            approved=False,
            findings=[VerificationFinding(severity="medium", message="Model output did not match expected verification schema.")],
            changes_requested=["Review model prompts or backend compatibility."],
            confidence=0.0,
        )
        errors.append("verification output did not match schema; used fallback")

    return {
        "llm_used": True,
        "provider": str(config.get("provider", "ollama")),
        "base_url": base_url,
        "errors": errors,
        "analysis": analysis_result.model_dump(),
        "generation": generation_result.model_dump(),
        "verification": verification_result.model_dump(),
        "sample_files": sample_files,
    }
