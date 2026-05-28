from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel, Field

from wikimaker_openai import _chat_completions, _parse_model_output, _require_local_llm_config
from wikimaker_state import hash_text


CARD_SCHEMA_VERSION = "card.v1"
CARD_PROMPT_VERSION = "card_prompt.v1"
BATCH_PROMPT_VERSION = "batch_prompt.v1"
GLOBAL_PROMPT_VERSION = "global_prompt.v1"
CARD_INDEX_FILENAME = "card_index.json"


class FileAnalysisCard(BaseModel):
    path: str
    title: str = ""
    page_role: str = "knowledge_page"
    summary: str = ""
    source_kind: str = ""
    corpus_kind: str = "mixed_notes"
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    candidate_links: list[str] = Field(default_factory=list)
    source_quality: str = "ok"
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class BatchSynthesis(BaseModel):
    name: str = ""
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    wiki_sets: list[str] = Field(default_factory=list)
    duplicate_hints: list[str] = Field(default_factory=list)
    contradiction_hints: list[str] = Field(default_factory=list)
    link_hints: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class GlobalSynthesis(BaseModel):
    corpus_summary: str = ""
    root_index_summary: str = ""
    dashboard_summary: str = ""
    stats_summary: str = ""
    wiki_sets: list[dict[str, Any]] = Field(default_factory=list)
    topic_clusters: list[str] = Field(default_factory=list)
    entity_clusters: list[str] = Field(default_factory=list)
    duplicate_clusters: list[str] = Field(default_factory=list)
    contradiction_clusters: list[str] = Field(default_factory=list)
    confidence: float = 0.5


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip().lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned[:80] or 'item'}-{digest}"


def _profile_hash(record: dict[str, Any]) -> str:
    profile = record.get("prompt_profile") or {}
    return hash_text(json.dumps(profile, sort_keys=True, default=str))


def _card_signature(rel_path: str, record: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": rel_path,
        "source_sha256": record.get("sha256", ""),
        "schema_version": CARD_SCHEMA_VERSION,
        "prompt_version": CARD_PROMPT_VERSION,
        "provider": config.get("provider", "ollama"),
        "model": config.get("analysis_model", ""),
        "profile_hash": _profile_hash(record),
    }


def _card_path(state_root: Path, rel_path: str) -> Path:
    return state_root / "cards" / f"{_safe_id(rel_path)}.json"


