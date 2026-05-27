from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from wikimaker_config import WikiMakerConfig
from wikimaker_discovery import build_discovery_views, write_discovery_views, _source_stub_name
from wikimaker_browser import write_browser_frontend
from wikimaker_openai import SourcePagePlan, AnalysisPlan, GenerationPlan, _require_local_llm_config, _analysis_prompt, _generation_prompt, _compact_scan_for_prompt, _verification_prompt
from wikimaker_runner import write_source_stubs, write_root_index
from wikimaker_scanner import scan_corpus
from wikimaker_state import diff_snapshots
from wikimaker_telemetry import build_telemetry


class WikiMakerSmokeTests(unittest.TestCase):
    def test_config_defaults_from_corpus_root(self) -> None:
        config = WikiMakerConfig.from_env_and_args(corpus_root="/tmp/corpus-root")
        self.assertEqual(config.corpus_root, Path("/tmp/corpus-root"))
        self.assertEqual(config.output_root, Path("/tmp/corpus-root/wiki-build/output"))
        self.assertEqual(config.state_root, Path("/tmp/corpus-root/wiki-build/state"))
        self.assertEqual(config.telemetry_root, Path("/tmp/corpus-root/wiki-build/telemetry"))

    def test_local_llm_config_rejects_non_local_endpoints(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Refusing non-local LLM endpoint"):
            _require_local_llm_config({"provider": "ollama", "openai_base_url": "http://example.com:11434"})

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
                "chat.md": """# Team chat

Conversation notes from Alice and Bob.
Alice: can we ship this today?
Bob: yes, after lunch.
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
            }
            for rel_path, content in files.items():
                path = corpus_root / rel_path
                path.write_text(content, encoding="utf-8")

            scan = scan_corpus(corpus_root)
            kinds = {record.get("corpus_kind") for record in scan["files"].values() if isinstance(record, dict)}
            self.assertIn("chats", kinds)
            self.assertIn("bills_documents", kinds)
            self.assertIn("project_artifacts", kinds)
            self.assertIn("index_ledger_pages", kinds)
            self.assertIn("mixed_notes", kinds)

            compact = _compact_scan_for_prompt(scan, {"added": [], "changed": [], "removed": [], "unchanged": []})
            self.assertGreaterEqual(len(compact["corpus_kinds"]), 5)
            analysis_prompt = _analysis_prompt(compact)
            self.assertIn("Detected corpus kinds:", analysis_prompt)
            self.assertIn("Chats:", analysis_prompt)
            self.assertIn("Bills/documents:", analysis_prompt)
            self.assertIn("Project artifacts:", analysis_prompt)
            self.assertIn("Index/ledger pages:", analysis_prompt)
            self.assertIn("Mixed notes:", analysis_prompt)

            analysis = AnalysisPlan(corpus_kinds=compact["corpus_kinds"])
            generation_prompt = _generation_prompt(compact, analysis)
            self.assertIn("Keep chats, bills/documents, mixed notes, project artifacts, and index/ledger pages separated", generation_prompt)
            self.assertIn("Detected corpus kinds:", generation_prompt)
            generation_result = GenerationPlan()
            verification_prompt = _verification_prompt(compact, analysis, generation_result)
            self.assertIn("Corpus-kind instructions:", verification_prompt)

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
            self.assertIn("| [Beta](sources/notes__b.md) |", dashboard_text)
            self.assertLess(dashboard_text.index("[Beta](sources/notes__b.md)"), dashboard_text.index("[Alpha](sources/notes__a.md)"))
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
            self.assertIn("WikiMaker Browser", browser_text)
            self.assertIn("sourceGrid", browser_text)
            self.assertIn("libraryGrid", browser_text)
            self.assertIn("themeToggle", browser_text)
            self.assertIn("localStorage", browser_text)
            self.assertIn("Most connected pages", browser_text)
            self.assertIn("Recently changed", browser_text)
            self.assertIn("Wiki sets", browser_text)
            self.assertIn("Source library", browser_text)
            self.assertIn("semantic pages", browser_text)
            self.assertIn("library pages", browser_text)
            self.assertIn("Links to", browser_text)
            self.assertIn("Linked from", browser_text)

            source_stubs = write_source_stubs(config, scan, diff, pipeline["generation"])
            self.assertTrue(any(path.name == "notes__a.md" for path in source_stubs))
            stub_path = output_root / "sources" / "notes__a.md"
            self.assertTrue(stub_path.exists())
            stub_text = stub_path.read_text(encoding="utf-8")
            self.assertIn("## Navigation", stub_text)
            self.assertIn("## Topics", stub_text)
            self.assertIn("## Entities", stub_text)

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
            self.assertIn("## Source pages", root_text)
            self.assertIn("| Title | Provenance | Source markdown | Stub | External/source link |", root_text)
            self.assertIn("Knowledge Page, chat, whatsapp", root_text)
            self.assertIn("Thread Page, chat, whatsapp", root_text)
            self.assertIn("`notes/alpha.md`", root_text)
            self.assertIn("[source stub](sources/notes__alpha.md)", root_text)
            self.assertIn("https://example.com/alpha", root_text)
            self.assertIn("https://example.com/beta-thread", root_text)

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
            expected = _source_stub_name("notes/weird:name?.md")
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
                ["/Users/enkay/dev/wikimaker/wikimakerctl.sh", "reset"],
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

    def test_source_stub_names_are_bounded_for_long_paths(self) -> None:
        long_rel_path = "a/" + ("verylongsegment" * 12) + "/b/" + ("anotherverylongsegment" * 12) + "/c/" + ("finalsegment" * 12) + ".md"
        stub = _source_stub_name(long_rel_path)
        self.assertLess(len(stub), 160)
        self.assertRegex(stub, r"[0-9a-f]{12}$")


if __name__ == "__main__":
    unittest.main()
