from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_PROMPT_PROFILES: dict[str, dict[str, Any]] = {
    "whatsapp_chats": {
        "name": "whatsapp_chats",
        "corpus_kind": "whatsapp_chats",
        "guidance": "Extract participants, contact handles, timestamps, reply/thread structure, shared media references, decisions, promises, unresolved questions, recurring entities, and relationship threads.",
        "extraction_fields": ["participants", "contact_handles", "timestamps", "reply_threads", "decisions", "promises", "recurring_entities", "open_questions"],
    },
    "ai_conversations": {
        "name": "ai_conversations",
        "corpus_kind": "ai_conversations",
        "guidance": "Extract the user's goal, model/tool context, useful answers, reusable prompts, decisions, code or commands, open tasks, and places where the assistant may have hallucinated or contradicted another source.",
        "extraction_fields": ["user_goal", "model_context", "useful_answers", "reusable_prompts", "decisions", "code_or_commands", "open_tasks", "uncertainties"],
    },
    "financial_documents": {
        "name": "financial_documents",
        "corpus_kind": "financial_documents",
        "guidance": "Extract vendors, institutions, dates, amounts, account/reference numbers, document type, due dates, tax/category hints, recurring charges, obligations, and ambiguous totals.",
        "extraction_fields": ["vendor", "institution", "document_type", "dates", "amounts", "reference_numbers", "due_dates", "tax_or_category_hints", "recurring_charges"],
    },
    "contacts": {
        "name": "contacts",
        "corpus_kind": "contacts",
        "guidance": "Extract people, organizations, roles, contact methods, relationship context, locations, birthdays or important dates, and source freshness.",
        "extraction_fields": ["people", "organizations", "roles", "contact_methods", "relationship_context", "locations", "important_dates", "freshness"],
    },
    "calendars": {
        "name": "calendars",
        "corpus_kind": "calendars",
        "guidance": "Extract events, attendees, dates, recurrence, locations, travel buffers, decisions implied by scheduling, and conflicts or follow-ups.",
        "extraction_fields": ["events", "attendees", "dates", "recurrence", "locations", "followups", "conflicts"],
    },
    "meeting_notes": {
        "name": "meeting_notes",
        "corpus_kind": "meeting_notes",
        "guidance": "Extract attendees, agenda, decisions, action items, owners, deadlines, blockers, and references to related projects or documents.",
        "extraction_fields": ["attendees", "agenda", "decisions", "action_items", "owners", "deadlines", "blockers", "related_documents"],
    },
    "recording_transcripts": {
        "name": "recording_transcripts",
        "corpus_kind": "recording_transcripts",
        "guidance": "Extract speakers, timestamps, topics, decisions, action items, quotable evidence, uncertainty from transcription, and links to source media.",
        "extraction_fields": ["speakers", "timestamps", "topics", "decisions", "action_items", "evidence_quotes", "transcription_uncertainty", "source_media"],
    },
    "emails": {
        "name": "emails",
        "corpus_kind": "emails",
        "guidance": "Extract senders, recipients, dates, subject threads, commitments, attachments, decisions, follow-ups, and relationship or project context.",
        "extraction_fields": ["senders", "recipients", "dates", "subjects", "commitments", "attachments", "decisions", "followups"],
    },
    "imessages": {
        "name": "imessages",
        "corpus_kind": "imessages",
        "guidance": "Extract participants, timestamps, conversation threads, attachments, decisions, promises, plans, and personal relationship context.",
        "extraction_fields": ["participants", "timestamps", "threads", "attachments", "decisions", "promises", "plans", "relationship_context"],
    },
    "project_artifacts": {
        "name": "project_artifacts",
        "corpus_kind": "project_artifacts",
        "guidance": "Extract project names, milestones, decisions, blockers, solution paths, owners, and deliverables.",
        "extraction_fields": ["project", "milestones", "decisions", "blockers", "solution_paths", "deliverables"],
    },
    "index_ledger_pages": {
        "name": "index_ledger_pages",
        "corpus_kind": "index_ledger_pages",
        "guidance": "Treat as navigation or memory scaffolding; summarize coverage, update history, and links without promoting it above substantive pages.",
        "extraction_fields": ["coverage", "update_history", "navigation_targets", "staleness"],
    },
    "mixed_notes": {
        "name": "mixed_notes",
        "corpus_kind": "mixed_notes",
        "guidance": "Extract topics, entities, source intent, useful claims, questions, and avoid over-merging unrelated notes.",
        "extraction_fields": ["topics", "entities", "claims", "questions", "source_intent"],
    },
    "personal_notes": {
        "name": "personal_notes",
        "corpus_kind": "personal_notes",
        "guidance": "Extract people, projects, intentions, decisions, questions, dated reflections, recurring themes, and private context while keeping speculative notes separate from confirmed facts.",
        "extraction_fields": ["people", "projects", "intentions", "decisions", "questions", "dated_reflections", "themes", "confidence"],
    },
    "google_docs": {
        "name": "google_docs",
        "corpus_kind": "google_docs",
        "guidance": "Extract document purpose, owner, collaborators, decisions, links, version/evolution signals, and claims that need source support.",
        "extraction_fields": ["document_purpose", "owner", "collaborators", "decisions", "links", "version_signals", "claims"],
    },
    "code_repositories": {
        "name": "code_repositories",
        "corpus_kind": "code_repositories",
        "guidance": "Extract repository/module purpose, entrypoints, APIs, dependencies, decisions, TODOs, tests, deployment notes, and links to issues or docs.",
        "extraction_fields": ["repo_purpose", "entrypoints", "apis", "dependencies", "decisions", "todos", "tests", "deployment_notes", "issue_links"],
    },
    "chats": {
        "name": "chats",
        "corpus_kind": "whatsapp_chats",
        "guidance": "Legacy alias for chat-like corpora; extract participants, timestamps, decisions, unresolved questions, promises, and relationship threads.",
        "extraction_fields": ["participants", "timestamps", "decisions", "promises", "threads", "recurring_entities", "open_questions"],
    },
    "bills_documents": {
        "name": "bills_documents",
        "corpus_kind": "financial_documents",
        "guidance": "Legacy alias for financial documents; extract vendors, dates, amounts, account/reference numbers, document type, due dates, and ambiguous totals.",
        "extraction_fields": ["vendor", "document_type", "dates", "amounts", "reference_numbers", "due_dates"],
    },
}


