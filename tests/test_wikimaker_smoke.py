from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import build_discovery_views, write_discovery_views, _source_stub_name
from wikimaker_browser import write_browser_frontend
from wikimaker_openai import SourcePagePlan, AnalysisPlan, GenerationPlan, preflight_llm_endpoint, _require_local_llm_config, _analysis_prompt, _generation_prompt, _compact_scan_for_prompt, _verification_prompt
from wikimaker_privacy import classify_endpoint_privacy
from wikimaker_profiles import apply_prompt_profiles
from wikimaker_health import build_wiki_health, write_health_report
from wikimaker_llm_monitor import monitored_call
from wikimaker_runner import run, write_source_stubs, write_root_index, write_knowledge_pages, write_privacy_report
from wikimaker_scanner import scan_corpus
from wikimaker_source_card import source_card_markdown_name
from wikimaker_state import diff_snapshots
from wikimaker_telemetry import build_telemetry


class WikiMakerSmokeTests(unittest.TestCase):
    def test_config_defaults_from_corpus_root(self) -> None:
        config = WikiMakerConfig.from_env_and_args(corpus_root="/tmp/corpus-root")
        self.assertEqual(config.corpus_root, Path("/tmp/corpus-root"))
        self.assertEqual(config.output_root, Path("/tmp/corpus-root/wiki-build/output"))
        self.assertEqual(config.state_root, Path("/tmp/corpus-root/wiki-build/state"))
        self.assertEqual(config.telemetry_root, Path("/tmp/corpus-root/wiki-build/telemetry"))
        self.assertEqual(config.synthesis_mode, "adk_workflow")
        self.assertTrue(config.use_adk)
        self.assertEqual(config.card_mode, "metadata")

    def test_scan_corpus_can_limit_sorted_markdown_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            corpus_root.mkdir()
            for name in ("c.md", "a.md", "b.md"):
                (corpus_root / name).write_text(f"# {name}\n", encoding="utf-8")
            scan = scan_corpus(corpus_root, limit=2)
            self.assertEqual(list(scan["files"].keys()), ["a.md", "b.md"])

    def test_llm_monitor_writes_safe_success_and_failure_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            telemetry_root = Path(tmp) / "telemetry"
            config = {"telemetry_root": str(telemetry_root), "llm_debug": False}
            result = monitored_call(
                config,
                {
                    "stage": "unit",
                    "role": "analysis",
                    "model": "mock-model",
                    "relative_path": "/Users/private/source.md",
                    "prompt": "raw prompt must not be logged",
                    "prompt_chars": 27,
                },
                lambda: "ok",
            )
            self.assertEqual(result, "ok")
            with self.assertRaisesRegex(RuntimeError, "boom"):
                monitored_call(config, {"stage": "unit_fail", "role": "analysis", "model": "mock-model"}, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            log_text = (telemetry_root / "llm_calls.jsonl").read_text(encoding="utf-8")
            current = json.loads((telemetry_root / "current.json").read_text(encoding="utf-8"))
            self.assertIn("llm_call_start", log_text)
            self.assertIn("llm_call_done", log_text)
            self.assertIn("llm_call_fail", log_text)
            self.assertNotIn("raw prompt", log_text)
            self.assertNotIn("/Users/private", log_text)
            self.assertEqual(current["event"], "llm_call_fail")

    def test_local_llm_config_rejects_non_local_endpoints(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Refusing non-local LLM endpoint"):
            _require_local_llm_config({"provider": "ollama", "openai_base_url": "http://example.com:11434"})

    def test_endpoint_privacy_classification_and_remote_opt_in(self) -> None:
        self.assertEqual(classify_endpoint_privacy("http://127.0.0.1:11434")["classification"], "local")
        self.assertEqual(classify_endpoint_privacy("http://10.0.0.2:11434")["classification"], "lan")
        remote = classify_endpoint_privacy("https://api.example.com/v1")
        self.assertEqual(remote["classification"], "remote")
        self.assertFalse(remote["allowed_by_default"])
        provider, base_url, _ = _require_local_llm_config(
            {
                "provider": "ollama",
                "openai_base_url": "https://api.example.com/v1",
                "allow_remote_llm": True,
            }
        )
        self.assertEqual(provider, "ollama")
        self.assertEqual(base_url, "https://api.example.com/v1")

    def test_llm_preflight_reports_connection_failure_with_endpoint_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "provider": "ollama",
                "openai_base_url": "http://127.0.0.1:11434",
                "analysis_model": "gemma4:e4b-mlx",
                "generation_model": "gemma4:e4b-mlx",
                "review_model": "gemma4:e4b-mlx",
                "telemetry_root": str(Path(tmp) / "telemetry"),
            }
            with patch(
                "wikimaker_openai._chat_completions",
                side_effect=RuntimeError("OpenAI-compatible request failed for http://127.0.0.1:11434/api/chat: <urlopen error [Errno 61] Connection refused>"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Unable to reach local LLM endpoint 'http://127.0.0.1:11434' while checking analysis model 'gemma4:e4b-mlx'"):
                    preflight_llm_endpoint(config)

    def test_scanner_extracts_title_headings_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp)
            md = corpus_root / "notes" / "sample.md"
            md.parent.mkdir(parents=True, exist_ok=True)
            md.write_text(
                """---
title: Sample Note
source_url: https://example.com/original
---

# Sample Note

See [Reference](https://example.com/ref).
""",
                encoding="utf-8",
            )

            scan = scan_corpus(corpus_root)
            record = scan["files"]["notes/sample.md"]
            self.assertEqual(record["title"], "Sample Note")
            self.assertIn("# Sample Note", record["headings"])
            self.assertIn("https://example.com/ref", record["source_links"])
            self.assertEqual(record["source_url"], "https://example.com/original")

    def test_corpus_kind_scanner_and_prompts_branch_by_document_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            corpus_root.mkdir(parents=True, exist_ok=True)
            files = {
                "whatsapp/chat.md": """# WhatsApp Team chat

Conversation notes from Alice and Bob.
Alice: can we ship this today?
Bob: yes, after lunch.
""",
                "ai/claude.md": """# Claude conversation

User: help me refactor the wiki generator.
Assistant: use a source-first compiler and keep provenance.
Tool call: inspect repository.
""",
                "invoice.md": """# Invoice 42

Invoice from ACME Corp.
Total due: $42.00
Due date: 2024-01-31
""",
                "project.md": """# Project plan

Milestone 1: design review
TODO: confirm rollout blockers
""",
                "ledger.md": """# Change log

Table of contents for this ledger page.
""",
                "notes.md": """# General notes

A loose set of mixed notes and ideas.
""",
                "journal.md": """# Personal note

Journal entry and reflection about priorities.
""",
            }
            for rel_path, content in files.items():
                path = corpus_root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            scan = scan_corpus(corpus_root)
            scan = apply_prompt_profiles(scan, corpus_root=corpus_root)
            kinds = {record.get("corpus_kind") for record in scan["files"].values() if isinstance(record, dict)}
            self.assertIn("whatsapp_chats", kinds)
            self.assertIn("ai_conversations", kinds)
            self.assertIn("financial_documents", kinds)
            self.assertIn("project_artifacts", kinds)
            self.assertIn("index_ledger_pages", kinds)
            self.assertIn("mixed_notes", kinds)
            self.assertIn("personal_notes", kinds)

            compact = _compact_scan_for_prompt(scan, {"added": [], "changed": [], "removed": [], "unchanged": []})
            self.assertGreaterEqual(len(compact["corpus_kinds"]), 7)
            analysis_prompt = _analysis_prompt(compact)
            self.assertIn("Detected corpus kinds:", analysis_prompt)
            self.assertIn("WhatsApp chats:", analysis_prompt)
            self.assertIn("AI conversations:", analysis_prompt)
            self.assertIn("Financial documents:", analysis_prompt)
            self.assertIn("Project artifacts:", analysis_prompt)
            self.assertIn("Index/ledger pages:", analysis_prompt)
            self.assertIn("Mixed notes:", analysis_prompt)
            self.assertIn("Personal notes:", analysis_prompt)

            analysis = AnalysisPlan(corpus_kinds=compact["corpus_kinds"])
            generation_prompt = _generation_prompt(compact, analysis)
            self.assertIn("Keep WhatsApp chats, AI conversations, financial documents", generation_prompt)
            self.assertIn("Detected corpus kinds:", generation_prompt)
            generation_result = GenerationPlan()
            verification_prompt = _verification_prompt(compact, analysis, generation_result)
            self.assertIn("Corpus-kind instructions:", verification_prompt)
            self.assertIn("Prompt-profile instructions:", verification_prompt)

    def test_prompt_profiles_override_nearest_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            chats_dir = corpus_root / "exports" / "chats"
            chats_dir.mkdir(parents=True, exist_ok=True)
            (chats_dir / "thread.md").write_text("# Thread\nAlice: ship it\n", encoding="utf-8")
            profile_path = corpus_root / "wikimaker.profiles.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "relationship_chat": {
                                "corpus_kind": "whatsapp_chats",
                                "guidance": "Capture relationship context and promises.",
                                "extraction_fields": ["people", "promises"],
                            }
                        },
                        "folder_rules": [
                            {"path": "exports", "profile": "mixed_notes"},
                            {"path": "exports/chats", "profile": "relationship_chat", "corpus_kind": "whatsapp_chats"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            scan = apply_prompt_profiles(scan_corpus(corpus_root), corpus_root=corpus_root)
            record = scan["files"]["exports/chats/thread.md"]
            self.assertEqual(record["prompt_profile"]["name"], "relationship_chat")
            self.assertEqual(record["corpus_kind"], "whatsapp_chats")
            compact = _compact_scan_for_prompt(scan, {"added": [], "changed": [], "removed": [], "unchanged": []})
            prompt = _analysis_prompt(compact)
            self.assertIn("Capture relationship context and promises.", prompt)

    def test_snapshot_diff_and_telemetry_counts(self) -> None:
        previous = {"files": {"a.md": {"sha256": "1"}}}
        current = {"files": {"a.md": {"sha256": "2"}, "b.md": {"sha256": "3"}}}
        diff = diff_snapshots(previous, current)
        self.assertEqual(diff["added"], ["b.md"])
        self.assertEqual(diff["changed"], ["a.md"])
        telemetry = build_telemetry({"use_adk": False}, diff, {"files": current["files"]})
        self.assertEqual(telemetry["scan"]["total_files"], 2)
        self.assertEqual(telemetry["scan"]["added"], 1)
        self.assertEqual(telemetry["scan"]["changed"], 1)

    def test_discovery_views_write_dashboard_stats_search_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            output_root = Path(tmp) / "output"
            state_root = Path(tmp) / "state"
            telemetry_root = Path(tmp) / "telemetry"
            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
            )
            scan = {
                "corpus_root": str(corpus_root),
                "files": {
                    "notes/a.md": {
                        "path": "notes/a.md",
                        "title": "Alpha",
                        "sha256": "1",
                        "size": 10,
                        "mtime_ns": 20,
                        "line_count": 3,
                        "headings": ["# Alpha"],
                        "source_links": ["https://example.com/a"],
                        "source_kind": "chat",
                        "platform": "whatsapp",
                        "source_url": "https://example.com/a",
                        "extracted_at": "2024-01-01T00:00:00+00:00",
                    },
                    "notes/b.md": {
                        "path": "notes/b.md",
                        "title": "Beta",
                        "sha256": "2",
                        "size": 12,
                        "mtime_ns": 30,
                        "line_count": 5,
                        "headings": ["# Beta"],
                        "source_links": [],
                        "source_kind": "chat",
                        "platform": "whatsapp",
                        "source_url": "https://example.com/b",
                        "extracted_at": "2024-01-02T00:00:00+00:00",
                    },
                },
            }
            diff = {"added": ["notes/a.md"], "changed": ["notes/b.md"], "removed": [], "unchanged": []}
            pipeline = {
                "analysis": {
                    "corpus_summary": "Test corpus",
                    "corpus_kinds": ["chat"],
                    "topic_clusters": ["Alpha topic"],
                    "entity_clusters": ["Beta entity"],
                    "duplicate_clusters": ["Alpha/Beta duplicate"],
                    "contradiction_clusters": ["Alpha/Beta contradiction"],
                    "reorg_suggestions": ["Merge sibling notes"],
                },
                "generation": {
                    "dashboard_summary": "Dashboard summary",
                    "stats_summary": "Stats summary",
                    "source_pages": [
                        {
                            "path": "notes/a.md",
                            "title": "Alpha",
                            "summary": "Alpha summary",
                            "platform": "whatsapp",
                            "source_kind": "chat",
                            "source_url": "https://example.com/a",
                            "tags": ["tag-a"],
                            "topics": ["Alpha topic"],
                            "entities": ["Alpha entity"],
                            "related_pages": [],
                            "used_in": ["Chat set A"],
                            "key_snippets": ["alpha snippet"],
                        },
                        {
                            "path": "notes/b.md",
                            "title": "Beta",
                            "summary": "Beta summary",
                            "platform": "whatsapp",
                            "source_kind": "chat",
                            "source_url": "https://example.com/b",
                            "tags": ["tag-b"],
                            "topics": ["Beta topic"],
                            "entities": ["Beta entity"],
                            "related_pages": ["notes/a.md", "notes/missing-1.md", "notes/missing-2.md", "notes/missing-3.md"],
                            "used_in": ["Chat set A", "Chat set B", "Chat set C", "Chat set D"],
                            "key_snippets": ["beta snippet"],
                        },
                    ],
                    "wiki_set_pages": [
                        {
                            "name": "Chat set A",
                            "purpose": "Shared chat corpus",
                            "pages": ["Alpha", "Beta"],
                        },
                        {
                            "name": "Chat set B",
                            "purpose": "Alpha-only supporting set",
                            "pages": ["Alpha"],
                        },
                        {
                            "name": "Chat set C",
                            "purpose": "Alpha-only supporting set",
                            "pages": ["Alpha"],
                        },
                        {
                            "name": "Chat set D",
                            "purpose": "Alpha-only supporting set",
                            "pages": ["Alpha"],
                        },
                    ],
                },
                "verification": {"approved": True, "confidence": 0.9},
            }
            views = build_discovery_views(scan, diff, pipeline)
            self.assertEqual(len(views["graph"]["nodes"]), 6)
            self.assertEqual(views["graph"]["nodes"][0]["label"], "Beta")
            self.assertIn("score", views["graph"]["nodes"][0])
            paths = write_discovery_views(config, scan, diff, pipeline)
            self.assertTrue(paths["dashboard"].exists())
            self.assertTrue(paths["stats"].exists())
            self.assertTrue(paths["search"].exists())
            self.assertTrue(paths["graph"].exists())
            dashboard_text = paths["dashboard"].read_text(encoding="utf-8")
            search_text = paths["search"].read_text(encoding="utf-8")
            self.assertIn("WikiMaker Dashboard", dashboard_text)
            beta_source = source_card_markdown_name("notes/b.md")
            alpha_source = source_card_markdown_name("notes/a.md")
            self.assertIn(f"| [Beta](sources/{beta_source}) |", dashboard_text)
            self.assertLess(dashboard_text.index(f"[Beta](sources/{beta_source})"), dashboard_text.index(f"[Alpha](sources/{alpha_source})"))
            self.assertIn("WikiMaker Stats", paths["stats"].read_text(encoding="utf-8"))
            self.assertIn("WikiMaker Search Index", search_text)
            self.assertIn("## Jump table", search_text)
            self.assertIn("## Navigation / index / ledger pages", search_text)
            self.assertIn("Alpha", search_text)
            self.assertIn("Beta", search_text)
            self.assertIn("Chat set A", search_text)

            browser_path = write_browser_frontend(config, scan, diff, pipeline)
            self.assertTrue(browser_path.exists())
            browser_text = browser_path.read_text(encoding="utf-8")
            browser_data = json.loads((output_root / "browser" / "data.json").read_text(encoding="utf-8"))
            self.assertTrue(browser_data["library_pages"][0]["links_to"])
            self.assertTrue(any(page["linked_from"] for page in browser_data["library_pages"]))
            self.assertIn("privacy", browser_data)
            self.assertEqual(browser_data["privacy"]["browser"]["classification"], "static-local")
            self.assertIn("facets", browser_data)
            self.assertIn("WikiMaker Browser", browser_text)
            self.assertIn("sourceGrid", browser_text)
            self.assertIn("libraryGrid", browser_text)
            self.assertIn("themeToggle", browser_text)
            self.assertIn("localStorage", browser_text)
            self.assertIn("Most connected pages", browser_text)
            self.assertIn("Recently changed", browser_text)
            self.assertIn("Wiki sets", browser_text)
            self.assertIn("Source library", browser_text)
            self.assertIn("wiki pages", browser_text)
            self.assertIn("library pages", browser_text)
            self.assertIn("Links to", browser_text)
            self.assertIn("Linked from", browser_text)
            self.assertIn("Topics and entities", browser_text)
            self.assertIn("Settings / Privacy", browser_text)
            self.assertIn("_privacy.md", browser_text)
            self.assertNotIn("fetch(", browser_text)

            source_stubs = write_source_stubs(config, scan, diff, pipeline["generation"])
            self.assertTrue(any(path.name == alpha_source for path in source_stubs))
            stub_path = output_root / "sources" / alpha_source
            self.assertTrue(stub_path.exists())
            stub_text = stub_path.read_text(encoding="utf-8")
            self.assertIn("## Navigation", stub_text)
            self.assertIn("## Topics", stub_text)
            self.assertIn("## Entities", stub_text)
            self.assertIn("## Links to", stub_text)
            self.assertIn("## Linked from", stub_text)

            knowledge_paths = write_knowledge_pages(config, pipeline, scan)
            self.assertTrue(any("_topics" in str(path) for path in knowledge_paths))
            self.assertTrue(any("_entities" in str(path) for path in knowledge_paths))
            topic_page = output_root / "wiki-sets" / "_topics" / "alpha-topic.md"
            entity_page = output_root / "wiki-sets" / "_entities" / "beta-entity.md"
            self.assertTrue(topic_page.exists())
            self.assertTrue(entity_page.exists())
            topic_text = topic_page.read_text(encoding="utf-8")
            self.assertIn("## Sources", topic_text)
            self.assertIn("## Evidence / Truth trail", topic_text)
            self.assertIn("## Contradictions / Tensions", topic_text)

            privacy_path = write_privacy_report(config, scan, {"privacy": classify_endpoint_privacy(config.openai_base_url)})
            self.assertIn("Browser network posture", privacy_path.read_text(encoding="utf-8"))
            health = build_wiki_health(scan, pipeline, views["graph"])
            self.assertIn("counts", health)
            health_path = write_health_report(output_root, health)
            self.assertTrue(health_path.exists())

    def test_page_roles_separate_primary_and_navigation_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            output_root = Path(tmp) / "output"
            state_root = Path(tmp) / "state"
            telemetry_root = Path(tmp) / "telemetry"
            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
            )
            scan = {
                "corpus_root": str(corpus_root),
                "files": {
                    "notes/alpha.md": {
                        "path": "notes/alpha.md",
                        "title": "Alpha",
                        "sha256": "1",
                        "size": 10,
                        "mtime_ns": 100,
                        "line_count": 4,
                        "headings": ["# Alpha"],
                        "source_links": [],
                        "source_kind": "notes",
                        "platform": "",
                        "source_url": "",
                        "extracted_at": "",
                    },
                    "notes/beta.md": {
                        "path": "notes/beta.md",
                        "title": "Beta",
                        "sha256": "2",
                        "size": 11,
                        "mtime_ns": 90,
                        "line_count": 4,
                        "headings": ["# Beta"],
                        "source_links": [],
                        "source_kind": "notes",
                        "platform": "",
                        "source_url": "",
                        "extracted_at": "",
                    },
                    "notes/gamma.md": {
                        "path": "notes/gamma.md",
                        "title": "Gamma",
                        "sha256": "3",
                        "size": 12,
                        "mtime_ns": 80,
                        "line_count": 4,
                        "headings": ["# Gamma"],
                        "source_links": [],
                        "source_kind": "notes",
                        "platform": "",
                        "source_url": "",
                        "extracted_at": "",
                    },
                    "notes/delta.md": {
                        "path": "notes/delta.md",
                        "title": "Delta",
                        "sha256": "4",
                        "size": 13,
                        "mtime_ns": 70,
                        "line_count": 4,
                        "headings": ["# Delta"],
                        "source_links": [],
                        "source_kind": "notes",
                        "platform": "",
                        "source_url": "",
                        "extracted_at": "",
                    },
                },
            }
            diff = {"added": ["notes/alpha.md", "notes/beta.md", "notes/gamma.md", "notes/delta.md"], "changed": [], "removed": [], "unchanged": []}
            pipeline = {
                "analysis": {
                    "corpus_summary": "Role-aware test corpus",
                    "corpus_kinds": ["notes"],
                    "topic_clusters": [],
                    "entity_clusters": [],
                    "duplicate_clusters": [],
                    "contradiction_clusters": [],
                    "reorg_suggestions": [],
                },
                "generation": {
                    "root_index_summary": "Role-aware root index",
                    "dashboard_summary": "Role-aware dashboard",
                    "stats_summary": "Role-aware stats",
                    "source_pages": [
                        {
                            "path": "notes/alpha.md",
                            "title": "Alpha",
                            "page_role": "knowledge_page",
                            "summary": "Alpha knowledge page",
                            "source_kind": "chat",
                            "platform": "whatsapp",
                            "source_url": "https://example.com/alpha",
                            "related_pages": ["Beta"],
                            "used_in": ["Primary set"],
                        },
                        {
                            "path": "notes/beta.md",
                            "title": "Beta",
                            "page_role": "thread_page",
                            "summary": "Beta thread page",
                            "source_kind": "chat",
                            "platform": "whatsapp",
                            "external_link": "https://example.com/beta-thread",
                            "related_pages": ["Alpha"],
                            "used_in": ["Primary set"],
                        },
                        {
                            "path": "notes/gamma.md",
                            "title": "Gamma",
                            "page_role": "index_page",
                            "summary": "Gamma navigation page",
                            "source_kind": "notes",
                            "platform": "docs",
                            "source_url": "https://example.com/gamma",
                            "related_pages": ["Alpha"],
                            "used_in": ["Primary set"],
                        },
                        {
                            "path": "notes/delta.md",
                            "title": "Delta",
                            "page_role": "ledger_page",
                            "summary": "Delta navigation page",
                            "source_kind": "ledger",
                            "platform": "docs",
                            "external_link": "https://example.com/delta",
                            "related_pages": ["Beta"],
                            "used_in": ["Primary set"],
                        },
                    ],
                    "wiki_set_pages": [
                        {
                            "name": "Primary set",
                            "purpose": "Primary role-aware set",
                            "pages": ["Alpha", "Beta", "Gamma", "Delta"],
                        }
                    ],
                },
                "verification": {"approved": True, "confidence": 0.8},
            }

            self.assertIn("page_role", SourcePagePlan.model_fields)

            views = build_discovery_views(scan, diff, pipeline)
            source_nodes = [node for node in views["graph"]["nodes"] if node.get("type") == "source"]
            self.assertTrue(all(node["page_role"] in {"knowledge_page", "thread_page"} for node in source_nodes[:2]))
            self.assertTrue(all(node["page_role"] in {"index_page", "ledger_page"} for node in source_nodes[2:]))

            paths = write_discovery_views(config, scan, diff, pipeline)
            search_text = paths["search"].read_text(encoding="utf-8")
            self.assertIn("## Source pages", search_text)
            self.assertIn("## Navigation / index / ledger pages", search_text)
            primary_section, navigation_section = search_text.split("## Navigation / index / ledger pages", 1)
            self.assertIn("Alpha", primary_section)
            self.assertIn("Beta", primary_section)
            self.assertNotIn("Gamma", primary_section)
            self.assertNotIn("Delta", primary_section)
            self.assertIn("Gamma", navigation_section)
            self.assertIn("Delta", navigation_section)

            root_index = write_root_index(config, pipeline)
            root_text = root_index.read_text(encoding="utf-8")
            self.assertIn("## Page roles", root_text)
            self.assertIn("Primary source pages", root_text)
            self.assertIn("Navigation pages", root_text)
            self.assertIn("## Jump table", root_text)
            self.assertIn("[_Privacy boundary](_privacy.md)", root_text)
            self.assertIn("[_Health check](_health.md)", root_text)
            self.assertIn("## Source pages", root_text)
            self.assertIn("| Title | Provenance | Source markdown | Stub | External/source link |", root_text)
            self.assertIn("Knowledge Page, chat, whatsapp", root_text)
            self.assertIn("Thread Page, chat, whatsapp", root_text)
            self.assertIn("`notes/alpha.md`", root_text)
            self.assertIn(f"[source stub](sources/{source_card_markdown_name('notes/alpha.md')})", root_text)
            self.assertIn("https://example.com/alpha", root_text)
            self.assertIn("https://example.com/beta-thread", root_text)

    def test_runner_generates_static_wiki_artifacts_with_mock_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_root = root / "corpus"
            output_root = root / "output"
            state_root = root / "state"
            telemetry_root = root / "telemetry"
            (corpus_root / "chats").mkdir(parents=True, exist_ok=True)
            (corpus_root / "bills").mkdir(parents=True, exist_ok=True)
            (corpus_root / "ai").mkdir(parents=True, exist_ok=True)
            (corpus_root / "chats" / "team.md").write_text(
                "# Team Chat\n\nAlice: ship the launch plan after invoice review.\nBob: agreed.\n",
                encoding="utf-8",
            )
            (corpus_root / "bills" / "invoice.md").write_text(
                "# Invoice 42\n\nVendor: ACME Corp\nAmount: $42.00\nDue: 2026-06-01\n",
                encoding="utf-8",
            )
            (corpus_root / "ai" / "assistant.md").write_text(
                "# AI Conversation\n\nUser: connect this with the launch plan.\nAssistant: link the project and finance evidence.\n",
                encoding="utf-8",
            )
            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="mock-analysis",
                generation_model="mock-generation",
                review_model="mock-review",
                synthesis_mode="llm_only",
                enable_quality_judge=False,
            )

            def fake_pipeline(scan: dict[str, Any], diff: dict[str, list[str]], config_dict: dict[str, Any]) -> dict[str, Any]:
                self.assertIn("prompt_profile", scan["files"]["chats/team.md"])
                self.assertIn("prompt_profile", scan["files"]["bills/invoice.md"])
                self.assertIn("prompt_profile", scan["files"]["ai/assistant.md"])
                return {
                    "llm_used": True,
                    "errors": [],
                    "analysis": {
                        "corpus_summary": "Launch chat plus invoice corpus.",
                        "corpus_kinds": scan.get("corpus_kinds", []),
                        "topic_clusters": ["Launch Plan"],
                        "entity_clusters": ["Alice Nguyen", "ACME Corp"],
                        "duplicate_clusters": ["Invoice review repeats in team chat"],
                        "contradiction_clusters": ["Invoice date needs confirmation"],
                        "reorg_suggestions": [],
                        "confidence": 0.8,
                    },
                    "generation": {
                        "root_index_summary": "Mock generated root index.",
                        "dashboard_summary": "Mock generated dashboard.",
                        "stats_summary": "Mock generated stats.",
                        "source_pages": [
                            {
                                "path": "chats/team.md",
                                "title": "Team Chat",
                                "page_role": "thread_page",
                                "summary": "Alice and Bob discuss launch timing and invoice review.",
                                "source_kind": "chat",
                                "platform": "markdown",
                                "topics": ["Launch Plan"],
                                "entities": ["Alice Nguyen", "ACME Corp"],
                                "related_pages": ["Invoice 42"],
                                "used_in": ["Launch Operations"],
                                "key_snippets": ["Alice: ship the launch plan after invoice review."],
                            },
                            {
                                "path": "bills/invoice.md",
                                "title": "Invoice 42",
                                "page_role": "knowledge_page",
                                "summary": "ACME invoice with amount and due date.",
                                "source_kind": "bill",
                                "platform": "markdown",
                                "topics": ["Launch Plan"],
                                "entities": ["ACME Corp"],
                                "related_pages": ["Team Chat"],
                                "used_in": ["Launch Operations"],
                                "key_snippets": ["Amount: $42.00"],
                            },
                        ],
                        "wiki_set_pages": [
                            {
                                "name": "Launch Operations",
                                "purpose": "Cross-links launch chat and invoice evidence.",
                                "pages": ["Team Chat", "Invoice 42"],
                            }
                        ],
                        "needed_followups": [],
                        "confidence": 0.8,
                    },
                    "verification": {"approved": True, "findings": [], "changes_requested": [], "confidence": 0.8},
                }

            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={"provider": "ollama", "base_url": "http://127.0.0.1:11434", "checked_models": []}), patch("wikimaker_runner.run_pipeline", side_effect=fake_pipeline):
                result = run(config)

            self.assertEqual(result["scan"]["total_files"], 3)
            self.assertTrue((output_root / "_privacy.md").exists())
            self.assertTrue((output_root / "_health.md").exists())
            self.assertTrue((output_root / "browser" / "index.html").exists())
            self.assertTrue((output_root / "browser" / "data.json").exists())
            self.assertTrue((output_root / "_llm_quality.md").exists())
            self.assertTrue((output_root / "wiki-sets" / "_topics" / "launch-plan.md").exists())
            self.assertTrue((output_root / "wiki-sets" / "_entities" / "acme-corp.md").exists())
            team_source = source_card_markdown_name("chats/team.md")
            self.assertTrue((output_root / "sources" / team_source).exists())
            self.assertTrue((state_root / "corpus_snapshot.json").exists())
            html = (output_root / "browser" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("fetch(", html)
            self.assertNotIn("radial-gradient", html)
            self.assertNotIn("hero-side card", html)
            browser_data = json.loads((output_root / "browser" / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(browser_data["counts"]["semantic_source_pages"], 2)
            self.assertEqual(browser_data["counts"]["library_pages"], 3)
            self.assertGreater(browser_data["counts"]["edges"], 0)
            self.assertEqual(browser_data["privacy"]["model_endpoint"]["classification"], "local")
            self.assertEqual(browser_data["privacy"]["browser"]["classification"], "static-local")
            source_text = (output_root / "sources" / team_source).read_text(encoding="utf-8")
            self.assertIn("## Links to", source_text)
            self.assertIn("Invoice 42", source_text)
            self.assertIn("## Linked from", source_text)
            search_text = (output_root / "_search.md").read_text(encoding="utf-8")
            self.assertIn("AI Conversation", search_text)
            quality_text = (output_root / "_llm_quality.md").read_text(encoding="utf-8")
            self.assertIn("aggregate counts only", quality_text)
            self.assertIn("LLM generated source-page coverage is below 80%", quality_text)
            self.assertNotIn("ai/assistant.md", quality_text)
            self.assertNotIn("Team Chat", quality_text)

    def test_coverage_fallback_skips_llm_and_generates_scan_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_root = root / "corpus"
            output_root = root / "output"
            state_root = root / "state"
            telemetry_root = root / "telemetry"
            (corpus_root / "notes").mkdir(parents=True, exist_ok=True)
            (corpus_root / "notes" / "alpha.md").write_text("# Alpha\n\nFirst note.\n", encoding="utf-8")
            (corpus_root / "notes" / "beta.md").write_text("# Beta\n\nSecond note.\n", encoding="utf-8")
            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="slow-model",
                generation_model="slow-model",
                review_model="slow-model",
                synthesis_mode="coverage_fallback",
                enable_quality_judge=True,
            )

            with patch("wikimaker_runner.preflight_llm_endpoint", side_effect=AssertionError("preflight should be skipped")), patch("wikimaker_runner.run_pipeline", side_effect=AssertionError("LLM pipeline should be skipped")):
                result = run(config)

            self.assertFalse(result["llm"]["used"])
            self.assertEqual(result["scan"]["total_files"], 2)
            self.assertTrue((output_root / "sources" / source_card_markdown_name("notes/alpha.md")).exists())
            self.assertTrue((output_root / "sources" / source_card_markdown_name("notes/beta.md")).exists())
            browser_data = json.loads((output_root / "browser" / "data.json").read_text(encoding="utf-8"))
            self.assertEqual(browser_data["counts"]["library_pages"], 2)
            self.assertGreaterEqual(browser_data["counts"]["semantic_source_pages"], 2)
            quality_text = (output_root / "_llm_quality.md").read_text(encoding="utf-8")
            self.assertIn("Coverage fallback is scan-only", quality_text)

    def test_map_reduce_cards_are_cached_and_force_paths_refresh_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_root = root / "corpus"
            output_root = root / "output"
            state_root = root / "state"
            telemetry_root = root / "telemetry"
            (corpus_root / "notes").mkdir(parents=True, exist_ok=True)
            (corpus_root / "notes" / "alpha.md").write_text("# Alpha\n\nFirst note.\n", encoding="utf-8")
            (corpus_root / "notes" / "beta.md").write_text("# Beta\n\nSecond note.\n", encoding="utf-8")

            def fake_chat(_provider: str, _base_url: str, _api_key: str, model: str, messages: list[dict[str, Any]], **_kwargs: Any) -> str:
                prompt = messages[-1]["content"]
                if "SOURCE_MARKDOWN_EXCERPT" in prompt:
                    path = "notes/alpha.md" if "notes/alpha.md" in prompt else "notes/beta.md"
                    title = "Alpha" if path.endswith("alpha.md") else "Beta"
                    return json.dumps(
                        {
                            "path": path,
                            "title": title,
                            "page_role": "knowledge_page",
                            "summary": f"{title} card summary",
                            "source_kind": "note",
                            "corpus_kind": "mixed_notes",
                            "topics": [title],
                            "entities": [],
                            "dates": [],
                            "amounts": [],
                            "candidate_links": [],
                            "source_quality": "ok",
                            "warnings": [],
                            "confidence": 0.8,
                        }
                    )
                if "BATCH_SUMMARIES_JSON" in prompt:
                    return json.dumps(
                        {
                            "corpus_summary": "Merged alpha and beta.",
                            "root_index_summary": "Merged root.",
                            "dashboard_summary": "Merged dashboard.",
                            "stats_summary": "Two cards.",
                            "wiki_sets": [{"name": "Notes", "purpose": "Notes set", "pages": ["Alpha", "Beta"]}],
                            "topic_clusters": ["Alpha", "Beta"],
                            "entity_clusters": [],
                            "duplicate_clusters": [],
                            "contradiction_clusters": [],
                            "confidence": 0.8,
                        }
                    )
                return json.dumps(
                    {
                        "name": "Batch 1",
                        "summary": "Batch summary",
                        "topics": ["Alpha", "Beta"],
                        "entities": [],
                        "wiki_sets": ["Notes"],
                        "duplicate_hints": [],
                        "contradiction_hints": [],
                        "link_hints": [],
                        "confidence": 0.8,
                    }
                )

            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="mock-analysis",
                generation_model="mock-generation",
                review_model="mock-review",
                synthesis_mode="map_reduce",
                card_mode="sampled",
                llm_debug=True,
                enable_quality_judge=False,
            )
            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={}), patch("wikimaker_cards._chat_completions", side_effect=fake_chat) as chat:
                first = run(config)
            self.assertEqual(first["llm"]["used"], True)
            self.assertTrue((state_root / "card_index.json").exists())
            self.assertEqual(len(list((state_root / "cards").glob("*.json"))), 2)
            first_file_calls = sum(1 for call in chat.call_args_list if "SOURCE_MARKDOWN_EXCERPT" in call.args[4][-1]["content"])
            self.assertEqual(first_file_calls, 2)

            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={}), patch("wikimaker_cards._chat_completions", side_effect=fake_chat) as second_chat:
                second = run(config)
            self.assertEqual(second["scan"]["unchanged"], 2)
            second_file_calls = sum(1 for call in second_chat.call_args_list if "SOURCE_MARKDOWN_EXCERPT" in call.args[4][-1]["content"])
            self.assertEqual(second_file_calls, 0)

            force_config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="mock-analysis",
                generation_model="mock-generation",
                review_model="mock-review",
                synthesis_mode="map_reduce",
                card_mode="sampled",
                force_paths=["notes/alpha.md"],
                enable_quality_judge=False,
            )
            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={}), patch("wikimaker_cards._chat_completions", side_effect=fake_chat) as force_chat:
                run(force_config)
            forced_file_calls = [call for call in force_chat.call_args_list if "SOURCE_MARKDOWN_EXCERPT" in call.args[4][-1]["content"]]
            self.assertEqual(len(forced_file_calls), 1)
            self.assertIn("notes/alpha.md", forced_file_calls[0].args[4][-1]["content"])
            source_text = (output_root / "sources" / source_card_markdown_name("notes/alpha.md")).read_text(encoding="utf-8")
            self.assertIn("## Build telemetry", source_text)
            telemetry = json.loads((telemetry_root / "latest.json").read_text(encoding="utf-8"))
            llm_log = (telemetry_root / "llm_calls.jsonl").read_text(encoding="utf-8")
            current_call = json.loads((telemetry_root / "current.json").read_text(encoding="utf-8"))
            self.assertIn("file_card", llm_log)
            self.assertIn("batch_merge", llm_log)
            self.assertIn("global_merge", llm_log)
            self.assertIn("llm_calls", telemetry)
            self.assertGreaterEqual(telemetry["llm_calls"]["total"], 1)
            self.assertIn(current_call["event"], {"llm_call_done", "llm_call_fail"})
            self.assertIn("stages", telemetry)
            self.assertEqual(telemetry["stages"]["card"]["counts"]["forced"], 1)

    def test_adk_workflow_default_uses_metadata_cards_without_source_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus_root = root / "corpus"
            output_root = root / "output"
            state_root = root / "state"
            telemetry_root = root / "telemetry"
            corpus_root.mkdir(parents=True, exist_ok=True)
            (corpus_root / "alpha.md").write_text("# Alpha\n\nThis original body should not be sent by default.\n", encoding="utf-8")

            prompts: list[str] = []

            def fake_chat(_provider: str, _base_url: str, _api_key: str, model: str, messages: list[dict[str, Any]], **_kwargs: Any) -> str:
                prompt = messages[-1]["content"]
                prompts.append(prompt)
                if "BATCH_SUMMARIES_JSON" in prompt:
                    return json.dumps({"corpus_summary": "Merged alpha.", "wiki_sets": [], "confidence": 0.7})
                if "CARDS_JSON" in prompt:
                    return json.dumps({"name": "Batch 1", "summary": "Batch summary", "confidence": 0.7})
                return json.dumps(
                    {
                        "path": "alpha.md",
                        "title": "Alpha",
                        "page_role": "knowledge_page",
                        "summary": "Alpha metadata summary",
                        "source_kind": "note",
                        "corpus_kind": "mixed_notes",
                        "topics": ["Alpha"],
                        "entities": [],
                        "dates": [],
                        "amounts": [],
                        "candidate_links": [],
                        "source_quality": "ok",
                        "warnings": [],
                        "confidence": 0.7,
                        "tags": ["mixed_notes"],
                    }
                )

            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="mock-analysis",
                generation_model="mock-generation",
                review_model="mock-review",
                enable_quality_judge=False,
            )
            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={}), patch("wikimaker_cards._chat_completions", side_effect=fake_chat):
                result = run(config)
            self.assertEqual(result["config"]["synthesis_mode"], "adk_workflow")
            telemetry = json.loads((telemetry_root / "latest.json").read_text(encoding="utf-8"))
            self.assertIn("adk_workflow", telemetry["stages"])
            self.assertFalse(any("SOURCE_MARKDOWN_EXCERPT" in prompt for prompt in prompts))
            card_path = next((state_root / "cards").glob("*.json"))
            card_payload = json.loads(card_path.read_text(encoding="utf-8"))
            self.assertEqual(card_payload["signature"]["card_mode"], "metadata")
            source_path = output_root / "sources" / source_card_markdown_name("alpha.md")
            self.assertTrue(source_path.exists())
            self.assertIn("Original source included: `False`", source_path.read_text(encoding="utf-8"))

    def test_failed_file_card_uses_fallback_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            output_root = Path(tmp) / "output"
            state_root = Path(tmp) / "state"
            telemetry_root = Path(tmp) / "telemetry"
            (corpus_root / "notes").mkdir(parents=True)
            (corpus_root / "notes" / "alpha.md").write_text("# Alpha\n", encoding="utf-8")

            def fake_chat(_provider: str, _base_url: str, _api_key: str, _model: str, messages: list[dict[str, Any]], **_kwargs: Any) -> str:
                prompt = messages[-1]["content"]
                if "SOURCE_MARKDOWN_EXCERPT" in prompt:
                    raise TimeoutError("timed out")
                if "BATCH_SUMMARIES_JSON" in prompt:
                    return json.dumps({"corpus_summary": "Fallback corpus", "wiki_sets": [], "confidence": 0.3})
                return json.dumps({"name": "Batch 1", "summary": "Fallback batch", "confidence": 0.3})

            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
                analysis_model="mock-analysis",
                generation_model="mock-generation",
                review_model="mock-review",
                synthesis_mode="map_reduce",
                card_mode="sampled",
                enable_quality_judge=False,
            )
            with patch("wikimaker_runner.preflight_llm_endpoint", return_value={}), patch("wikimaker_cards._chat_completions", side_effect=fake_chat):
                result = run(config)
            self.assertEqual(result["scan"]["total_files"], 1)
            card_payload = json.loads(next((state_root / "cards").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(card_payload["card"]["source_quality"], "llm_failed")
            self.assertTrue((output_root / "sources" / source_card_markdown_name("notes/alpha.md")).exists())

    def test_source_stub_names_are_sanitized_for_weird_paths(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            corpus_root = Path(tmp) / "corpus"
            output_root = Path(tmp) / "output"
            state_root = Path(tmp) / "state"
            telemetry_root = Path(tmp) / "telemetry"
            config = WikiMakerConfig(
                corpus_root=corpus_root,
                output_root=output_root,
                state_root=state_root,
                telemetry_root=telemetry_root,
            )
            scan = {
                "corpus_root": str(corpus_root),
                "files": {
                    "notes/weird:name?.md": {
                        "path": "notes/weird:name?.md",
                        "title": "Weird",
                        "sha256": "abc",
                        "size": 9,
                        "mtime_ns": 1,
                        "line_count": 2,
                        "headings": [],
                        "source_links": [],
                        "source_kind": "",
                        "platform": "",
                        "source_url": "",
                        "extracted_at": "",
                    },
                },
            }
            diff = {"added": ["notes/weird:name?.md"], "changed": [], "removed": [], "unchanged": []}
            generation = {
                "source_pages": [
                    {
                        "path": "notes/weird:name?.md",
                        "title": "Weird",
                        "summary": "Weird summary",
                        "source_paths": ["notes/weird:name?.md"],
                    }
                ]
            }
            paths = write_source_stubs(config, scan, diff, generation)
            expected = source_card_markdown_name("notes/weird:name?.md")
            self.assertTrue((output_root / "sources" / expected).exists())

    def test_helper_reset_deletes_only_generated_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            corpus_root = tmp_root / "corpus"
            output_root = tmp_root / "wiki-build" / "output"
            state_root = tmp_root / "wiki-build" / "state"
            telemetry_root = tmp_root / "wiki-build" / "telemetry"
            corpus_root.mkdir(parents=True, exist_ok=True)
            output_root.mkdir(parents=True, exist_ok=True)
            state_root.mkdir(parents=True, exist_ok=True)
            telemetry_root.mkdir(parents=True, exist_ok=True)
            (corpus_root / "keep.md").write_text("# keep\n", encoding="utf-8")
            (output_root / "remove.txt").write_text("generated\n", encoding="utf-8")
            (state_root / "remove.txt").write_text("generated\n", encoding="utf-8")
            (telemetry_root / "remove.txt").write_text("generated\n", encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "WIKIMAKER_CORPUS_ROOT": str(corpus_root),
                    "WIKIMAKER_OUTPUT_ROOT": str(output_root),
                    "WIKIMAKER_STATE_ROOT": str(state_root),
                    "WIKIMAKER_TELEMETRY_ROOT": str(telemetry_root),
                    "WIKIMAKER_ASSUME_YES": "1",
                }
            )
            result = subprocess.run(
                [str(REPO_ROOT / "wikimakerctl.sh"), "reset"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("Reset complete", result.stdout)
            self.assertTrue((corpus_root / "keep.md").exists())
            self.assertFalse(output_root.exists())
            self.assertFalse(state_root.exists())
            self.assertFalse(telemetry_root.exists())

    def test_helper_usage_includes_freshcat_commands(self) -> None:
        result = subprocess.run(
            [str(REPO_ROOT / "wikimakerctl.sh")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("freshcat", result.stdout)
        self.assertIn("freshcat-test", result.stdout)
        helper = (REPO_ROOT / "wikimakerctl.sh").read_text(encoding="utf-8")
        self.assertIn('freshcat --test-limit "${WIKIMAKER_TEST_LIMIT:-10}"', helper)

    def test_source_stub_names_are_bounded_for_long_paths(self) -> None:
        long_rel_path = "a/" + ("verylongsegment" * 12) + "/b/" + ("anotherverylongsegment" * 12) + "/c/" + ("finalsegment" * 12) + ".md"
        stub = _source_stub_name(long_rel_path)
        self.assertLess(len(stub), 160)
        self.assertRegex(stub, r"[0-9a-f]{12}$")


if __name__ == "__main__":
    unittest.main()
