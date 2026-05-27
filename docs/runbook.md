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
- The local Ollama endpoint runs on your LAN, so the code can talk to it without any external LLM dependency

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
OPENAI_BASE_URL=http://192.168.86.11:11434
WIKIMAKER_ANALYSIS_MODEL=gemma4:e4b-mlx
WIKIMAKER_GENERATION_MODEL=gemma4:e4b-mlx
WIKIMAKER_REVIEW_MODEL=gemma4:e4b-mlx
```

Use your local Ollama models for the stage 1 source-page pass, stage 2 commonality pass, and stage 3 verification pass.

## Command

```bash
python wikimaker.py --corpus-root /path/to/corpus
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

## Mac interactive helper

For the FileAnalyze corpus setup on macOS, the helper now defaults to your real corpus and output roots, so you can run it with no extra parameters:

```bash
/Users/enkay/dev/wikimaker/wikimakerctl.sh run
```

It prints the chosen corpus/output/state/telemetry/model settings, asks for confirmation, verifies the local Ollama server and model, and then runs in the foreground with live progress.

Background mode and logs:

```bash
/Users/enkay/dev/wikimaker/wikimakerctl.sh start
/Users/enkay/dev/wikimaker/wikimakerctl.sh logs
/Users/enkay/dev/wikimaker/wikimakerctl.sh logs -f
/Users/enkay/dev/wikimaker/wikimakerctl.sh stop
```

To wipe generated wiki output and start over cleanly, use:

```bash
/Users/enkay/dev/wikimaker/wikimakerctl.sh reset
/Users/enkay/dev/wikimaker/wikimakerctl.sh fresh
/Users/enkay/dev/wikimaker/wikimakerctl.sh fresh-start
```

Reset semantics:
- only deletes the generated `output/`, `state/`, and `telemetry/` roots under the common `wiki-build/` parent
- never touches the source corpus root
- stops a running WikiMaker process first if needed
- asks for a typed confirmation phrase unless `WIKIMAKER_ASSUME_YES=1` is set
- leaves `/tmp/wikimaker.log` alone; `start` truncates it on the next run

The helper pins the local Ollama endpoint to `http://192.168.86.11:11434`, uses the `FileAnalyze` conda env, and writes its PID/log to `/tmp`.

## What the scaffold does
- loads configuration
- scans the corpus recursively
- computes file hashes
- detects changed/new/removed files against the last snapshot
- writes a change report
- writes telemetry
- writes deterministic source-summary stubs
- stores updated state for the next run

## What comes later
- ADK graph wiring for full orchestration
- LLM-based topic inference
- full wiki synthesis
- contradiction and evolution analysis
- incremental page reorganization