def default_profile_path(corpus_root: Path) -> Path | None:
    for name in ("wikimaker.profiles.json", "wikimaker.profiles.yaml", "wikimaker.profiles.yml"):
        candidate = corpus_root / name
        if candidate.exists():
            return candidate
    return None


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small profile YAML shape WikiMaker documents, without requiring PyYAML."""

    data: dict[str, Any] = {"profiles": {}, "folder_rules": []}
    section = ""
    current_profile: str | None = None
    current_rule: dict[str, Any] | None = None
    current_list_key: str | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0 and line.endswith(":"):
            section = line[:-1].strip()
            current_profile = None
            current_rule = None
            current_list_key = None
            continue
        if section == "profiles":
            if indent == 2 and line.endswith(":"):
                current_profile = line[:-1].strip()
                data["profiles"].setdefault(current_profile, {"name": current_profile})
                current_list_key = None
                continue
            if current_profile and ":" in line:
                key, value = line.split(":", 1)
                value = value.strip().strip('"').strip("'")
                key = key.strip()
                if value:
                    data["profiles"][current_profile][key] = value
                    current_list_key = None
                else:
                    data["profiles"][current_profile][key] = []
                    current_list_key = key
                continue
            if current_profile and current_list_key and line.startswith("- "):
                data["profiles"][current_profile][current_list_key].append(line[2:].strip().strip('"').strip("'"))
                continue
        if section == "folder_rules":
            if line.startswith("- "):
                current_rule = {}
                data["folder_rules"].append(current_rule)
                item = line[2:]
                if ":" in item:
                    key, value = item.split(":", 1)
                    current_rule[key.strip()] = value.strip().strip('"').strip("'")
                continue
            if current_rule is not None and ":" in line:
                key, value = line.split(":", 1)
                current_rule[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_prompt_profile_config(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {"profiles": {}, "folder_rules": [], "source_path": ""}
    profile_path = Path(path).expanduser()
    if not profile_path.exists():
        return {"profiles": {}, "folder_rules": [], "source_path": str(profile_path), "missing": True}
    text = profile_path.read_text(encoding="utf-8")
    if profile_path.suffix.lower() == ".json":
        loaded = json.loads(text)
    else:
        try:
            import yaml  # type: ignore

            loaded = yaml.safe_load(text) or {}
        except Exception:
            loaded = _parse_simple_yaml(text)
    if not isinstance(loaded, dict):
        loaded = {}
    profiles = loaded.get("profiles") if isinstance(loaded.get("profiles"), dict) else {}
    rules = loaded.get("folder_rules") if isinstance(loaded.get("folder_rules"), list) else []
    return {"profiles": profiles, "folder_rules": rules, "source_path": str(profile_path)}


def _clean_profile(profile: dict[str, Any], name: str) -> dict[str, Any]:
    fields = profile.get("extraction_fields", [])
    if isinstance(fields, str):
        fields = [item.strip() for item in fields.split(",") if item.strip()]
    if not isinstance(fields, list):
        fields = []
    return {
        "name": str(profile.get("name") or name).strip() or name,
        "corpus_kind": str(profile.get("corpus_kind") or name).strip() or name,
        "guidance": str(profile.get("guidance") or "").strip(),
        "extraction_fields": [str(item).strip() for item in fields if str(item).strip()],
    }


def apply_prompt_profiles(scan: dict[str, Any], *, corpus_root: Path, profile_path: str | Path | None = None) -> dict[str, Any]:
    selected_path = Path(profile_path).expanduser() if profile_path else default_profile_path(corpus_root)
    loaded = load_prompt_profile_config(selected_path)
    profile_library = {name: dict(value) for name, value in DEFAULT_PROMPT_PROFILES.items()}
    for name, value in loaded.get("profiles", {}).items():
        if isinstance(value, dict):
            profile_library[str(name)] = {**profile_library.get(str(name), {}), **value, "name": str(name)}
    cleaned_profiles = {name: _clean_profile(value, name) for name, value in profile_library.items()}
    rules = [rule for rule in loaded.get("folder_rules", []) if isinstance(rule, dict)]

    files = scan.get("files", {})
    for rel_path, record in files.items():
        if not isinstance(record, dict):
            continue
        matched_rule: dict[str, Any] | None = None
        for rule in rules:
            prefix = str(rule.get("path") or "").strip().strip("/")
            if not prefix:
                continue
            normalized_rel = str(rel_path).strip("/")
            if normalized_rel == prefix or normalized_rel.startswith(prefix + "/"):
                if matched_rule is None or len(prefix) > len(str(matched_rule.get("path") or "")):
                    matched_rule = rule
        profile_name = str((matched_rule or {}).get("profile") or record.get("corpus_kind") or "mixed_notes").strip()
        profile = dict(cleaned_profiles.get(profile_name) or cleaned_profiles.get(record.get("corpus_kind")) or cleaned_profiles["mixed_notes"])
        if matched_rule:
            if matched_rule.get("corpus_kind"):
                profile["corpus_kind"] = str(matched_rule["corpus_kind"]).strip()
                record["corpus_kind"] = profile["corpus_kind"]
            if matched_rule.get("guidance"):
                profile["guidance"] = str(matched_rule["guidance"]).strip()
        record["prompt_profile"] = profile

    scan["prompt_profiles"] = {
        "source_path": loaded.get("source_path", ""),
        "loaded": bool(loaded.get("source_path")) and not loaded.get("missing"),
        "available": sorted(cleaned_profiles),
        "folder_rules": rules,
    }
    scan["corpus_kinds"] = sorted({str(record.get("corpus_kind") or "").strip() for record in files.values() if isinstance(record, dict) and record.get("corpus_kind")})
    return scan
