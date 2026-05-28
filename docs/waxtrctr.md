# WAXtrctr

WAXtrctr is the WhatsApp iPhone-backup extractor product in this repository.

It is designed to:
- auto-detect the latest local iPhone backup on macOS
- extract WhatsApp data into a human-readable, chat-first corpus
- preserve provenance and raw metadata
- keep incremental history append-only
- make the output feel closer to the WhatsApp app while still adding extra forensic context

## What it outputs
- one Markdown file per chat/conversation
- a top-level index for navigation
- per-run summary files
- append-only state for incremental updates
- readable message timelines with raw provenance blocks

## Default run
```bash
python <repo-root>/waxtrctr.py
```

By default, WAXtrctr writes to:
- `~/extracts/whatsapp`

## Other common modes
```bash
python <repo-root>/whatsapp_backup_extractor.py --mode incremental
python <repo-root>/whatsapp_backup_extractor.py --output-root /some/other/path
python <repo-root>/whatsapp_backup_extractor.py --db /path/to/ChatStorage.sqlite
python <repo-root>/whatsapp_backup_extractor.py --manifest /path/to/Manifest.db --backup-root /path/to/iPhoneBackup
```

## Open-source intent
This repo is meant to be cloned and run locally by people who want a practical WhatsApp backup extraction workflow with strong provenance and readable output.

## Notes
- source data is treated as read-only
- no data is intentionally discarded
- opaque or encoded fields may stay raw when that is the only lossless representation
- output is optimized for later wiki ingestion and manual inspection
