# WikiMaker Repository

WikiMaker is a local-first provenance compiler that turns a recursive Markdown corpus into an evolving wiki.

This repository also contains WAXtrctr, the WhatsApp iPhone-backup extractor that produces the Markdown corpus WikiMaker consumes.

## What WikiMaker does

WikiMaker:
- scans a recursive tree of Markdown source files
- treats the source corpus as read-only
- generates source-summary pages and wiki-set pages
- preserves provenance and original URLs when present
- keeps duplicates, evolution, and contradictions explicit
- maintains folder-level `gist.md` and `ledger.md` memory
- writes telemetry, change reports, indexes, and a local browser UI

## Repository layout

- `wikimaker.py` — repo-root launcher
- `code/` — implementation modules
- `docs/` — project docs, plans, and handoff material
- `skill/` — the WikiMaker skill mirror/source files
- `tests/` — smoke and integration coverage
- `wikimakerctl.sh` — macOS helper for run/start/stop/logs/reset/fresh
- `whatsapp_backup_extractor.py` — WAXtrctr launcher
- `waxtrctr.py` — alias launcher for WAXtrctr

## Architecture

Current stack:
- Python 3
- Google ADK 2 for orchestration and observability
- local OpenAI-compatible API surface for model calls
- Ollama on the LAN as the default inference backend
- static Markdown outputs plus a local browser frontend
- pytest / unittest smoke coverage
- optional local ADK tracing and evaluation hooks

Important implementation facts:
- ADK import namespace: `google.adk`
- working package line in this environment: `google-adk==2.0.0b1`
- local inference endpoint: `http://192.168.86.11:11434`
- real-corpus runs are intentionally local-only
- there is no deterministic non-AI fallback wiki-generation path

Main code paths:
- `code/wikimaker_scanner.py`
- `code/wikimaker_openai.py`
- `code/wikimaker_discovery.py`
- `code/wikimaker_browser.py`
- `code/wikimaker_runner.py`
- `code/wikimaker_observability.py`
- `code/wikimaker_state.py`
- `code/wikimaker_telemetry.py`
- `code/wikimaker_config.py`

## Product boundary

Non-negotiables:
- source corpus stays read-only
- provenance must remain visible
- output must live in a separate tree from the source corpus
- duplicates, evolution, and contradictions must be surfaced, not hidden
- folder-level `gist.md` and `ledger.md` are required
- local-first behavior is the default
- real-corpus runs should stay on the local Ollama path

WikiMaker is a provenance-first compiler, not a mutable note browser.

## Model and configuration

Suggested environment variables:
- `WIKIMAKER_CORPUS_ROOT`
- `WIKIMAKER_OUTPUT_ROOT`
- `WIKIMAKER_STATE_ROOT`
- `WIKIMAKER_TELEMETRY_ROOT`
- `WIKIMAKER_PROVIDER`
- `WIKIMAKER_LLM_API_STYLE`
- `WIKIMAKER_ANALYSIS_MODEL`
- `WIKIMAKER_GENERATION_MODEL`
- `WIKIMAKER_REVIEW_MODEL`
- `WIKIMAKER_USE_ADK`
- `WIKIMAKER_ENABLE_ADK_TRACING`
- `WIKIMAKER_ENABLE_ADK_EVAL`
- `WIKIMAKER_ADK_TRACE_DB`
- `WIKIMAKER_ADK_EVAL_DIR`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY` or `OSAURUS_API_KEY` if using an OpenAI-compatible backend instead of plain Ollama

Recommended local setup:
- provider: `ollama`
- API style: `ollama`
- base URL: `http://192.168.86.11:11434`
- analysis/generation/review model: your local Gemma 4 E4B model, if available

## How to run

Basic run:
```bash
python wikimaker.py --corpus-root <path-to-markdown-corpus>
```

Dry run:
```bash
python wikimaker.py \
  --corpus-root <path-to-markdown-corpus> \
  --dry-run
```

With explicit roots:
```bash
python wikimaker.py \
  --corpus-root <path-to-markdown-corpus> \
  --output-root <path-to-output> \
  --state-root <path-to-state> \
  --telemetry-root <path-to-telemetry>
```

Mac helper:
```bash
./wikimakerctl.sh run
./wikimakerctl.sh start
./wikimakerctl.sh logs
./wikimakerctl.sh reset
./wikimakerctl.sh fresh
./wikimakerctl.sh fresh-start
```

## What the outputs contain

Common output paths:
- `_change_report.md` — run summary and scan details
- `_root_index.md` — top-level wiki index
- `_dashboard.md` — corpus overview and most-connected pages
- `_stats.md` — corpus health and counts
- `_search.md` — jump table for source pages and wiki sets
- `_graph.json` — graph data for future UI layers
- `browser/index.html` — local browser frontend
- `sources/` — one source-summary page per Markdown file
- `wiki-sets/` — wiki-set pages and indexes
- `folders/` — folder-level `gist.md` and `ledger.md`
- `state/corpus_snapshot.json` — change tracking snapshot
- `telemetry/latest.json` — telemetry summary

## Documentation

- `docs/requirements.md` — product requirements and acceptance criteria
- `docs/runbook.md` — configuration and runbook
- `docs/wiki-os-borrowing-plan.md` — what to borrow from wiki-os and what to avoid
- `docs/plans/wiki-os-next-stage-analysis.md` — next-stage analysis and UI/AI gap notes
- `docs/plans/wiki-os-next-stage-implementation-plan.md` — task-by-task implementation plan
- `docs/handover-next-agent.md` — handoff document for the next agent
- `skill/SKILL.md` — WikiMaker skill source

## WAXtrctr

WAXtrctr is the WhatsApp iPhone-backup extractor in this repo.

It is designed to:
- extract chat data from iPhone backups
- preserve provenance and raw source details
- emit readable transcript-first output for WikiMaker ingestion
- keep append-only history when run incrementally

Typical entry points:
- `python whatsapp_backup_extractor.py`
- `python waxtrctr.py`

## Current product state

What works now:
- recursive Markdown scanning
- frontmatter/title/link extraction
- corpus-kind inference
- local LLM config validation and hard-fail behavior for non-local endpoints
- prompt schemas for analysis, generation, and verification
- source-summary stubs
- root index, dashboard, stats, search, graph, and browser outputs
- telemetry and change-report generation
- optional ADK tracing and local eval hooks
- discovery views and browser ranking for browsing the generated wiki
- smoke tests covering config, scanning, prompts, discovery, browser, and telemetry

What still needs stronger work:
- browser calmness and hierarchy
- corpus-aware synthesis quality
- backlinks and related-page surfacing
- distinguishing content pages from navigation pages
- better ranking so substantive pages appear before scaffolding

## Wiki-os guidance

WikiMaker should borrow good discovery and navigation ideas from wiki-os, but not merge the full codebase.

Borrow:
- cleaner home/dashboard patterns
- persistent search and fast navigation
- relationship surfacing
- graph and stats views
- stronger taxonomy discipline

Do not borrow:
- remote fetch defaults
- mutable note-browser trust model
- hidden outbound traffic
- a full repo/stack merge

## Handoff

If you are picking up the next stage, start here:
- `docs/handover-next-agent.md`

That handoff should be read before changing architecture or UI direction.
