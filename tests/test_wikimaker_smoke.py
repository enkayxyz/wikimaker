from __future__ import annotations

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
from wikimaker_runner import write_source_stubs
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
                            "related_pages": ["notes/b.md"],
                            "used_in": ["Chat set"],
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
                            "related_pages": ["notes/a.md"],
                            "used_in": ["Chat set"],
                            "key_snippets": ["beta snippet"],
                        },
                    ],
                    "wiki_set_pages": [
                        {
                            "name": "Chat set",
                            "purpose": "Chat corpus",
                            "pages": ["Alpha", "Beta"],
                        }
                    ],
                },
                "verification": {"approved": True, "confidence": 0.9},
            }
            views = build_discovery_views(scan, diff, pipeline)
            self.assertEqual(len(views["graph"]["nodes"]), 3)
            self.assertEqual(views["graph"]["nodes"][0]["label"], "Beta")
            self.assertIn("score", views["graph"]["nodes"][0])
            paths = write_discovery_views(config, scan, diff, pipeline)
            self.assertTrue(paths["dashboard"].exists())
            self.assertTrue(paths["stats"].exists())
            self.assertTrue(paths["search"].exists())
            self.assertTrue(paths["graph"].exists())
            self.assertIn("WikiMaker Dashboard", paths["dashboard"].read_text(encoding="utf-8"))
            self.assertIn("WikiMaker Stats", paths["stats"].read_text(encoding="utf-8"))
            self.assertIn("WikiMaker Search Index", paths["search"].read_text(encoding="utf-8"))
            self.assertIn("Alpha", paths["search"].read_text(encoding="utf-8"))
            self.assertIn("Chat set", paths["search"].read_text(encoding="utf-8"))

            browser_path = write_browser_frontend(config, scan, diff, pipeline)
            self.assertTrue(browser_path.exists())
            browser_text = browser_path.read_text(encoding="utf-8")
            self.assertIn("WikiMaker Browser", browser_text)
            self.assertIn("sourceGrid", browser_text)

            source_stubs = write_source_stubs(config, scan, diff, pipeline["generation"])
            self.assertTrue(any(path.name == "notes__a.md" for path in source_stubs))
            stub_path = output_root / "sources" / "notes__a.md"
            self.assertTrue(stub_path.exists())
            stub_text = stub_path.read_text(encoding="utf-8")
            self.assertIn("## Navigation", stub_text)
            self.assertIn("## Topics", stub_text)
            self.assertIn("## Entities", stub_text)


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
            self.assertTrue(any(path.name == expected for path in paths))


if __name__ == "__main__":
    unittest.main()
