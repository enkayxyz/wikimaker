# WikiMaker Scaffold Runbook

## Environment variables
Put these in `.env`:

- `WIKIMAKER_CORPUS_ROOT` — root folder containing Markdown source files
- `WIKIMAKER_OUTPUT_ROOT` — where generated wiki output is written
- `WIKIMAKER_STATE_ROOT` — persistent state directory
- `WIKIMAKER_TELEMETRY_ROOT` — telemetry output directory
- `WIKIMAKER_PROVIDER` — logical provider label, usually `ollama`
- `WIKIMAKER_LLM_API_STYLE` — `ollama` for the current scaffold
- `WIKIMAKER_ANALYSIS_MODEL` — model used for stage 1 source-page generation (recommended: your local Gemma 4 E4B MLX model)
- `WIKIMAKER_REVIEW_MODEL` — model used for stage 3 verification
- `WIKIMAKER_SYNTHESIS_MODE` — default `adk_workflow`; use ADK-owned source-card, batch, global, quality, and render stages
- `WIKIMAKER_CARD_MODE` — default `metadata`; use `sampled`, `deep`, or `original` only when source text enrichment is explicitly needed
- `WIKIMAKER_LLM_BATCH_SIZE` — source-card summaries per merge batch; default `50`
- `WIKIMAKER_LLM_DEBUG` — `1` prints safe `llm start`, `llm done`, and `llm fail` lines while calls run
- `WIKIMAKER_LLM_PREFLIGHT_TIMEOUT` — preflight timeout in seconds; default `20`
- `WIKIMAKER_LLM_FILE_TIMEOUT` — per-file card timeout in seconds; default `120`
- `WIKIMAKER_LLM_BATCH_TIMEOUT` — batch merge timeout in seconds; default `180`
- `WIKIMAKER_LLM_GLOBAL_TIMEOUT` — global merge timeout in seconds; default `300`
- `WIKIMAKER_LLM_QUALITY_TIMEOUT` — quality judge timeout in seconds; default `120`
- `WIKIMAKER_TEST_LIMIT` — limit processing to the first N sorted Markdown files for quick debugging
- `WIKIMAKER_FORCE_REPROCESS` — `1` to regenerate all per-file cards
- `WIKIMAKER_FORCE_PATHS` — comma-separated relative paths or globs to regenerate selected per-file cards
- `WIKIMAKER_ENABLE_QUALITY_JUDGE` — `1` to run an aggregate-only quality judge after generation
- `WIKIMAKER_QUALITY_JUDGE_MODEL` — local model for quality judging; defaults to review model
- The default local Ollama endpoint uses localhost, so the code can run without any external LLM dependency

- `WIKIMAKER_USE_ADK` — `1` for the ADK-driven workflow path
- `WIKIMAKER_ENABLE_ADK_TRACING` — `1` to export ADK/OpenTelemetry spans into SQLite
- `WIKIMAKER_ENABLE_ADK_EVAL` — retained for compatibility; local-only mode does not use live ADK eval
- `WIKIMAKER_ADK_TRACE_DB` — path for the ADK trace SQLite database
- `WIKIMAKER_ADK_EVAL_DIR` — directory for ADK evaluation artifacts
- `OPENAI_API_KEY` — key for an OpenAI-compatible backend if you switch back later
- `OSAURUS_API_KEY` — optional alias for `OPENAI_API_KEY`
- Ollama does not need a key unless you put a proxy in front of it
- `OPENAI_BASE_URL` — OpenAI-compatible endpoint for this machine; use `http://127.0.0.1:11434` only when Ollama runs locally, otherwise point it at the Ollama host/IP for the test machine

### Local Ollama example

```env
WIKIMAKER_PROVIDER=ollama
WIKIMAKER_LLM_API_STYLE=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434
WIKIMAKER_ANALYSIS_MODEL=gemma4:e4b-mlx
WIKIMAKER_GENERATION_MODEL=gemma4:e4b-mlx
WIKIMAKER_REVIEW_MODEL=gemma4:e4b-mlx
WIKIMAKER_USE_ADK=1
WIKIMAKER_SYNTHESIS_MODE=adk_workflow
WIKIMAKER_CARD_MODE=metadata
WIKIMAKER_LLM_DEBUG=1
WIKIMAKER_LLM_BATCH_SIZE=50
WIKIMAKER_LLM_PREFLIGHT_TIMEOUT=20
WIKIMAKER_LLM_FILE_TIMEOUT=120
WIKIMAKER_LLM_BATCH_TIMEOUT=180
WIKIMAKER_LLM_GLOBAL_TIMEOUT=300
WIKIMAKER_LLM_QUALITY_TIMEOUT=120
WIKIMAKER_ENABLE_QUALITY_JUDGE=1
```

Use your local Ollama models behind the ADK workflow stage boundary for SourceCard enrichment, batch summaries, the global merge pass, and optional aggregate quality judging.

If Ollama is running on another machine, replace `127.0.0.1` with that machine's IP or hostname in `OPENAI_BASE_URL`.

WikiMaker requires Python 3.11 or newer. Use the dedicated `wikimaker` conda environment.

Create/update runtime and test dependencies with:

```bash
cd <repo-root>
conda env create -f environment.yml
conda run -n wikimaker python -m pip install -r requirements.txt
```

For a new test machine, create machine-local settings from the template:

