# WikiMaker Next Stage Analysis: Make it Feel Like wiki-os, Without Losing Provenance

Date: 2026-05-26
Status: analysis + handoff for next session
Scope: UI/UX, ranking, semantic analysis, backlinks, reset workflow, and corpus-aware output quality

## Executive summary

The current WikiMaker run succeeded technically, but the output still feels like a provenance browser rather than a self-sufficient wiki app. That is the core gap.

The main issues are:

1. The browser UI is too visually dense and too “debug dashboard”-like.
2. There is no light/dark mode, which makes long browsing sessions feel worse.
3. The analysis layer is too generic; it is not yet adapting strongly to corpus type or corpus intent.
4. Backlinks are effectively missing, so the wiki does not yet feel connected.
5. Index-like pages are being treated too much like content pages instead of navigation scaffolding.
6. The current semantic layer is too sparse in places, so the browser exposes empty or low-value cards.

The strategic fix is not to merge wiki-os wholesale. It is to keep WikiMaker as the provenance engine and selectively borrow wiki-os UX patterns and page organization, while making the analysis layer more corpus-aware and link-driven.

## What the current run tells us

The output indicates the pipeline is functioning end-to-end:
- corpus scan works
- local Ollama works
- output generation works
- browser frontend renders
- reset utility works

But the output quality shows the real bottleneck:
- many pages are being surfaced as generic entries
- source pages are not yet strongly distinguished from index/navigation pages
- backlinks/outlinks are weak or absent
- semantic structure is shallow
- the browser does not yet provide the “I can live in this wiki” feeling

## Root cause analysis

### 1. Analysis is too generic
The model is being asked to summarize a corpus broadly, but different corpus types need different behavior.

Examples:
- WhatsApp chats should emphasize conversation participants, recurring entities, decisions, and relationship threads.
- bills/documents should emphasize entities, dates, amounts, vendors, and document types.
- AI chat exports should emphasize tasks, decisions, project names, and solution paths.

A single generic prompt does not capture these differences well enough.

### 2. Backlinks are not structurally enforced
The current experience lacks the feeling of a wiki because pages do not strongly point to each other.

A wiki needs:
- page A links to page B
- B links back to A
- related pages show mutual relationships
- entity/topic pages act as hubs

Without that, the site is a collection of summaries, not a wiki.

### 3. Index pages are being overrepresented
Some items shown in the browser are closer to indexes, stubs, or generated navigation artifacts than substantive content.

Those should exist, but they should be visually and semantically distinct from actual knowledge pages.

### 4. The browser is functional but not composed like a wiki home
The current browser is a discovery UI. It needs stronger hierarchy:
- one clean landing page
- focused sections
- fewer simultaneous visual equal-weight panels
- better default sorting
- less clutter in the detail pane

### 5. Missing theme support
Light mode and dark mode matter here because the product is for long-form reading and browsing, not just occasional inspection.

## What wiki-os seems to do better, conceptually

Even without merging code, wiki-os likely gives a better sense of:
- a single, coherent home
- visually clean page cards
- easier navigation between topics
- a more “self-contained wiki app” feel
- less emphasis on underlying pipeline artifacts

WikiMaker should borrow those surface behaviors, not the entire architecture.

## Recommended direction

Keep the overall strategy:
- WikiMaker remains the provenance-first engine
- source corpus stays read-only
- outputs stay separate from the corpus
- browser stays local-first
- no external fetches by default
- generated pages remain one click away from original provenance

But upgrade the product feel in 4 layers:

1. UI layer: make the browser clean, calm, and obvious.
2. Semantic layer: make the analysis corpus-aware.
3. Link layer: make backlinks and related-page connections first-class.
4. Navigation layer: make the browser home page a true wiki home.

## Next-stage priorities

### Priority 1: Clean wiki home UX
Goal: reduce visual noise and make the browser feel intentional.

Recommended changes:
- add an actual home section with a short intro and key corpus stats
- reduce card density by default
- group cards into clearer sections with stronger visual separation
- give the detail panel a calmer layout
- add light/dark toggle
- make the default entry point a “home” view, not a raw discovery dump
- use flatter cards, cleaner spacing, and fewer competing borders

### Priority 2: Corpus-aware analysis
Goal: improve the quality of extracted topics, entities, summaries, and page roles.

