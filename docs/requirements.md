# WikiMaker Alpha v0001 Requirements

This document captures the clarified product requirements for WikiMaker.

## User intent, in plain language

WikiMaker should take a corpus of already-extracted Markdown documents, where each Markdown file already links back to its original source, and turn that corpus into a meaningful evolving wiki.

Over time, when the corpus changes, WikiMaker should detect those changes and update the wiki accordingly.

The user’s desired stack is:
- Google ADK for orchestration
- Ollama as the default local API for LLM calls, with OpenAI-compatible backends allowed as a fallback option
- no deterministic fallback path for wiki generation
- read-only source corpus behavior
- ledger/gist style memory for folders and wiki structure

The user’s preferred high-level flow is:
1. generate individual file/source pages
2. identify commonality across pages
3. update individual pages and wiki pages with newly identified insights
4. preserve provenance, backlinks, duplicates, evolution, and contradictions

## Core goals

- Scan a recursive folder tree of Markdown files.
- Treat the source corpus as read-only.
- Generate meaningful wiki output from the corpus.
- Update the wiki when the corpus changes.
- Preserve backlinks to the original Markdown source.
- Preserve any original source URLs when present.
- Maintain `gist.md` and `ledger.md` style folder memory.
- Keep duplicates, evolution, and contradictions visible rather than hiding them.
- Emit telemetry and a change report for every run.
- Support a verification pass against the originals.

## Architecture requirements

### Orchestration
- Use Google ADK for orchestration.
- ADK should coordinate the workflow stages.
- The orchestration layer should remain separate from the model provider.

### Model access
- Use Ollama through its native local API by default, while keeping OpenAI-compatible support available.
- The live inference path should use `OPENAI_BASE_URL`.
- The live inference path should use `OPENAI_API_KEY` or `OSAURUS_API_KEY`.
- Do not use a direct Google/Gemini backend in the active pipeline.
- Do not keep a deterministic fallback wiki-generation path.
- If the model server or key is missing, fail clearly and early.

### Provider behavior
- Model/provider selection should be configurable.
- Default behavior should prefer the local Ollama path.
- The code should be able to explain which backend is active.

## Processing stages

WikiMaker should operate as a multi-stage compiler for the corpus.

### Stage 1: individual file generation
For each Markdown file:
- read the file
- extract title/headings/links/metadata
- generate a source-summary page
- preserve the source link and any external links
- retain evidence snippets where useful

### Stage 2: identify commonality
Across the generated source pages:
- infer shared themes
- cluster related source pages into wiki sets
- identify duplicate or near-duplicate content
- identify contradictions or tensions
- identify evolving topics over time
- propose cross-links between related pages

### Stage 3: update and synthesize
Use the discovered commonality to:
- update source pages with new insights
- generate higher-level wiki pages / wiki-set pages
- update folder-level `gist.md`
- append to folder-level `ledger.md`
- refresh indexes and change reports

## Corpus requirements

- Input is a recursively nested folder tree containing Markdown files.
- Each Markdown file is part of the source truth.
- The source corpus may already contain links to original sources.
- The corpus is read-only from WikiMaker’s perspective.
- Optional CSV metadata may be used later for enrichment, but Markdown is the primary input.

## Output requirements

WikiMaker should generate:
- one source-summary page per Markdown file
- one or more wiki-set pages
- root index pages
- a corpus dashboard page
- a stats page
- a search/jump-table page
- a graph data file for future UI layers
- folder-level `gist.md`
- folder-level `ledger.md`
- a change report
- telemetry artifacts
- state/snapshot data for incremental runs

## Folder memory requirements

Every relevant folder should maintain:
- `gist.md` — current summary of what the folder contains
- `ledger.md` — append-only changelog of file/content/page changes

The ledger should record:
- new files
- changed files
- removed files
- generated page changes
- reorganization suggestions
- accepted/rejected structural changes

## Provenance requirements

Every generated page should preserve traceability back to the source corpus.

That means:
- direct links to source Markdown files
- original source/chat/document links when available
- evidence snippets for major claims
- citations or backlinks in generated wiki pages

## Verification requirements

WikiMaker should support a verification pass that checks:
- source coverage
- missing backlinks
- unsupported claims
- duplicate or stale wiki pages
- contradictions or tensions
- whether the generated wiki still matches the corpus

## Non-goals for v0001

- No web UI requirement.
- No requirement to solve every ontology problem perfectly.
- No hidden or silent destructive reorganization.
- No fallback non-AI wiki generation.
- No direct dependency on Google model APIs for inference.

## Next-release direction

WikiMaker's next release should borrow selective discovery and navigation ideas from wiki-os without merging codebases.

Priority 2 borrow list:
- corpus dashboard / "what matters here?" view
- persistent search and fast navigation
- page-level relationship surfacing
- explicit taxonomy discipline
- low-friction onboarding

Priority 1 borrow list:
- graph exploration view
- stats view

Priority -1 do-not-borrow list:
- external fetch defaults such as Wikipedia lookups and Google Fonts
- mutable note-browser trust model
- full repo merge or TS/React/server stack merge
- hidden outbound traffic or silent remote lookups

Current release gate before real-corpus testing:
- browser-based frontend / UI polish
- deeper ranking and graph-quality improvements
- extra hardening for edge cases and security review on a real corpus
- verify these changes still preserve local-first, provenance-first behavior

Detailed requirements, checklist, and success criteria live in:
- `docs/wiki-os-borrowing-plan.md`

## Acceptance criteria

A v0001 implementation is acceptable if it can:
1. initialize from a corpus root
2. scan all Markdown files recursively
3. use Ollama via the local API for LLM calls
4. use Google ADK for orchestration
5. generate source-summary pages
6. infer commonality/wiki sets
7. update pages and folder memory on later runs
8. preserve provenance
9. detect deltas on later runs
10. emit telemetry and a change report
11. fail clearly when the model backend is unavailable
