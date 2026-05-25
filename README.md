# WikiMaker Project

Canonical WikiMaker project workspace.

Location:
- `/Users/enkay/dev/wikimaker`

Main pieces:
- `wikimaker.py` — project-root launcher
- `code/` — implementation files
- `docs/` — project docs
- `skill/` — skill mirror/source files

WAXtrctr:
- the WhatsApp iPhone-backup extractor product in this repo
- produces a chat-first, human-readable corpus with lossless provenance
- product doc: `docs/waxtrctr.md`
- default launcher: `python /Users/enkay/dev/wikimaker/whatsapp_backup_extractor.py`
- alias launcher: `python /Users/enkay/dev/wikimaker/waxtrctr.py`

Environment:
- Copy `.env.example` to `.env`
- Put your local inference config in `/Users/enkay/dev/wikimaker/.env`
- Set `OPENAI_BASE_URL=http://192.168.86.11:11434`
- Set `WIKIMAKER_PROVIDER=ollama`
- Set `WIKIMAKER_LLM_API_STYLE=ollama`
- Set `WIKIMAKER_ANALYSIS_MODEL=gemma4:e4b-mlx`
- No API key is needed for plain Ollama
- Install dependencies with `python -m pip install -r /Users/enkay/dev/wikimaker/requirements.txt`

What it expects:
- A recursive folder tree of Markdown files
- Read-only source data
- A separate output folder for generated wiki artifacts
- Optional CSV metadata can stay beside the corpus as reference, but the current runner uses the Markdown tree as the primary input
- If your corpus contains both bills and WhatsApp extracts, keep them under one parent corpus root; WikiMaker will split them into separate wiki sets and cross-link shared entities

Suggested input for your mail archive:
- Markdown corpus: `/Users/enkay/dev/FileAnalyze/MDExtract/data`
- If your extracted Markdown lives in a subfolder, point `--corpus-root` at the folder that contains the `.md` files

Recommended first run inside your conda env:
```bash
conda activate FileAnalyze
python /Users/enkay/dev/wikimaker/wikimaker.py \
  --corpus-root /Users/enkay/dev/FileAnalyze/MDExtract/data \
  --output-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/output \
  --state-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/state \
  --telemetry-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/telemetry
```

If you want a safe dry run first:
```bash
conda activate FileAnalyze
python /Users/enkay/dev/wikimaker/wikimaker.py \
  --corpus-root /Users/enkay/dev/FileAnalyze/MDExtract/data \
  --output-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/output \
  --state-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/state \
  --telemetry-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/telemetry \
  --dry-run
```

Dry-run behavior:
- scans every Markdown file
- writes a preview report to `telemetry/dry_run_preview.md`
- includes a file-by-file table with status/title/heading/link counts
- does not write wiki output pages or update the corpus snapshot

If you want a quieter run while testing, you can also disable the live eval hook and limit the prompt sample to 5 files:
```bash
conda activate FileAnalyze
python /Users/enkay/dev/wikimaker/wikimaker.py \
  --corpus-root /Users/enkay/dev/FileAnalyze/MDExtract/data \
  --output-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/output \
  --state-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/state \
  --telemetry-root /Users/enkay/dev/FileAnalyze/MDExtract/wikimaker/telemetry \
  --dry-run \
  --no-enable-adk-eval \
  --sample-files 5
```

Model knobs:
- `--analysis-model` for corpus analysis (recommended: your local Gemma 4 E4B MLX model)
- `--generation-model` for wiki page writing
- `--review-model` for verification / contradiction checking
- Default backend is the local Ollama server on your LAN
- Google ADK remains the orchestration/observability layer

Useful outputs:
- `output/_change_report.md` — run summary and scan details
- `output/_root_index.md` — top-level wiki index
- `output/sources/` — one source-summary page per Markdown file
- `output/wiki-sets/` — wiki-set index pages
- `output/folders/` — folder gist.md and ledger.md memory
- `state/corpus_snapshot.json` — change-tracking snapshot
- `telemetry/latest.json` — run telemetry and observability summary

Run:
- `python /Users/enkay/dev/wikimaker/wikimaker.py --corpus-root <path>`

Next steps:
- tighten the JSON prompts so Ollama/Gemma returns the exact schema more reliably
- run a small end-to-end corpus slice before the full wiki build
- verify source backlinks and wiki-set cross-links in the generated output
- keep the corpus privacy-preserving and local-first
- wiki-os-inspired next release plan: `/Users/enkay/dev/wikimaker/docs/wiki-os-borrowing-plan.md`
- default decision: borrow UX/discovery ideas only; do not merge the full wiki-os codebase

WAXtrctr / WhatsApp extractor:
- `python /Users/enkay/dev/wikimaker/whatsapp_backup_extractor.py` uses the latest iPhone backup automatically and writes to `~/extracts/whatsapp`
- `python /Users/enkay/dev/wikimaker/whatsapp_backup_extractor.py --output-root /some/other/path` changes the destination
- `python /Users/enkay/dev/wikimaker/whatsapp_backup_extractor.py --db /path/to/ChatStorage.sqlite`
- or `python /Users/enkay/dev/wikimaker/whatsapp_backup_extractor.py --manifest /path/to/Manifest.db --backup-root /path/to/iPhoneBackup`
- use `--mode incremental` to only emit new/changed chat content while keeping append-only history
- chat files are written as a readable transcript first, with raw provenance tucked into collapsible `<details>` blocks for easier WikiMaker ingestion
