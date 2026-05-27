# WikiMaker Handover for Next Agent

Date: 2026-05-27

## 1) What this project is

WikiMaker is a local-first compiler that turns a recursive Markdown corpus into an evolving wiki.

The core boundary is:
- input corpus is read-only
- generated wiki lives in a separate output tree
- provenance must remain visible
- duplicates, evolution, and contradictions should stay explicit
- folder memory should be preserved with `gist.md` and `ledger.md`

There is also WAXtrctr in this repo, which is the WhatsApp iPhone-backup extractor side of the project. Keep that distinct from WikiMaker’s wiki synthesis pipeline.

## 2) Technical architecture

Current stack:
- Python 3 implementation
- Google ADK 2 for orchestration and observability
- local OpenAI-compatible API surface for model calls
- Ollama on the LAN as the default inference backend
- static Markdown outputs plus a local browser frontend
- pytest for smoke and integration checks
- shell helper: `wikimakerctl.sh`

Important implementation details:
- package namespace: `google.adk`
- working package line in this environment: `google-adk==2.0.0b1`
- local LLM endpoint: `http://192.168.86.11:11434`
- the pipeline is intentionally local-only for real corpus runs
- do not add a deterministic non-AI wiki-generation fallback

Main entry points:
- `wikimaker.py` at repo root
- `code/wikimaker_runner.py`
- `code/wikimaker_scanner.py`
- `code/wikimaker_openai.py`
- `code/wikimaker_discovery.py`
- `code/wikimaker_browser.py`
- `code/wikimaker_observability.py`
- `code/wikimaker_state.py`
- `code/wikimaker_telemetry.py`

## 3) Current state of the codebase

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

What is still weak:
- the browser UI still feels too dense and too much like a debug dashboard
- inference quality is not strong enough for all corpus types
- commonality / synthesis across pages can still be shallow
- backlink and relationship surfacing is better than before, but still not strong enough for a truly wiki-like feel
- distinguishing content pages from generated navigation pages still needs more polish in UX and ranking

## 4) Product requirements that matter most

Non-negotiables:
- source corpus stays read-only
- provenance must be preserved
- generated pages must link back to source Markdown and original URLs when available
- duplicates, evolution, and contradictions must be surfaced, not hidden
- folder-level `gist.md` and `ledger.md` are required for long-term corpus memory
- local-first behavior is the default
- real-corpus runs should stay on the 192.168.86.* Ollama path

Desired product shape:
- one source-summary page per source document
- one or more wiki sets inferred from the corpus
- explicit backlinks and related pages
- clear separation between source pages, wiki-set pages, and navigation pages
- a calmer browser UI that feels like a wiki, not a tool console

## 5) My understanding of the user’s wish

The user thinks the current UI and the inference layer for turning data into a wiki are still too weak.

The user wants a stronger agent to take over and improve:
- UI polish and browseability
- synthesis quality across different corpus types
- corpus-aware reasoning
- relationship inference and backlinks
- better page ranking and page-role separation

The user also wants the work handed over cleanly so the next agent can continue without re-discovering the boundaries.

## 6) Summary of our chat so far

The conversation was:
1. The user said WikiMaker has been developed, but UI and information inference are still weak.
2. The user proposed handing the work to another agent with stronger capabilities.
3. The user asked for a handover document describing architecture, current state, wishes, and chat summary.
4. The user asked to push the code and the document to GitHub for pickup by the next agent.
5. The user asked for a small prompt to give that next agent to plan and execute.

## 7) Suggested boundary for the next agent

The next agent should treat WikiMaker as:
- a provenance-first compiler
- not a mutable note browser
- not a remote-fetch app
- not a full wiki-os merge

Borrow the good UX ideas, but do not merge the wiki-os codebase. Keep the generated wiki separate from the source corpus.

## 8) Where to start next

Recommended next steps for the next agent:
1. improve browser home layout and visual hierarchy
2. make page roles and navigation pages more explicit
3. strengthen corpus-aware prompting and page-role classification
4. improve backlinks / related-page derivation
5. tune ranking so substantive pages appear before scaffolding
6. keep provenance one click away at all times

## 9) Relevant docs

- `README.md`
- `docs/requirements.md`
- `docs/runbook.md`
- `docs/wiki-os-borrowing-plan.md`
- `docs/plans/wiki-os-next-stage-analysis.md`
- `docs/plans/wiki-os-next-stage-implementation-plan.md`
- `skill/SKILL.md`

## 10) One-line handoff

WikiMaker is working end-to-end as a local provenance-first wiki compiler, but the next agent should focus on making the browser calmer and making the AI synthesis much better across corpus types while preserving the read-only/provenance boundary.
