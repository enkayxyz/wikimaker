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
- Python 3.11+
- Google ADK 2 workflow orchestration and observability
- local OpenAI-compatible API surface for model calls
- Ollama on localhost as the default inference backend
- static Markdown outputs plus a local browser frontend
- pytest / unittest smoke coverage
- local ADK tracing and evaluation hooks

Important implementation facts:
- ADK import namespace: `google.adk`
- pinned package line in this environment: `google-adk==2.1.0`
- local inference endpoint: `http://127.0.0.1:11434`
- Python runtime: 3.11 or newer
- real-corpus runs are intentionally local-only
- ADK workflow synthesis owns scan, source-card, batch, global, quality, and render stages
- source cards are canonical and render to both `state/cards/*.json` and `output/sources/*.md`
- default source-card mode is metadata-first; original/full source text is opt-in with `WIKIMAKER_CARD_MODE=sampled|deep|original`
- `map_reduce` and `llm_only` are retained as legacy debug modes; `coverage_fallback` remains scan-only/offline

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
- `WIKIMAKER_ALLOW_REMOTE_LLM`
- `WIKIMAKER_PROMPT_PROFILE`
- `WIKIMAKER_SYNTHESIS_MODE` — default `adk_workflow`; `map_reduce` and `llm_only` are legacy debug modes
- `WIKIMAKER_CARD_MODE` — default `metadata`; use `sampled`, `deep`, or `original` only for opt-in source-text enrichment
- `WIKIMAKER_LLM_BATCH_SIZE`
- `WIKIMAKER_LLM_DEBUG` — `1` prints safe `llm start/done/fail` progress lines
- `WIKIMAKER_LLM_PREFLIGHT_TIMEOUT`
- `WIKIMAKER_LLM_FILE_TIMEOUT`
- `WIKIMAKER_LLM_BATCH_TIMEOUT`
- `WIKIMAKER_LLM_GLOBAL_TIMEOUT`
- `WIKIMAKER_LLM_QUALITY_TIMEOUT`
- `WIKIMAKER_TEST_LIMIT` — limit runs to the first N sorted Markdown files for quick debugging
- `WIKIMAKER_FORCE_REPROCESS`
- `WIKIMAKER_FORCE_PATHS`
- `WIKIMAKER_ENABLE_QUALITY_JUDGE`
- `WIKIMAKER_QUALITY_JUDGE_MODEL`
- `OPENAI_BASE_URL` - OpenAI-compatible endpoint for this machine; use `127.0.0.1` only when Ollama is local
- `OPENAI_API_KEY` or `OSAURUS_API_KEY` if using an OpenAI-compatible backend instead of plain Ollama

Recommended local setup:
- conda env: `wikimaker`
- provider: `ollama`
- API style: `ollama`
- base URL: `http://127.0.0.1:11434` when Ollama runs on the same machine
- analysis/generation/review model: your local Gemma 4 E4B model, if available
- synthesis mode: `adk_workflow` for ADK-owned source-card, batch, global, quality, and render stages

## How to run

Basic run:
```bash
conda run -n wikimaker python wikimaker.py --corpus-root <path-to-markdown-corpus>
```

Create/update the environment:

```bash
conda env create -f environment.yml
conda run -n wikimaker python -m pip install -r requirements.txt
```

Machine-local settings live in `.env`, which is intentionally ignored. Start from the public template:

```bash
cp .env.example .env
$EDITOR .env
```

## Public Export And Test Machine Setup

Do not publish old git history if it contains private paths, LAN details, or corpus names. Create a sanitized export and initialize a fresh public repository from that export.

Create the sanitized export:

```bash
cd <repo-root>
./sanitize_public_release.sh export /tmp/wikimaker-public
cd /tmp/wikimaker-public
./sanitize_public_release.sh audit
git init
git add .
git commit -m "Initial sanitized WikiMaker release"
git remote add origin <NEW_SANITIZED_REPO_URL>
git push -u origin main
```

On a test machine, copy only `.env.example` to `.env`, then edit `.env` for that machine's local endpoint, model names, corpus root, and output roots:

```bash
git clone <NEW_SANITIZED_REPO_URL> wikimaker
cd wikimaker

conda env create -f environment.yml
conda run -n wikimaker python -m pip install -r requirements.txt

cp .env.example .env
$EDITOR .env

./sanitize_public_release.sh audit

conda run -n wikimaker python wikimaker.py --help
conda run -n wikimaker python -m unittest tests.test_wikimaker_smoke -v
conda run -n wikimaker python -m compileall -q code tests

./wikimakerctl.sh status
./wikimakerctl.sh freshcat-test
./wikimakerctl.sh freshcat
```

