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


if __name__ == "__main__":
    unittest.main()
