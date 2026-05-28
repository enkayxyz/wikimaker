---
name: wikimaker
description: Compile a recursive folder tree of Markdown source documents into one or more evolving wiki sets with folder-level gist.md and ledger.md maintenance.
version: 0.1.0
author: local agent Agent
license: MIT
metadata:
 .wikimaker:
    tags: [wiki, knowledge-base, markdown, corpus-analysis, linking, reorganization]
---

# WikiMaker

Use this skill when the user provides a folder tree containing Markdown files. The tree may contain many nested subfolders. The corpus may include multiple source domains, such as bills and WhatsApp exports, and the wiki should usually split them into separate wiki sets while still cross-linking shared entities. Every source file is Markdown and should include a link back to its original source document. Your job is to infer one wiki or multiple wiki sets, generate the wiki in Markdown, maintain links/backlinks, and keep folder-level `gist.md` and `ledger.md` files updated over time. Keep the pipeline local-first and compatible with an OpenAI-style local server (Ollama, Osaurus, or similar) rather than assuming any external LLM.

This is a compiler and curator workflow, not an extraction workflow.

See also:
- `<repo-root>/docs/wiki-os-borrowing-plan.md` for the next-release borrow / do-not-borrow requirements and success criteria.

## Core product behavior

Input:
- A root folder containing only `.md` files, possibly across many nested subfolders.
- Each source `.md` should link back to the original document.

Output:
- A generated wiki under an output folder.
- One or more inferred wiki sets.
- Cross-linked pages, indexes, and relationship hubs.
- Per-folder `gist.md` and `ledger.md` files.
- Incremental updates and reorganization suggestions as content changes.
- A static browser UI inspired by WikiOS, without merging the WikiOS stack.
- Privacy and health reports for each generated wiki.

## Non-negotiable rules

1. Treat the source tree as read-only.
2. Walk the tree recursively.
3. Preserve provenance. Every generated page should cite source markdown files.
4. Every managed folder must maintain:
   - `gist.md` = current folder understanding
   - `ledger.md` = append-only change history
5. Do not silently reorganize. Record the reason in the relevant ledger.
6. Preserve all meaningful content. Do not hide duplicates, evolution, or contradictions; surface them explicitly.
7. Prefer read-only generated output so edits require deliberate effort outside the normal browsing flow.
8. Prefer incremental updates over full rebuilds when possible.
9. Default to local-only inference paths; if a remote or external model is ever used, make that explicit in config and documentation.
10. Classify the model endpoint as local, LAN, or remote before sending corpus content to it.
11. Do not generate browser assets that silently fetch remote fonts, images, analytics, or metadata.

## Day-zero model separation

Expose model choices from the start. Support separate configuration for:
- analysis_llm: infer wiki sets, ontology, hierarchy, link opportunities
- generation_llm: write wiki pages, indexes, summaries, backlinks
- review_llm: optional, for reorg suggestions and health checks

If the user provides only one model, reuse it for all roles.

Keep the default backend local and prefer Ollama on the user's LAN when available.

## Provider / transport wiring

ADK 2 can own orchestration and tool-routing, but the model backend should stay separate.

Preferred pattern:
- keep ADK responsible for workflow orchestration and observability
- use an env-driven adapter for model/provider selection
- keep model names configurable without code changes
- use a local Ollama server when possible

Local model setup note:
- Ollama can be accessed through its local API on the LAN
- `OPENAI_BASE_URL` should point at the local Ollama host
- no API key is needed for plain Ollama
- if you switch back to an OpenAI-compatible backend, `OPENAI_API_KEY` or `OSAURUS_API_KEY` should hold the local server key
- stage 1 should generate individual source-page plans
- stage 2 should identify commonality and synthesize wiki sets
- stage 3 should verify the wiki output against the corpus

## ADK 2 / provider-agnostic implementation notes

For the v0001 scaffold, the preferred orchestration stack is:
- Google ADK 2.x for graph/workflow orchestration
- an OpenAI-compatible LLM API surface for model calls
- a local-only inference backend when available

Important implementation details:
- the PyPI package is `google-adk`
- the import namespace is `google.adk`
- in this environment, pin the package line as `google-adk==2.1.0`
- root ADK `LlmAgent` instances must use `mode="chat"` (not `single_turn`)
- do not hard-bind logic to Google-only models
- keep provider selection configurable via env vars or config
- use ADK for orchestration/observability, not as a model lock-in layer
- enable observability with `google.adk.telemetry.setup.maybe_set_otel_providers(...)` and a local `SqliteSpanExporter` if you want persistent traces
- keep the runtime hard-failing if the local model server or key is missing
- do not retain a deterministic fallback wiki-generation path
- keep default synthesis `llm_only`; scan data may support provenance/library visibility but must not invent semantic links

