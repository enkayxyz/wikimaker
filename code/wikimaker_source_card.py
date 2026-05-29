from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, Field


SOURCE_CARD_SCHEMA_VERSION = "source_card.v1"
SOURCE_CARD_PROMPT_VERSION = "source_card_prompt.v1"


class SourceCard(BaseModel):
    id: str
    path: str
    title: str = ""
    page_role: str = "knowledge_page"
    summary: str = ""
    source_kind: str = ""
    corpus_kind: str = "mixed_notes"
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    candidate_links: list[str] = Field(default_factory=list)
    source_quality: str = "ok"
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    build: dict[str, Any] = Field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_card_id(rel_path: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", rel_path).strip("._-").replace("/", "__")
    digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]
    if len(cleaned) <= 120:
        return f"{cleaned or 'source'}--{digest}"
    return f"{cleaned[:100].rstrip('._-')}--{digest}"


def source_card_json_name(rel_path: str) -> str:
    return f"{source_card_id(rel_path)}.json"


def source_card_markdown_name(rel_path: str) -> str:
    return f"{source_card_id(rel_path)}.md"


def clean_items(values: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result[:limit]


def kind_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").replace("/", " ").strip().title() or "Mixed Notes"


def extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            if match not in found:
                found.append(match)
    return found[:12]


def extract_amounts(text: str) -> list[str]:
    found: list[str] = []
    for match in re.findall(r"(?<!\w)(?:USD\s*)?\$\s?\d[\d,]*(?:\.\d{2})?", text, flags=re.IGNORECASE):
        cleaned = re.sub(r"\s+", " ", match).strip()
        if cleaned not in found:
            found.append(cleaned)
    return found[:12]


def source_facts_from_record(rel_path: str, record: dict[str, Any], *, sample_text: str = "") -> dict[str, Any]:
    title = str(record.get("title") or Path(rel_path).stem).strip()
    corpus_kind = str(record.get("corpus_kind") or record.get("source_kind") or "mixed_notes").strip() or "mixed_notes"
    headings = [item.lstrip("#").strip() for item in clean_items(record.get("headings"), limit=8)]
    folders = [part for part in Path(rel_path).parts[:-1] if part not in {"", "."}]
    tags = clean_items([corpus_kind, *folders], limit=12)
    topics = clean_items([kind_label(corpus_kind), *[kind_label(part) for part in folders[:3]], *headings[:4]], limit=12)
    text_for_extracts = " ".join([title, " ".join(headings), sample_text[:4000]])
    entities: list[str] = []
    if title.startswith("Chat: "):
        candidate = title.removeprefix("Chat: ").strip()
        if candidate and not candidate.startswith("+"):
            entities.append(candidate)
    return {
        "id": source_card_id(rel_path),
        "path": rel_path,
        "title": title,
        "page_role": "thread_page" if any(token in corpus_kind.lower() for token in ("chat", "conversation", "whatsapp", "imessage")) else "knowledge_page",
        "summary": f"{title}. Headings: {'; '.join(headings[:3])}" if headings else f"{title}. Source file classified as {kind_label(corpus_kind)}.",
        "source_kind": str(record.get("source_kind") or corpus_kind),
        "corpus_kind": corpus_kind,
        "tags": tags,
        "topics": topics,
        "entities": entities,
        "dates": clean_items([str(record.get("extracted_at") or ""), *extract_dates(text_for_extracts)], limit=12),
        "amounts": extract_amounts(text_for_extracts),
        "links": clean_items(record.get("source_links"), limit=20),
        "candidate_links": [],
        "source_quality": "scan_facts",
        "warnings": [],
        "confidence": 0.45,
    }


def source_card_to_source_page(card: SourceCard) -> dict[str, Any]:
    data = card.model_dump()
    return {
        "id": data["id"],
        "path": data["path"],
        "title": data["title"],
        "page_role": data["page_role"],
        "summary": data["summary"],
        "platform": "",
        "source_kind": data["source_kind"],
        "corpus_kind": data["corpus_kind"],
        "extracted_at": (data["dates"][0] if data["dates"] else ""),
        "source_url": "",
        "source_paths": [data["path"]],
        "external_links": data["links"],
        "tags": data["tags"],
        "topics": data["topics"],
        "entities": data["entities"],
        "related_pages": data["candidate_links"],
        "used_in": [],
        "key_snippets": [],
        "breadcrumbs": list(Path(data["path"]).parts[:-1]),
        "build": data["build"],
        "source_page_filename": source_card_markdown_name(data["path"]),
        "card_json_filename": source_card_json_name(data["path"]),
    }


def render_source_card_markdown(card: SourceCard) -> str:
    data = card.model_dump()
    lines = [
        f"# {data['title']}",
        "",
        f"- Card ID: `{data['id']}`",
        f"- Source markdown: `{data['path']}`",
        f"- Corpus kind: `{data['corpus_kind']}`",
        f"- Source kind: `{data['source_kind']}`",
        f"- Page role: `{data['page_role']}`",
        f"- Source quality: `{data['source_quality']}`",
        f"- Confidence: `{data['confidence']}`",
        "",
        "## Summary",
        data["summary"] or "_No summary available._",
        "",
        "## Tags",
    ]
    for field in ("tags", "topics", "entities", "dates", "amounts", "links", "candidate_links", "warnings"):
        if field != "tags":
            lines.extend(["", f"## {field.replace('_', ' ').title()}"])
        values = data.get(field) or []
        lines.extend(f"- {value}" for value in values) if values else lines.append("- _None_")
    build = data.get("build") or {}
    warning_text = ", ".join(str(item) for item in (build.get("warnings") or data.get("warnings") or [])[:3]) or "none"
    lines.extend(
        [
            "",
            "## Build telemetry",
            f"- Run ID: `{build.get('run_id', '')}`",
            f"- Source hash: `{build.get('source_sha256', '')}`",
            f"- Cache status: `{build.get('cache_status', '')}`",
            f"- Card schema: `{build.get('card_schema_version', SOURCE_CARD_SCHEMA_VERSION)}`",
            f"- Prompt version: `{build.get('prompt_version', SOURCE_CARD_PROMPT_VERSION)}`",
            f"- Model: `{build.get('model', '')}`",
            f"- Synthesis stage: `{build.get('synthesis_stage', '')}`",
            f"- Input cards: `{build.get('input_card_count', 1)}`",
            f"- Card mode: `{build.get('card_mode', 'metadata')}`",
            f"- Original source included: `{build.get('original_source_included', False)}`",
            f"- Warnings: `{warning_text}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_source_card_artifacts(state_root: Path, output_root: Path, card: SourceCard, *, write_json: bool = True) -> tuple[Path, Path]:
    json_path = state_root / "cards" / source_card_json_name(card.path)
    md_path = output_root / "sources" / source_card_markdown_name(card.path)
    if write_json:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(card.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_source_card_markdown(card), encoding="utf-8")
    return json_path, md_path