Dry run:
```bash
conda run -n wikimaker python wikimaker.py \
  --corpus-root <path-to-markdown-corpus> \
  --dry-run
```

With explicit roots:
```bash
conda run -n wikimaker python wikimaker.py \
  --corpus-root <path-to-markdown-corpus> \
  --output-root <path-to-output> \
  --state-root <path-to-state> \
  --telemetry-root <path-to-telemetry>
```

Mac helper:
```bash
<repo-root>/wikimakerctl.sh fresh
./wikimakerctl.sh run
./wikimakerctl.sh start
./wikimakerctl.sh logs
./wikimakerctl.sh reset
./wikimakerctl.sh fresh
./wikimakerctl.sh fresh-start
```

For the real default corpus, `wikimakerctl.sh freshcat` is the monitored full rebuild path: it resets only generated output/state/telemetry, never the source extracts, then runs in the foreground while teeing all output to `/tmp/wikimaker.log`. For debugging, `wikimakerctl.sh freshcat-test` runs the same flow with `--test-limit 10`.

`wikimakerctl.sh` is intentionally tuned for the primary macOS/local agent test setup and hardcodes `$HOME` defaults. For another machine, either set the `WIKIMAKER_*` environment variables or call `conda run -n wikimaker python wikimaker.py ...` with explicit roots.

## What the outputs contain

Common output paths:
- `_change_report.md` — run summary and scan details
- `_root_index.md` — top-level wiki index
- `_dashboard.md` — corpus overview and most-connected pages
- `_stats.md` — corpus health and counts
- `_search.md` — jump table for source pages and wiki sets
- `_graph.json` — graph data for future UI layers
- `_privacy.md` — model endpoint and browser network boundary report
- `_llm_quality.md` — aggregate-only LLM output quality report
- `_health.md` — wiki lint/health findings
- `browser/index.html` — local browser frontend
- `sources/` — one SourceCard Markdown page per Markdown file, sharing its id/data with `state/cards/*.json`
- `wiki-sets/` — wiki-set pages and indexes
- `folders/` — folder-level `gist.md` and `ledger.md`
- `state/corpus_snapshot.json` — change tracking snapshot
- `telemetry/latest.json` — telemetry summary

## Prompt profiles

WikiMaker automatically assigns a corpus kind to each Markdown file, then applies a prompt profile. Built-in profiles cover the current corpus buckets (`whatsapp_chats`, `ai_conversations`, and `financial_documents`) plus planned 360-degree sources: contacts, calendars, meeting notes, recording transcripts, emails, iMessages, personal notes, Google Docs, code repositories, project artifacts, index/ledger pages, and mixed notes. Legacy `chats` and `bills_documents` profile names remain as aliases.

To override behavior, add `wikimaker.profiles.json` or `wikimaker.profiles.yaml` next to the corpus root, or set `WIKIMAKER_PROMPT_PROFILE`.

```json
{
  "profiles": {
    "family_archive": {
      "corpus_kind": "whatsapp_chats",
      "guidance": "Emphasize people, dates, decisions, relationships, and unresolved follow-ups.",
      "extraction_fields": ["people", "dates", "decisions", "relationships"]
    }
  },
  "folder_rules": [
    {"path": "whatsapp", "profile": "family_archive", "corpus_kind": "whatsapp_chats"},
    {"path": "ai-conversations", "profile": "ai_conversations", "corpus_kind": "ai_conversations"},
    {"path": "financial", "profile": "financial_documents", "corpus_kind": "financial_documents"}
  ]
}
```

## Privacy boundary

WikiMaker classifies the model endpoint before running:
- `local` means this machine
- `lan` means a private-network endpoint
- `remote` means DNS/public internet risk

Remote endpoints are refused unless `WIKIMAKER_ALLOW_REMOTE_LLM=1` or `--allow-remote-llm` is set. The generated browser remains static: no remote fonts, image lookups, analytics, or hidden fetches.

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
- canonical SourceCard JSON and Markdown pages
- root index, dashboard, stats, search, graph, and browser outputs
- telemetry and change-report generation
- ADK workflow stage telemetry, tracing, and local eval hooks
- discovery views and browser ranking for browsing the generated wiki
- smoke tests covering config, scanning, prompts, discovery, browser, and telemetry

What still needs stronger work:
- real-corpus evaluation of profile-guided synthesis quality
- deeper visual QA of the WikiOS-inspired browser experience
- larger-corpus performance tuning for graph and health checks

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