Recommended env vars:
- `WIKIMAKER_CORPUS_ROOT`
- `WIKIMAKER_OUTPUT_ROOT`
- `WIKIMAKER_STATE_ROOT`
- `WIKIMAKER_TELEMETRY_ROOT`
- `WIKIMAKER_PROVIDER`
- `WIKIMAKER_ANALYSIS_MODEL`
- `WIKIMAKER_GENERATION_MODEL`
- `WIKIMAKER_REVIEW_MODEL`
- `WIKIMAKER_USE_ADK`
- `WIKIMAKER_ALLOW_REMOTE_LLM`
- `WIKIMAKER_PROMPT_PROFILE`
- `WIKIMAKER_CONDA_ENV`
- `OPENAI_API_KEY`
- `OSAURUS_API_KEY`
- `OPENAI_BASE_URL`

Local model defaults that worked best in this flow:
- your Ollama model name for routine extraction/summarization
- your Ollama model name for heavier synthesis/review

## Runtime environment

Use the dedicated `wikimaker` conda environment, not the extraction utility environment:

```bash
cd <repo-root>
conda env create -f environment.yml
conda run -n wikimaker python -m pip install -r requirements.txt
conda run -n wikimaker python wikimaker.py --help
```

The macOS helper defaults to `WIKIMAKER_CONDA_ENV=wikimaker`. Override that only for debugging.

If network access is unavailable during setup, it is acceptable to clone an existing local Python 3.11 env as a temporary bootstrap, then run the `pip install -r requirements.txt` command when package access returns.

## Privacy boundary

Every run should make the model boundary visible:
- `local` means this machine
- `lan` means private-network endpoint
- `remote` means DNS/public internet risk

Remote endpoints must be refused unless `WIKIMAKER_ALLOW_REMOTE_LLM=1` or `--allow-remote-llm` is set. The generated output should include `_privacy.md` and `_llm_quality.md`, and the browser UI should expose the model endpoint classification, browser network posture, and quality report link.

The LLM quality judge must receive aggregate metrics only: no source text, filenames, titles, snippets, or personal data.

The generated browser should stay static-first: embedded/local JSON, local links, no remote fonts, no image lookup, no analytics, no hidden fetches.

## Prompt profiles

Use automatic corpus-kind detection plus optional local overrides. WikiMaker should look for `wikimaker.profiles.json`, `wikimaker.profiles.yaml`, or `wikimaker.profiles.yml` under the corpus root, or use `WIKIMAKER_PROMPT_PROFILE`.

Profiles should be local files and can override folder behavior:

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

Built-in profiles should cover the current corpus families (`whatsapp_chats`, `ai_conversations`, and `financial_documents`) plus contacts, calendars, meeting notes, recording transcripts, emails, iMessages, personal notes, Google Docs, code repositories, project artifacts, index/ledger pages, and mixed notes. Legacy `chats` and `bills_documents` are still accepted as aliases.


## Expected workspace layout

```text
project/
  corpus/                    # user-owned recursive markdown source tree (raw truth)
  wiki-build/
    config.yaml
    state/
      corpus_snapshot.json
      page_map.json
      cluster_map.json
    output/
      _root_index.md
      _change_report.md
      _privacy.md
      _llm_quality.md
      _health.md
      raw-links/             # optional indexes into the raw corpus
      sources/               # one compact source-summary page per source document/chat
      wiki-sets/
        <wiki-set>/
          _index.md
          ...generated knowledge pages...
```

Source folders inside `corpus/` should also gain or maintain:
- `gist.md`
- `ledger.md`

If these files do not exist, create them.

## Alpha v0001 content model

Prefer a 3-layer structure:
1. `corpus/` = raw source markdown, read-only truth layer
2. `output/sources/` = one wiki-style source page per source document/chat
3. `output/wiki-sets/` = higher-level knowledge/topic pages built from many source pages

Do not use one source file as the final wiki page. Raw source, source summary, and knowledge synthesis should remain distinct layers.

## Commands you should support conceptually

Use these command names in your workflow and explanations:
- `init` — create config and output/state folders
- `analyze` — scan corpus recursively and infer wiki / wiki sets
- `preview` — show proposed structure before writing all pages
- `apply` — generate wiki pages and indexes
- `update` — detect changes and update wiki incrementally
- `reorganize` — propose/apply merges, splits, moves, renames
- `publish` — present final wiki output and change report
- `healthcheck` — inspect link quality, duplicates, weak pages, stale structure
- `build` — one-command alpha v0001 run that generates the wiki end-to-end unless human intervention is truly required

## Recommended execution flow

### 1. Init
When asked to set up a project:
- create `wiki-build/config.yaml` from the template
- create `wiki-build/state/`
- create `wiki-build/output/wiki-sets/`
- verify the corpus root exists

### 2. Analyze
Scan the corpus recursively.
Ignore generated wiki output folders.
For each folder and file, capture:
- relative path
- title
- source link if present
- headings
- entities/topics inferred from text
- references to sibling or related docs

