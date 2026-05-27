from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from wikimaker_state import hash_text

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
TITLE_RE = re.compile(r"^#\s+(.*)$")


def _family_from_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("invoice", "receipt", "bill", "statement", "vendor", "amount due", "subtotal", "total due", "due date")):
        return "bills_documents"
    if any(token in lowered for token in ("whatsapp", "chat", "conversation", "thread", "message", "messages", "speaker:", "am", "pm")):
        return "chats"
    if any(token in lowered for token in ("project", "roadmap", "milestone", "todo", "task", "issue", "spec", "deliverable", "blocker")):
        return "project_artifacts"
    if any(token in lowered for token in ("index", "table of contents", "toc", "ledger", "journal", "changelog", "change log", "log")):
        return "index_ledger_pages"
    return "mixed_notes"


def _infer_corpus_kind(path: Path, title: str, frontmatter: dict[str, Any], headings: list[str], text: str) -> str:
    explicit = str(frontmatter.get("corpus_kind") or frontmatter.get("source_kind") or frontmatter.get("kind") or "").strip().lower()
    if explicit:
        if any(token in explicit for token in ("invoice", "bill", "receipt", "statement", "document")):
            return "bills_documents"
        if any(token in explicit for token in ("whatsapp", "chat", "conversation", "thread", "message")):
            return "chats"
        if any(token in explicit for token in ("project", "task", "issue", "roadmap", "spec", "milestone")):
            return "project_artifacts"
        if any(token in explicit for token in ("index", "ledger", "journal", "log", "toc")):
            return "index_ledger_pages"
        if explicit in {"mixed_notes", "mixed note", "notes", "note"}:
            return "mixed_notes"
    family = _family_from_text(" ".join([str(path), title, " ".join(headings), text[:4000]]))
    return family


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_index = None
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}

    meta: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in lines[1:end_index]:
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_key:
            existing = meta.get(current_key)
            value = line.strip().lstrip("- ").strip().strip('"').strip("'")
            if isinstance(existing, list):
                existing.append(value)
            elif existing not in (None, ""):
                meta[current_key] = [existing, value]
            else:
                meta[current_key] = [value]
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value == "":
            meta[key] = []
        else:
            meta[key] = value
        current_key = key
    return meta


def scan_markdown_file(path: Path, corpus_root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    frontmatter = _parse_frontmatter(text)
    headings: list[str] = []
    title = path.stem
    for line in lines[:250]:
        m = HEADING_RE.match(line.strip())
        if not m:
            continue
        level = len(m.group(1))
        heading_text = m.group(2).strip()
        headings.append(f"{'#' * level} {heading_text}")
        if level == 1 and title == path.stem:
            title = heading_text

    if title == path.stem:
        for line in lines[:20]:
            m = TITLE_RE.match(line.strip())
            if m:
                title = m.group(1).strip()
                break

    if isinstance(frontmatter.get("title"), str) and frontmatter["title"].strip():
        title = str(frontmatter["title"]).strip()

    source_links = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target:
            source_links.append(target)

    for key in ("source", "source_url", "original_url", "url", "chat_url"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            source_links.append(value.strip())

    stat = path.stat()
    corpus_kind = _infer_corpus_kind(path, title, frontmatter, headings, text)
    source_kind = str(frontmatter.get("source_kind") or frontmatter.get("kind") or "").strip()
    return {
        "path": str(path.relative_to(corpus_root)),
        "abs_path": str(path),
        "sha256": hash_text(text),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "line_count": len(lines),
        "title": title,
        "headings": headings[:40],
        "source_links": source_links[:40],
        "frontmatter": frontmatter,
        "source_kind": source_kind,
        "corpus_kind": corpus_kind,
        "platform": str(frontmatter.get("platform") or frontmatter.get("provider") or "").strip(),
        "source_url": str(frontmatter.get("source_url") or frontmatter.get("original_url") or frontmatter.get("url") or "").strip(),
        "extracted_at": str(frontmatter.get("extracted_at") or frontmatter.get("date") or frontmatter.get("created") or "").strip(),
    }


def scan_corpus(corpus_root: Path, *, progress_every: int = 0) -> dict[str, Any]:
    corpus_root = corpus_root.expanduser().resolve()
    paths = [
        path
        for path in sorted(corpus_root.rglob("*.md"))
        if not any(part in {"wiki-build", ".git", "node_modules"} for part in path.parts)
    ]
    files: dict[str, Any] = {}
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        rel_path = str(path.relative_to(corpus_root))
        if progress_every and (index == 1 or index % progress_every == 0 or index == total):
            print(f"scan [{index}/{total}] {rel_path}", flush=True)
        try:
            files[rel_path] = scan_markdown_file(path, corpus_root)
        except Exception as exc:  # pragma: no cover - defensive scaffold
            files[rel_path] = {
                "path": rel_path,
                "error": f"scan_failed: {exc}",
            }
    corpus_kinds = sorted({str(record.get("corpus_kind") or "").strip() for record in files.values() if isinstance(record, dict) and record.get("corpus_kind")})
    return {"corpus_root": str(corpus_root), "files": files, "corpus_kinds": corpus_kinds}