def _read_card(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_card(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _matches_force_path(rel_path: str, patterns: list[str]) -> bool:
    return any(rel_path == pattern or fnmatch(rel_path, pattern) for pattern in patterns)


def _fallback_card(rel_path: str, record: dict[str, Any], *, reason: str = "") -> FileAnalysisCard:
    title = str(record.get("title") or Path(rel_path).stem)
    corpus_kind = str(record.get("corpus_kind") or record.get("source_kind") or "mixed_notes")
    headings = [str(item).lstrip("#").strip() for item in (record.get("headings") or [])[:4] if str(item).strip()]
    topics = [corpus_kind.replace("_", " ").title()]
    topics.extend(item for item in headings if item not in topics)
    warnings = [reason] if reason else []
    source_quality = "llm_failed" if reason else "scan_fallback"
    return FileAnalysisCard(
        path=rel_path,
        title=title,
        page_role="thread_page" if "chat" in corpus_kind else "knowledge_page",
        summary=f"{title}. Source file classified as {corpus_kind.replace('_', ' ')}.",
        source_kind=str(record.get("source_kind") or corpus_kind),
        corpus_kind=corpus_kind,
        topics=topics[:8],
        entities=[],
        dates=[str(record.get("extracted_at"))] if record.get("extracted_at") else [],
        amounts=[],
        candidate_links=[],
        source_quality=source_quality,
        warnings=warnings,
        confidence=0.0 if reason else 0.35,
    )


def _file_prompt(rel_path: str, record: dict[str, Any], text: str) -> str:
    compact = {
        "path": rel_path,
        "title": record.get("title"),
        "sha256": record.get("sha256"),
        "source_kind": record.get("source_kind"),
        "corpus_kind": record.get("corpus_kind"),
        "headings": (record.get("headings") or [])[:20],
        "source_links": (record.get("source_links") or [])[:20],
        "prompt_profile": record.get("prompt_profile") or {},
    }
    return (
        "Analyze exactly one Markdown source file for WikiMaker. Return strict JSON matching this shape: "
        "path, title, page_role, summary, source_kind, corpus_kind, topics, entities, dates, amounts, "
        "candidate_links, source_quality, warnings, confidence. Keep it compact and provenance-first.\n\n"
        f"SCAN_METADATA_JSON:\n{json.dumps(compact, indent=2, sort_keys=True)}\n\n"
        f"SOURCE_MARKDOWN_EXCERPT:\n{text[:12000]}"
    )


def _load_source_excerpt(corpus_root: Path, rel_path: str) -> str:
    try:
        return (corpus_root / rel_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _card_from_llm(provider: str, base_url: str, api_key: str, model: str, corpus_root: Path, rel_path: str, record: dict[str, Any]) -> FileAnalysisCard:
    text = _load_source_excerpt(corpus_root, rel_path)
    response = _chat_completions(
        provider,
        base_url,
        api_key,
        model,
        [
            {"role": "system", "content": "You create one durable WikiMaker source card from one file."},
            {"role": "user", "content": _file_prompt(rel_path, record, text)},
        ],
        temperature=0.0,
    )
    card = _parse_model_output(response, FileAnalysisCard)
    data = card.model_dump()
    data["path"] = rel_path
    data["title"] = data.get("title") or record.get("title") or Path(rel_path).stem
    data["source_kind"] = data.get("source_kind") or record.get("source_kind") or record.get("corpus_kind") or ""
    data["corpus_kind"] = data.get("corpus_kind") or record.get("corpus_kind") or "mixed_notes"
    return FileAnalysisCard(**data)


def _stored_card(signature: dict[str, Any], card: FileAnalysisCard, *, status: str, duration_ms: int, error: str = "") -> dict[str, Any]:
    return {
        "signature": signature,
        "card": card.model_dump(),
        "cache_status": status,
        "generated_at": _utc_now(),
        "duration_ms": duration_ms,
        "error": error,
    }


def build_file_cards(scan: dict[str, Any], config: dict[str, Any], diff: dict[str, list[str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider, base_url, api_key = _require_local_llm_config(config)
    model = str(config.get("analysis_model") or "").strip()
    corpus_root = Path(str(scan.get("corpus_root") or config.get("corpus_root") or "."))
    state_root = Path(str(config.get("state_root") or "."))
    force_all = bool(config.get("force_reprocess"))
    force_patterns = [str(item).strip() for item in (config.get("force_paths") or []) if str(item).strip()]
    files = scan.get("files", {})
    cards: list[dict[str, Any]] = []
    index: dict[str, Any] = {"generated_at": _utc_now(), "cards": {}}
    counts = {"hits": 0, "misses": 0, "forced": 0, "failed": 0}

    for rel_path, record in sorted(files.items()):
        if not isinstance(record, dict) or record.get("error"):
            continue
        signature = _card_signature(rel_path, record, config)
        cache_path = _card_path(state_root, rel_path)
        cached = _read_card(cache_path)
        forced = force_all or _matches_force_path(rel_path, force_patterns)
        if cached and cached.get("signature") == signature and not forced:
            cached["cache_status"] = "hit"
            cards.append(cached)
            counts["hits"] += 1
        else:
            started = time.monotonic()
            status = "forced" if forced else "miss"
            error = ""
            try:
                card = _card_from_llm(provider, base_url, api_key, model, corpus_root, rel_path, record)
            except Exception as exc:
                error = str(exc)
                card = _fallback_card(rel_path, record, reason=error)
                counts["failed"] += 1
            duration_ms = int((time.monotonic() - started) * 1000)
            stored = _stored_card(signature, card, status=status, duration_ms=duration_ms, error=error)
            _write_card(cache_path, stored)
            cards.append(stored)
            if forced:
                counts["forced"] += 1
            else:
                counts["misses"] += 1
        index["cards"][rel_path] = {
            "cache_file": str(Path("cards") / cache_path.name),
            "valid": True,
            "source_sha256": signature["source_sha256"],
            "schema_version": CARD_SCHEMA_VERSION,
            "prompt_version": CARD_PROMPT_VERSION,
            "model": model,
            "cache_status": cards[-1].get("cache_status"),
        }
    index_path = state_root / CARD_INDEX_FILENAME
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    stage = {
        "card_schema_version": CARD_SCHEMA_VERSION,
        "card_prompt_version": CARD_PROMPT_VERSION,
        "batch_prompt_version": BATCH_PROMPT_VERSION,
        "global_prompt_version": GLOBAL_PROMPT_VERSION,
        "model": model,
        "card_index": str(index_path),
        "counts": counts,
        "diff": {
            "added": len(diff.get("added", [])),
            "changed": len(diff.get("changed", [])),
            "unchanged": len(diff.get("unchanged", [])),
            "removed": len(diff.get("removed", [])),
        },
    }
    return cards, stage


def _card_public(card_payload: dict[str, Any]) -> dict[str, Any]:
    card = dict(card_payload.get("card") or {})
    signature = dict(card_payload.get("signature") or {})
    return {
        "path": card.get("path"),
        "title": card.get("title"),
        "summary": card.get("summary"),
        "page_role": card.get("page_role"),
        "source_kind": card.get("source_kind"),
        "corpus_kind": card.get("corpus_kind"),
        "topics": card.get("topics", []),
        "entities": card.get("entities", []),
        "dates": card.get("dates", []),
        "amounts": card.get("amounts", []),
        "candidate_links": card.get("candidate_links", []),
        "source_quality": card.get("source_quality"),
        "warnings": card.get("warnings", []),
        "confidence": card.get("confidence"),
        "cache_status": card_payload.get("cache_status"),
        "source_sha256": signature.get("source_sha256"),
    }


def _chunks(cards: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [cards[index:index + size] for index in range(0, len(cards), size)]


def _batch_prompt(batch: list[dict[str, Any]], index: int) -> str:
    cards = [_card_public(item) for item in batch]
    return (
        "Analyze this batch of WikiMaker source cards. Do not ask for raw source text. Return strict JSON with "
        "name, summary, topics, entities, wiki_sets, duplicate_hints, contradiction_hints, link_hints, confidence.\n\n"
        f"BATCH_INDEX: {index}\nCARDS_JSON:\n{json.dumps(cards, indent=2, sort_keys=True)}"
    )


def _fallback_batch(batch: list[dict[str, Any]], index: int, reason: str = "") -> BatchSynthesis:
    topics: list[str] = []
    entities: list[str] = []
    kinds: list[str] = []
    for payload in batch:
        card = payload.get("card") or {}
        topics.extend(str(item) for item in card.get("topics", []) if str(item).strip())
        entities.extend(str(item) for item in card.get("entities", []) if str(item).strip())
        kind = str(card.get("corpus_kind") or "").strip()
        if kind:
            kinds.append(kind.replace("_", " ").title())
    unique_topics = list(dict.fromkeys(topics))[:20]
    unique_entities = list(dict.fromkeys(entities))[:20]
    unique_kinds = list(dict.fromkeys(kinds)) or ["Mixed Notes"]
    return BatchSynthesis(
        name=f"Batch {index}",
        summary=f"Scan-derived batch summary for {len(batch)} source cards." + (f" LLM issue: {reason[:160]}" if reason else ""),
        topics=unique_topics,
        entities=unique_entities,
        wiki_sets=[f"{kind} Sources" for kind in unique_kinds],
        confidence=0.25,
    )


def build_batch_summaries(cards: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    provider, base_url, api_key = _require_local_llm_config(config)
    model = str(config.get("generation_model") or config.get("analysis_model") or "").strip()
    batch_size = int(config.get("llm_batch_size", 50) or 50)
    batches: list[dict[str, Any]] = []
    failed = 0
    for index, batch in enumerate(_chunks(cards, batch_size), start=1):
        error = ""
        try:
            text = _chat_completions(
                provider,
                base_url,
                api_key,
                model,
                [
                    {"role": "system", "content": "You merge WikiMaker source cards into one batch summary."},
                    {"role": "user", "content": _batch_prompt(batch, index)},
                ],
                temperature=0.0,
            )
            synthesis = _parse_model_output(text, BatchSynthesis)
        except Exception as exc:
            error = str(exc)
            failed += 1
            synthesis = _fallback_batch(batch, index, reason=error)
        batches.append(
            {
                "index": index,
                "input_card_count": len(batch),
                "synthesis": synthesis.model_dump(),
                "error": error,
            }
        )
    return batches, {"batch_count": len(batches), "batch_size": batch_size, "failed_batches": failed, "model": model}


def _global_prompt(batches: list[dict[str, Any]]) -> str:
    summaries = [
        {
            "index": item.get("index"),
            "input_card_count": item.get("input_card_count"),
            **dict(item.get("synthesis") or {}),
        }
        for item in batches
    ]
    return (
        "Merge WikiMaker batch summaries into a corpus-level wiki plan. Use only these summaries. Return strict JSON with "
        "corpus_summary, root_index_summary, dashboard_summary, stats_summary, wiki_sets, topic_clusters, "
        "entity_clusters, duplicate_clusters, contradiction_clusters, confidence.\n\n"
        f"BATCH_SUMMARIES_JSON:\n{json.dumps(summaries, indent=2, sort_keys=True)}"
    )


def _fallback_global(cards: list[dict[str, Any]], batches: list[dict[str, Any]], reason: str = "") -> GlobalSynthesis:
    topics: list[str] = []
    entities: list[str] = []
    kinds: dict[str, list[str]] = {}
    for payload in cards:
        card = payload.get("card") or {}
        title = str(card.get("title") or card.get("path") or "").strip()
        kind = str(card.get("corpus_kind") or "mixed_notes").strip()
        kinds.setdefault(kind, [])
        if title:
            kinds[kind].append(title)
        topics.extend(str(item) for item in card.get("topics", []) if str(item).strip())
        entities.extend(str(item) for item in card.get("entities", []) if str(item).strip())
    wiki_sets = [
        {
            "name": f"{kind.replace('_', ' ').title()} Sources",
            "purpose": f"Source cards grouped by {kind.replace('_', ' ')}.",
            "pages": pages[:250],
        }
        for kind, pages in sorted(kinds.items())
    ]
    summary = f"Compiled {len(cards)} source cards across {len(kinds)} corpus families and {len(batches)} batches."
    if reason:
        summary += " Global LLM merge used deterministic fallback."
    return GlobalSynthesis(
        corpus_summary=summary,
        root_index_summary=summary,
        dashboard_summary=summary,
        stats_summary=f"{len(cards)} source cards, {len(wiki_sets)} wiki sets, {len(batches)} batches.",
        wiki_sets=wiki_sets,
        topic_clusters=list(dict.fromkeys(topics))[:100],
        entity_clusters=list(dict.fromkeys(entities))[:100],
        confidence=0.35,
    )


def build_global_synthesis(cards: list[dict[str, Any]], batches: list[dict[str, Any]], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    provider, base_url, api_key = _require_local_llm_config(config)
    model = str(config.get("generation_model") or config.get("analysis_model") or "").strip()
    error = ""
    try:
        text = _chat_completions(
            provider,
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": "You merge WikiMaker batch summaries into a corpus-level wiki plan."},
                {"role": "user", "content": _global_prompt(batches)},
            ],
            temperature=0.0,
        )
        global_plan = _parse_model_output(text, GlobalSynthesis)
    except Exception as exc:
        error = str(exc)
        global_plan = _fallback_global(cards, batches, reason=error)
    return global_plan.model_dump(), {"status": "fallback" if error else "ok", "error": error, "model": model}


def pipeline_from_cards(scan: dict[str, Any], cards: list[dict[str, Any]], batches: list[dict[str, Any]], global_plan: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    source_pages = []
    for payload in cards:
        card = dict(payload.get("card") or {})
        signature = dict(payload.get("signature") or {})
        rel_path = str(card.get("path") or "")
        source_pages.append(
            {
                "path": rel_path,
                "title": card.get("title") or Path(rel_path).stem,
                "page_role": card.get("page_role") or "knowledge_page",
                "summary": card.get("summary") or "",
                "platform": "",
                "source_kind": card.get("source_kind") or card.get("corpus_kind") or "",
                "corpus_kind": card.get("corpus_kind") or "mixed_notes",
                "extracted_at": "",
                "source_url": "",
                "source_paths": [rel_path] if rel_path else [],
                "external_links": [],
                "tags": [card.get("corpus_kind")] if card.get("corpus_kind") else [],
                "topics": card.get("topics", []),
                "entities": card.get("entities", []),
                "related_pages": card.get("candidate_links", []),
                "used_in": [],
                "key_snippets": [],
                "breadcrumbs": list(Path(rel_path).parts[:-1]) if rel_path else [],
                "build": {
                    "run_id": stage.get("run_id", ""),
                    "source_sha256": signature.get("source_sha256", ""),
                    "cache_status": payload.get("cache_status", ""),
                    "card_schema_version": CARD_SCHEMA_VERSION,
                    "prompt_version": CARD_PROMPT_VERSION,
                    "model": signature.get("model", ""),
                    "synthesis_stage": "per_file_card",
                    "input_card_count": 1,
                    "confidence": card.get("confidence", 0.0),
                    "warnings": card.get("warnings", []),
                },
            }
        )
    pipeline = {
        "llm_used": True,
        "provider": "map_reduce",
        "base_url": "",
        "errors": [item.get("error") for item in batches if item.get("error")],
        "analysis": {
            "corpus_summary": global_plan.get("corpus_summary", ""),
            "corpus_kinds": scan.get("corpus_kinds", []),
            "wiki_sets": global_plan.get("wiki_sets", []),
            "source_page_candidates": source_pages,
            "topic_clusters": global_plan.get("topic_clusters", []),
            "entity_clusters": global_plan.get("entity_clusters", []),
            "duplicate_clusters": global_plan.get("duplicate_clusters", []),
            "contradiction_clusters": global_plan.get("contradiction_clusters", []),
            "reorg_suggestions": [],
            "confidence": global_plan.get("confidence", 0.0),
        },
        "generation": {
            "wiki_set_pages": global_plan.get("wiki_sets", []),
            "source_pages": source_pages,
            "root_index_summary": global_plan.get("root_index_summary", ""),
            "dashboard_summary": global_plan.get("dashboard_summary", ""),
            "stats_summary": global_plan.get("stats_summary", ""),
            "needed_followups": [],
            "confidence": global_plan.get("confidence", 0.0),
        },
        "verification": {"approved": True, "findings": [], "changes_requested": [], "confidence": global_plan.get("confidence", 0.0)},
        "sample_files": len(cards),
        "stage": stage,
        "batches": batches,
    }
    return pipeline


def run_map_reduce_pipeline(scan: dict[str, Any], diff: dict[str, list[str]], config: dict[str, Any]) -> dict[str, Any]:
    run_id = _safe_id(_utc_now())
    cards, card_stage = build_file_cards(scan, config, diff)
    batches, batch_stage = build_batch_summaries(cards, config)
    global_plan, global_stage = build_global_synthesis(cards, batches, config)
    stage = {
        "run_id": run_id,
        "card": card_stage,
        "batch": batch_stage,
        "global": global_stage,
    }
    return pipeline_from_cards(scan, cards, batches, global_plan, stage)