Then infer:
- single wiki vs multiple wiki sets
- top-level themes
- canonical page names
- page-to-source mappings
- folder-to-wiki-set mappings
- cross-link candidates

Write a preview document at:
- `wiki-build/output/_change_report.md`

### 3. Folder intelligence
For every folder in the source corpus, maintain two files.

#### `gist.md`
Purpose: current understanding of that folder.
Include:
- folder purpose
- major themes/entities
- key files
- child folder summaries
- open questions / ambiguities
- affected wiki set(s)
- last updated timestamp

#### `ledger.md`
Purpose: append-only changelog.
Record entries such as:
- file added
- file changed
- gist refreshed
- wiki page created/updated
- page moved/merged/split
- reorg suggestion accepted/rejected
- timestamp
- reason

### 4. Preview before full generation
Before writing many pages, present:
- inferred wiki set names
- proposed hierarchy
- major pages
- uncertain clusters
- notable cross-links
- suggested user adjustments

### 5. Apply
Generate:
- root index
- per-wiki-set index
- one source-summary page per source document/chat
- concept/entity/topic pages
- relationship hubs when useful
- backlinks / related pages sections
- privacy report (`_privacy.md`)
- aggregate-only LLM quality report (`_llm_quality.md`)
- health report (`_health.md`)

Every source-summary page should include:
- title
- platform/provider
- date/extracted timestamp if known
- short summary
- key snippets
- raw markdown source link
- original source/chat URL when available
- topics/tags
- `## Used in` links to the knowledge pages that rely on this source

Every generated knowledge page should include:
- short purpose statement
- synthesized content grounded in sources
- source citations with relative paths
- related pages
- `## Sources` with direct links to source markdown files and/or source-summary pages
- `## External references` with original URLs when available
- `## Evidence / Truth trail` with bullets tying major claims to source files or URLs
- `## Duplicates / Near-duplicates` when multiple sources cover the same content
- `## Evolution over time` when a topic changes across dates or versions
- `## Contradictions / Tensions` when sources disagree or conflict
- `## Cross-wiki links` pointing to relevant pages in other wiki sets or top-level topics

By default, duplicates and contradictions should appear as sections inside relevant knowledge pages, not as separate cluster page types, unless they grow large enough to justify dedicated pages.

### 6. Update
On later runs:
- compare file tree and content hashes against prior snapshot
- detect new/changed/removed files
- update affected folder `gist.md`
- append relevant `ledger.md` entries
- update only affected wiki pages if possible
- refresh indexes and change report

### 7. Reorganize
Look for:
- duplicate pages
- evolving pages that represent the same subject across time
- contradictory pages or claims
- oversized pages needing split
- sparse pages needing merge
- clusters that should become separate wiki sets
- weakly linked areas needing hub pages
- naming inconsistencies / aliases
- opportunities to cross-link across wiki sets or topics

Record every accepted change in ledgers and in `_change_report.md`.

## Heuristics to follow

Infer multiple wiki sets when:
- there are clearly separate domains with low overlap
- folder and topic structure show distinct clusters
- cross-links between clusters are sparse compared with within-cluster links

Concrete examples of separate wiki sets can include finance/bills, WhatsApp/chat history, and other archival corpora that share people or vendors but differ in the shape of the source documents.

Infer a single wiki when:
- the corpus is one coherent domain
- entities and concepts cross-link heavily
- folders differ mainly by subtopic, not by domain

When uncertain, prefer:
- one root wiki with multiple wiki sets beneath it

## Source markdown expectations

A source markdown file should ideally contain one of:
- YAML frontmatter with source metadata
- a visible `Source:` line
- a link to the original document near the top or bottom

If the source link is missing, continue but note the gap in folder `gist.md` and `ledger.md`.

## Health checks

Run health checks when asked or after major updates. Look for:
- missing provenance links
- orphan wiki pages
- source files not represented in any wiki page
- repeated pages / aliases needing merge
- underlinked folders
- folders whose `gist.md` is stale relative to file changes

Write health results to `_health.md` and surface the health link in the generated browser.

## Implementation guidance

When implementing this in a repo, start simple:
- Python for filesystem scanning and state snapshots
- Markdown output for all generated artifacts
- YAML config for model selection and paths
- deterministic hashing for change detection
- LLM only for analysis, synthesis, and reorganization suggestions

## What success looks like

The user can point you at a corpus folder, choose models, preview the inferred wiki structure, approve or tweak it, generate the wiki, and later rerun updates as the corpus changes. The wiki should improve over time while preserving provenance and folder-level memory through `gist.md` and `ledger.md`.

## Linked files

See:
- `README.md`
- `docs/requirements.md`
- `docs/runbook.md`
- `docs/wiki-os-borrowing-plan.md`
- `wikimaker.py`
- `wikimakerctl.sh`
- `environment.yml`
- `skill/wikimaker_alpha_v0001.py`
