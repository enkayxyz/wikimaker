# WikiOS Borrowing Plan for WikiMaker

Date: 2026-05-25
Status: Draft
Decision: Hybrid — learn from wiki-os, selectively port a few proven UX patterns, do not merge the repos.

## 1) Purpose

Define what WikiMaker should borrow from https://github.com/Ansub/wiki-os, what it should explicitly not borrow, and how to test whether the borrowed ideas improve WikiMaker without weakening provenance, privacy, or local-first behavior.

This is not an implementation task. It is a requirements + execution checklist for later work.

## 2) Product decision

WikiMaker remains the source-of-truth engine:
- read-only source corpus
- provenance-first output
- source-summary pages
- wiki-set synthesis
- folder gist.md + ledger.md memory
- explicit backlinks and evidence

wiki-os is a design reference only:
- borrow UI/navigation ideas
- do not import its trust model
- do not import its external-fetch defaults
- do not import its full TS/React/server stack

## 3) Priority legend

- Priority 2 = must borrow or strongly prefer borrowing
- Priority 1 = useful if low-risk and low-maintenance
- Priority 0 = optional / later if needed
- Priority -1 = explicitly do not borrow for the current plan

## 4) Priority 2: borrow these ideas into WikiMaker

### 4.1 Corpus dashboard / “what matters here?” view
Requirement:
- WikiMaker should provide a compact corpus overview that highlights important areas before the user searches manually.

Borrowed idea from wiki-os:
- homepage-style corpus dashboard
- “most connected” items
- recent additions
- corpus stats snapshot
- visible entrypoints into graph/search/stats

Why:
- This is the best path toward corpus-to-corpus insight discovery.

### 4.2 Persistent search and fast navigation
Requirement:
- Search must be available from the main browsing surface and support rapid jump-to-page behavior.

Borrowed idea from wiki-os:
- always-available search
- debounced search behavior
- multiple escape hatches from every page

Why:
- Keeps the wiki feeling like a system, not a folder viewer.

### 4.3 Page-level relationship surfacing
Requirement:
- Every page should show related pages, neighboring concepts, and provenance clearly.

Borrowed idea from wiki-os:
- TOC
- breadcrumbs
- related chips
- local neighborhood graph
- metadata block with counts / recency / links

Why:
- Fits WikiMaker’s provenance-first model very well.

### 4.4 Explicit taxonomy discipline
Requirement:
- WikiMaker should separate topics, tags, and entity classes more clearly.

Borrowed idea from wiki-os:
- topic normalization
- aliases
- explicit entity classes like People
- config-driven classification

Why:
- This improves cross-corpus grouping without turning everything into tag soup.

### 4.5 Low-friction onboarding
Requirement:
- First-run setup should be simple, safe, and preview-first.

Borrowed idea from wiki-os:
- guided setup flow
- clear corpus selection
- immediate visible output
- preview before apply

Why:
- Lowers friction without changing the core engine.

## 5) Priority 1: borrow if it remains low-risk after review

### 5.1 Graph exploration view
Requirement:
- WikiMaker should eventually offer a graph view for exploring corpus relationships.

Borrowed idea from wiki-os:
- force-directed graph exploration
- node focus / neighborhood expansion
- graph search

Reason for priority 1, not 2:
- Useful, but only if it stays lightweight and does not become the source of truth.

### 5.2 Stats view
Requirement:
- WikiMaker should surface corpus health metrics.

Borrowed idea from wiki-os:
- total pages/files
- backlink counts
- most connected concepts
- page-size / density indicators

Reason for priority 1:
- Valuable, but only after the underlying data model is stable.

## 6) Priority 0: consider later, but not required now

### 6.1 UI polish patterns
Examples:
- clean cards
- small metadata chips
- subtle visual hierarchy
- light first-run animations

Why optional:
- Nice-to-have, but not needed for correctness or trust.

### 6.2 Demo-vault style onboarding content
Examples:
- sample corpus
- tutorial notes
- example pages explaining the workflow

Why optional:
- Helpful for adoption, but not essential for v0001/v0002.

## 7) Priority -1: explicitly do NOT borrow

These are the “do not bring into WikiMaker” items.

### 7.1 External fetch defaults
Do not borrow:
- Wikipedia image/summary lookups
- Google Fonts or other default third-party browser dependencies

Reason:
- Conflicts with strict local-first privacy expectations.

### 7.2 Mutable note-browser trust model
Do not borrow:
- any assumption that the source corpus is a live mutable vault
- any design where the browser app is the canonical editor for the source corpus

Reason:
- WikiMaker is a compiler over read-only source data, not a vault editor.

### 7.3 Full repo merge
Do not borrow:
- the complete wiki-os codebase
- its server/runtime assumptions
- its deployment/update shell helpers
- its full TS/React stack as the primary WikiMaker implementation

Reason:
- Too much maintenance burden and too much trust-boundary expansion.

### 7.4 Hidden outbound traffic
Do not borrow:
- silent network requests that reveal source/page names to third parties
- automatic remote lookups without explicit opt-in

Reason:
- This can leak corpus metadata and harm trust.

## 8) Requirement checklist

Use this checklist to decide whether a wiki-os-inspired change belongs in WikiMaker.

A change is acceptable only if all are true:
- [ ] It preserves source provenance.
- [ ] It keeps the source corpus read-only.
- [ ] It does not hide duplicates, evolution, or contradictions.
- [ ] It does not require remote services by default.
- [ ] It does not weaken local-first behavior.
- [ ] It has a clear role in cross-corpus insight discovery.
- [ ] It can be expressed as a thin layer or module, not a full merge.
- [ ] It has a measurable success criterion.
- [ ] It does not introduce opaque shell execution or unsafe update behavior.
- [ ] It can be tested on a small corpus before scaling.

