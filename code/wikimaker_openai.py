from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class SourcePagePlan(BaseModel):
    path: str = Field(description="Relative source file path or stable source identifier")
    title: str = Field(description="Human-readable page title")
    summary: str = Field(description="Short source-summary of what the page contains")
    platform: str = Field(default="", description="Source platform or extractor label, if known")
    source_kind: str = Field(default="", description="Corpus kind such as bills or whatsapp, if known")
    extracted_at: str = Field(default="", description="Known extracted or source timestamp")
    source_url: str = Field(default="", description="Original source URL, if present")
    source_paths: list[str] = Field(default_factory=list, description="Direct source markdown paths used for this page")
    external_links: list[str] = Field(default_factory=list, description="Original URLs or external references")
    tags: list[str] = Field(default_factory=list, description="Broad tags attached to the page")
    related_pages: list[str] = Field(default_factory=list, description="Suggested internal links")
    used_in: list[str] = Field(default_factory=list, description="Higher-level wiki pages that use this source page")
    key_snippets: list[str] = Field(default_factory=list, description="Important quotes or evidence snippets")


class WikiSetPlan(BaseModel):
    name: str = Field(description="Wiki set name")
    purpose: str = Field(description="What this wiki set is for")
    pages: list[str] = Field(default_factory=list, description="Canonical page names in this set")


class AnalysisPlan(BaseModel):
    corpus_summary: str = Field(default="", description="High-level summary of the corpus")
    corpus_kinds: list[str] = Field(default_factory=list, description="Detected corpus buckets such as bills and whatsapp")
    wiki_sets: list[WikiSetPlan] = Field(default_factory=list)
    source_page_candidates: list[SourcePagePlan] = Field(default_factory=list)
    duplicate_clusters: list[str] = Field(default_factory=list)
    contradiction_clusters: list[str] = Field(default_factory=list)
    reorg_suggestions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class GenerationPlan(BaseModel):
    wiki_set_pages: list[WikiSetPlan] = Field(default_factory=list)
    source_pages: list[SourcePagePlan] = Field(default_factory=list)
    root_index_summary: str = Field(default="")
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


def _boolish(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _compact_scan_for_prompt(scan: dict[str, Any], diff: dict[str, list[str]], *, limit: int = 30) -> dict[str, Any]:
    files = scan.get("files", {})
    compact_files: list[dict[str, Any]] = []
    for path in sorted(files)[:limit]:
        record = files[path]
        compact_files.append(
            {
                "path": path,
                "title": record.get("title"),
                "sha256": record.get("sha256"),
                "headings": record.get("headings", [])[:8],
                "source_links": record.get("source_links", [])[:8],
                "size": record.get("size"),
                "line_count": record.get("line_count"),
            }
        )

    def _trim_list(values: list[str], max_items: int = 25) -> dict[str, Any]:
        return {"count": len(values), "items": values[:max_items]}

    return {
        "corpus_root": scan.get("corpus_root"),
        "file_count": len(files),
        "sample_limit": limit,
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
    return (
        "Stage 1: generate individual source-page plans for each Markdown file. "
        "Return strict JSON only. Infer the corpus kinds present (for example, bills and whatsapp), and capture the source page title, summary, platform, source kind, timestamps, links, tags, snippets, what higher-level pages may use it later, and a brief corpus summary. "
        "Preserve provenance and keep the output compact.\n\n"
        f"SCAN_JSON:\n{json.dumps(scan_prompt, indent=2, sort_keys=True)}"
    )


def _generation_prompt(scan_prompt: dict[str, Any], analysis: AnalysisPlan) -> str:
    return (
        "Stage 2: identify commonality across the source pages and update the source-page plans with new insights. Return strict JSON only. "
        "Cluster related source pages into wiki sets, separate distinct corpora when needed (for example, bills vs whatsapp), identify duplicates, contradictions, and evolving topics, propose wiki-set page names, draft a concise root-index summary, and fill each source page's used-in links when relevant. "
        "Preserve backlinks and evidence.\n\n"
        f"SCAN_JSON:\n{json.dumps(scan_prompt, indent=2, sort_keys=True)}\n\n"
        f"ANALYSIS_JSON:\n{json.dumps(analysis.model_dump(), indent=2, sort_keys=True)}"
    )


def _verification_prompt(scan_prompt: dict[str, Any], analysis: AnalysisPlan, generation: GenerationPlan) -> str:
    return (
        "Stage 3: update and synthesize the wiki from the discovered commonality. Return strict JSON only. "
        "Check whether the source-page plans and wiki-set plans preserve provenance, backlinks, duplicates, evolution, contradictions, and local-only model assumptions. "
        "Flag unsupported claims, missing backlinks, missed files, or risky reorganization suggestions.\n\n"
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
            source_pages.append(
                SourcePagePlan(
                    path=str(item.get("path") or item.get("source_page_title") or f"analysis-item-{idx + 1}"),
                    title=str(item.get("source_page_title") or item.get("title") or f"Source {idx + 1}"),
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
            duplicate_clusters=[],
            contradiction_clusters=[],
            reorg_suggestions=[],
            confidence=0.25,
        )
        errors.append("analysis output did not match schema; used fallback synthesis")

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
            needed_followups=[str(item) for item in raw_generation.get("reorg_suggestions", []) if item],
            confidence=float(summary.get("confidence", analysis_result.confidence) or analysis_result.confidence),
        )
        errors.append("generation output did not match schema; used fallback synthesis")

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