```bash
cp .env.example .env
$EDITOR .env
```

## Command

```bash
conda run -n wikimaker python wikimaker.py --corpus-root /path/to/corpus
```

Optional flags may override env vars:
- `--output-root`
- `--state-root`
- `--telemetry-root`
- `--provider`
- `--analysis-model`
- `--generation-model`
- `--review-model`
- `--use-adk`
- `--dry-run`
- `--allow-remote-llm`
- `--prompt-profile`
- `--synthesis-mode`
- `--card-mode`
- `--llm-batch-size`
- `--test-limit`
- `--force-reprocess`
- `--force-path`
- `--enable-quality-judge` / `--no-enable-quality-judge`
- `--quality-judge-model`

## Mac interactive helper

For the default macOS corpus setup, the helper points at your configured corpus and output roots, so you can run it with no extra parameters:

```bash
<repo-root>/wikimakerctl.sh freshcat
```

`freshcat` is the canonical monitored rebuild command for your real corpus. It resets generated output/state/telemetry only, keeps the source extracts read-only, prints the chosen corpus/output/state/telemetry/model settings, asks for confirmation, verifies the local Ollama server and model before scanning, then runs in the foreground while teeing all output to `/tmp/wikimaker.log`.

For quick debugging without waiting on the whole corpus:

```bash
<repo-root>/wikimakerctl.sh freshcat-test
```

`freshcat-test` is equivalent to `freshcat --test-limit 10` unless `WIKIMAKER_TEST_LIMIT` is set. LLM call details are written to `telemetry/llm_calls.jsonl`, and the active or most recent call is written to `telemetry/current.json`. `wikimakerctl.sh status` prints both.

After a successful build, inspect:
- `output/_privacy.md`
- `output/_llm_quality.md`
- `output/_health.md`
- `output/browser/index.html`
- `output/browser/data.json`

Remote model endpoints are refused unless `WIKIMAKER_ALLOW_REMOTE_LLM=1` or `--allow-remote-llm` is set. Use that only after reviewing the leak boundary.

Background mode and logs:

```bash
<repo-root>/wikimakerctl.sh start
<repo-root>/wikimakerctl.sh logs
<repo-root>/wikimakerctl.sh logs -f
<repo-root>/wikimakerctl.sh stop
```

To wipe generated wiki output and start over cleanly, use:

```bash
<repo-root>/wikimakerctl.sh reset
<repo-root>/wikimakerctl.sh freshcat
<repo-root>/wikimakerctl.sh fresh-start
```

Reset semantics:
- only deletes the generated `output/`, `state/`, and `telemetry/` roots under the common `wiki-build/` parent
- never touches the source corpus root
- stops a running WikiMaker process first if needed
- asks for a typed confirmation phrase unless `WIKIMAKER_ASSUME_YES=1` is set
- leaves `/tmp/wikimaker.log` alone; `start` truncates it on the next run

The helper pins the local Ollama endpoint to `http://127.0.0.1:11434`, uses the `wikimaker` conda env by default, and writes its PID/log to `/tmp`. It is intentionally Mac/local agent-specific and hardcodes `$HOME` defaults. Override with `WIKIMAKER_*` environment variables or use the Python CLI with explicit roots for other machines.

## Public export

Before publishing, create a clean export without git history, `.env`, generated outputs, caches, logs, databases, or archives:

```bash
cd <repo-root>
./sanitize_public_release.sh export /tmp/wikimaker-public
cd /tmp/wikimaker-public
./sanitize_public_release.sh audit
```

Initialize the new public repository from that export, not from the old checkout:

```bash
git init
git add .
git commit -m "Initial sanitized WikiMaker release"
git remote add origin <NEW_SANITIZED_REPO_URL>
git push -u origin main
```

Minimum validation on the receiving machine:

```bash
./sanitize_public_release.sh audit
conda run -n wikimaker python wikimaker.py --help
conda run -n wikimaker python -m unittest tests.test_wikimaker_smoke -v
conda run -n wikimaker python -m compileall -q code tests
./wikimakerctl.sh status
./wikimakerctl.sh freshcat-test
./wikimakerctl.sh freshcat
```

Corpus families currently expected:
- WhatsApp extracts
- AI conversations from different chats/tools
- financial documents from Markdown extraction

Planned corpus families already have built-in prompt profiles: contacts, calendars, meeting notes, recording transcripts, emails, iMessages, personal notes, Google Docs, code repositories, project artifacts, index/ledger pages, and mixed notes.

## What the scaffold does
- loads configuration
- scans the corpus recursively
- computes file hashes
- detects changed/new/removed files against the last snapshot
- writes a change report
- writes telemetry
- writes canonical SourceCard JSON and matching SourceCard Markdown pages
- stores updated state for the next run

## Current wiki compiler behavior
- classifies model endpoint privacy before LLM use
- applies automatic corpus-kind detection plus optional local prompt-profile overrides
- runs ADK workflow stages for source-card construction, wiki-set synthesis, global merge, quality, and deterministic rendering
- keeps wiki synthesis LLM-only by default; scan heuristics should not invent semantic links
- writes `_llm_quality.md`, which judges only aggregate counts and never sends source text, filenames, titles, or snippets to the judge model
- writes source summaries, wiki sets, topic/entity pages, backlinks, graph data, privacy status, health checks, browser data, telemetry, and state
- preserves generated output separately from the source corpus