A change must be rejected or deferred if any are true:
- [ ] It depends on third-party browser fetches for core function.
- [ ] It makes the source corpus writable by default.
- [ ] It blurs source pages with derived wiki pages.
- [ ] It makes provenance harder to verify.
- [ ] It requires merging unrelated code stacks.

## 9) Implementation plan

### Phase 1: Spec alignment
Goal:
- Lock the exact borrowing boundaries in the product docs.

Tasks:
- Update WikiMaker requirements to include the borrowed UX goals.
- Add the priority -1 anti-borrow list to the docs.
- Define what “graph,” “dashboard,” and “stats” mean in WikiMaker terms.

Success criteria:
- Requirements document clearly says what we want and what we refuse to import.
- No ambiguity remains about local-first behavior.

### Phase 2: Data model enrichment
Goal:
- Make the engine emit the fields needed for discovery UI later.

Tasks:
- Ensure analysis/generation plans keep explicit fields for topics, tags, entities, related pages, duplicates, contradictions, and cross-links.
- Ensure telemetry can report connectedness and corpus health.
- Ensure source pages keep backlinks and source URLs visible.

Success criteria:
- Output artifacts already contain the data needed for dashboard/search/graph surfaces.
- No extra scraping is needed later to build the UI.

### Phase 3: Browse-first artifact shaping
Goal:
- Make generated Markdown easier to browse and inspect.

Tasks:
- Improve root index / wiki-set index layouts.
- Keep key metadata in predictable sections.
- Preserve explicit source/provenance sections.
- Make folder gist and ledger continue to carry meaningful memory.

Success criteria:
- A human can find the important pages and lineage without reading the whole corpus.
- The wiki remains understandable from static Markdown alone.

### Phase 4: Discovery layer prototype
Goal:
- Add a thin browsing layer inspired by wiki-os, not a full merge.

Tasks:
- Prototype a dashboard view.
- Prototype search-first navigation.
- Prototype graph/stats presentation if the data is ready.

Success criteria:
- The browsing layer improves discovery without changing the source corpus.
- No third-party fetches are required for core use.

### Phase 5: Trust and privacy review
Goal:
- Verify the hybrid approach remains safe.

Tasks:
- Check for unintended outbound network requests.
- Check that source metadata is not leaked silently.
- Check that no unsafe update/deploy shell path was introduced.

Success criteria:
- All non-essential external requests are absent or opt-in.
- The system remains suitable for sensitive local corpora.

## 10) Success criteria to test against

Use these as go/no-go tests.

### Functional success criteria
- [ ] The wiki can be generated from a recursive Markdown corpus.
- [ ] Source-summary pages are created per source file.
- [ ] Wiki-set pages are created for inferred clusters.
- [ ] Folder gist.md and ledger.md are maintained.
- [ ] Duplicates, evolution, and contradictions remain visible.
- [ ] Cross-links between related pages are produced.
- [ ] The output includes explicit backlinks to source documents.
- [ ] The system can surface corpus-level insight, not just per-file summaries.

### Trust / safety success criteria
- [ ] No default external fetches are required for core wiki generation.
- [ ] The source corpus remains read-only.
- [ ] The output tree remains separate from the input corpus.
- [ ] There is no hidden shell-based update mechanism in the core path.
- [ ] The browsing layer does not become the canonical source of truth.

### Usability success criteria
- [ ] A newcomer can identify the main corpus topics in under a minute.
- [ ] A newcomer can jump from a summary to a source file in one click.
- [ ] A newcomer can tell which pages are central vs peripheral.
- [ ] A newcomer can see where evidence came from.

### Maintenance success criteria
- [ ] The borrowed ideas fit as thin modules or generated artifacts.
- [ ] The codebase remains manageable in the current Python-first Wikimaker stack.
- [ ] No full-stack merge is required to keep improving the product.

## 11) Review questions before implementation

Ask these before accepting any wiki-os-inspired change:
- Does it preserve provenance?
- Does it keep the corpus read-only?
- Is it local-first by default?
- Is it a thin, low-risk addition?
- Does it improve corpus-to-corpus insight discovery?
- Does it avoid hidden network traffic?
- Can it be tested on a small corpus first?

If any answer is “no,” the item goes to priority -1 or is deferred.

## 12) Recommended next move

Before coding, convert this plan into the next implementation checklist for WikiMaker v0002:
- exact files to update
- exact fields to add
- exact outputs to verify
- exact acceptance tests to run

## 13) Current release gate

Status: implemented in the codebase and smoke-tested.

Before testing on a real corpus with local AI, finish these three items:
1. Browser-based frontend / UI polish
   - surface dashboard, stats, search, and graph views in a clean browser UI
   - keep every page one click away from its source/provenance
2. Deeper ranking / graph quality improvements
   - improve node ordering, centrality, and neighborhood relevance
   - make the graph more useful for cross-corpus insight discovery
3. Extra hardening for edge cases and security review
   - validate against weird filenames, duplicate titles, missing metadata, and large corpora
   - confirm no silent outbound fetches or unsafe behavior on a real corpus

Acceptance gate:
- the UI is pleasant enough to browse
- graph/search ranking feels meaningfully better than the first pass
- security review passes on a real corpus
- only then do we move to real corpus + local AI testing