Recommended changes:
- classify corpus type per file or per folder before summarization
- branch prompts by corpus kind:
  - chats
  - bills/documents
  - mixed notes
  - project artifacts
  - index/ledger pages
- ask the model for different outputs per corpus type
- extract page roles explicitly:
  - knowledge page
  - thread page
  - index page
  - ledger page
  - duplicate/evolution page
  - contradiction page

This should improve both summary quality and browser relevance.

### Priority 3: Backlink generation
Goal: make the wiki actually feel connected.

Recommended changes:
- derive backlinks from shared entities, topics, and cited pages
- treat page titles, normalized aliases, and source links as candidate edges
- generate mutual related-page links when similarity is above threshold
- show backlinks prominently in the detail pane
- expose “linked from” and “links to” sections on every page
- prefer explicit backlinks over only graph edges

Backlinks need to be visible in the browser, not just in JSON.

### Priority 4: Better page ranking and default ordering
Goal: surface the most useful pages first.

Recommended changes:
- rank by a blend of:
  - graph centrality
  - backlinks count
  - topic/entity density
  - corpus-specific importance
  - recency for chats
  - document importance for bills/docs
- deprioritize pure index pages in the main source feed
- allow a separate “indexes and ledgers” section for navigation artifacts
- surface “most connected” and “most informative” as different categories

### Priority 5: Distinguish content pages from generated navigation pages
Goal: stop index pages from overwhelming the experience.

Recommended changes:
- label page type clearly in UI
- keep generated indices in their own section
- do not mix index pages with primary source pages in the default browse list
- preserve provenance links but treat generated pages as secondary layers

## Suggested product model for the next stage

Think in three layers:

### Layer A: Source corpus
Raw Markdown sources and metadata.
This is immutable and read-only.

### Layer B: Provenance wiki
Generated source pages, wiki-set pages, indexes, ledgers, and graph artifacts.
This is the trusted generated output.

### Layer C: Browsable wiki experience
A clean front-end that makes Layer B feel like a living wiki.
This is where the wiki-os inspiration should land.

## Concrete UI features to add next

1. Light/dark mode toggle
2. Cleaner home screen with less density
3. “Top pages” / “Recently changed” / “Most connected” tabs
4. Better source page cards with preview snippets
5. Entity/topic chips that are clickable filters
6. Backlinks and outgoing links shown in the detail pane
7. A dedicated “indexes and ledgers” area
8. Search-first mode with clear filtering
9. A clean empty-state message when the semantic layer is sparse
10. Better visual hierarchy around provenance

## Concrete analysis improvements to add next

1. Corpus classifier before summarization
2. Prompt templates per corpus kind
3. Page role classification
4. Entity normalization and alias merging
5. Backlink extraction from shared entities and page references
6. Duplicate/evolution detection
7. Contradiction clustering
8. Stronger relevance scoring for the browser default ordering

## What not to do

- Do not merge the full wiki-os codebase into WikiMaker.
- Do not drop provenance in favor of aesthetics.
- Do not make the browser depend on remote services.
- Do not treat generated index pages as equal to substantive source pages.
- Do not overfit to one corpus type.

## Recommended next-session implementation order

1. Add theme support and simplify the browser chrome.
2. Split source pages, index pages, and navigation pages more clearly.
3. Add backlink generation and display.
4. Add corpus-aware analysis prompts and page-role classification.
5. Re-rank cards using stronger graph and corpus signal.
6. Rework the home page layout to feel like a wiki home.
7. Add tests for backlinks, page-type separation, and theme toggle.

## Acceptance criteria for the next stage

The next stage should be considered successful when:
- the browser feels clean and wiki-like, not like a debug dashboard
- dark and light mode are both available
- at least some pages display meaningful backlinks and related pages
- corpus-specific analysis is visibly better than the generic pass
- index pages no longer dominate the main discovery view
- the user can navigate from home to a topic/page and back cleanly
- provenance remains one click away at all times

## Handoff summary

The current codebase is ready for the next stage, but the next stage should focus on making the wiki experience feel real.

The most important missing pieces are:
- cleaner UI
- theme support
- corpus-aware AI analysis
- backlinks
- better page classification
- less cluttered home navigation

That is the bridge from “working provenance browser” to “usable self-sufficient wiki app.”
