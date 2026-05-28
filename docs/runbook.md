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
- `WIKIMAKER_SYNTHESIS_MODE` — default `llm_only`; do not synthesize links from scan heuristics
- `WIKIMAKER_ENABLE_QUALITY_JUDGE` — `1` to run an aggregate-only quality judge after generation
- `WIKIMAKER_QUALITY_JUDGE_MODEL` — local model for quality judging; defaults to review model
- The default local Ollama endpoint uses localhost, so the code can run without any external LLM dependency

- `WIKIMAKER_USE_ADK` — retained for orchestration settings
- `WIKIMAKER_ENABLE_ADK_TRACING` — `1` to export ADK/OpenTelemetry spans into SQLite
- `WIKIMAKER_ENABLE_ADK_EVAL` — retained for compatibility; local-only mode does not use live ADK eval
- `WIKIMAKER_ADK_TRACE_DB` — path for the ADK trace SQLite database
- `WIKIMAKER_ADK_EVAL_DIR` — directory for ADK evaluation artifacts
- `OPENAI_API_KEY` — key for an OpenAI-compatible backend if you switch back later
- `OSAURUS_API_KEY` — optional alias for `OPENAI_API_KEY`
- Ollama does not need a key unless you put a proxy in front of it
- `OPENAI_BASE_URL` — local OpenAI-compatible endpoint override

### Local Ollama example

```env
WIKIMAKER_PROVIDER=ollama
WIKIMAKER_LLM_API_STYLE=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434
WIKIMAKER_ANALYSIS_MODEL=gemma4:e4b-mlx
WIKIMAKER_GENERATION_MODEL=gemma4:e4b-mlx
WIKIMAKER_REVIEW_MODEL=gemma4:e4b-mlx
WIKIMAKER_SYNTHESIS_MODE=llm_only
WIKIMAKER_ENABLE_QUALITY_JUDGE=1
```

Use your local Ollama models for the stage 1 source-page pass, stage 2 commonality pass, and stage 3 verification pass.

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
- `--enable-quality-judge` / `--no-enable-quality-judge`
- `--quality-judge-model`

## Mac interactive helper

For the default macOS corpus setup, the helper points at your configured corpus and output roots, so you can run it with no extra parameters:

```bash
<repo-root>/wikimakerctl.sh fresh
```

`fresh` is the canonical full rebuild command for your real corpus. It resets generated output/state/telemetry only, keeps the source extracts read-only, prints the chosen corpus/output/state/telemetry/model settings, asks for confirmation, verifies the local Ollama server and model, and then runs in the foreground with live progress.

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
<repo-root>/wikimakerctl.sh fresh
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
./wikimakerctl.sh fresh
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
- writes deterministic source-summary stubs
- stores updated state for the next run

## Current wiki compiler behavior
- classifies model endpoint privacy before LLM use
- applies automatic corpus-kind detection plus optional local prompt-profile overrides
- asks the local LLM for source-page plans, wiki-set synthesis, and verification
- keeps wiki synthesis LLM-only by default; scan heuristics should not invent semantic links
- writes `_llm_quality.md`, which judges only aggregate counts and never sends source text, filenames, titles, or snippets to the judge model
- writes source summaries, wiki sets, topic/entity pages, backlinks, graph data, privacy status, health checks, browser data, telemetry, and state
- preserves generated output separately from the source corpus
