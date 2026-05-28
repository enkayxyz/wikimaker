# WikiMaker Next Stage Implementation Plan

> **For local agent:** Use subagent-driven-development task-by-task for implementation.

**Goal:** Make WikiMaker feel like a calm, self-sufficient wiki app while preserving provenance, local-only inference, and read-only source corpus behavior.

**Architecture:** Keep WikiMaker as the provenance-first compiler. Upgrade the experience in four layers: browser UI, page-role/ranking model, backlink graph, and corpus-aware prompts. Do not merge wiki-os or add remote fetches; borrow only the discovery/navigation behaviors that improve the local wiki feel.

**Tech Stack:** Python 3, local OpenAI-compatible Ollama endpoint on `127.0.0.1`, Google ADK orchestration/telemetry, static Markdown outputs, local browser HTML/JS, pytest.

---

## Current release gate

Do not expand live-corpus iteration until the next milestone includes:
- a calmer browser home page with theme support
- explicit separation of source pages, index/ledger pages, and generated navigation pages
- visible backlinks / related pages in the browser detail pane
- corpus-aware prompt branching for different source kinds
- tests proving the new page-role and ranking behavior

Success means the browser feels like a wiki, not a debug dashboard, while provenance remains one click away.

---

## Task 1: Add theme support and simplify the browser home layout

**Objective:** Make the local browser feel intentional, readable, and less dense.

**Files:**
- Modify: `code/wikimaker_browser.py`
- Test: `tests/test_wikimaker_smoke.py`

**Step 1: Write the failing test**

Add assertions that the generated browser HTML includes:
- a theme toggle control
- a persisted theme hook or `localStorage` usage
- clearer home sections for top pages / recent updates / most connected / wiki sets

Example expectations:
```python
browser_text = browser_path.read_text(encoding="utf-8")
self.assertIn("themeToggle", browser_text)
self.assertIn("localStorage", browser_text)
self.assertIn("Most connected", browser_text)
self.assertIn("Recently changed", browser_text)
```

**Step 2: Run the test to verify failure**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: at least one assertion fails because the theme toggle and section labels do not yet exist.

**Step 3: Implement the smallest browser changes**

In `code/wikimaker_browser.py`:
- add a light/dark toggle button
- persist theme selection in `localStorage`
- reduce default card density and visual noise
- split the main browser into clearer sections
- simplify the detail pane spacing and metadata block
- keep the browser static and local-only

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: browser smoke test passes and generated HTML contains the new controls/sections.

**Step 5: Commit**

```bash
git add code/wikimaker_browser.py tests/test_wikimaker_smoke.py
git commit -m "feat: calm browser home and add theme toggle"
```

---

## Task 2: Introduce explicit page roles and keep navigation pages out of the main browse feed

**Objective:** Stop index-like artifacts from looking like primary knowledge pages.

**Files:**
- Modify: `code/wikimaker_openai.py`
- Modify: `code/wikimaker_discovery.py`
- Modify: `code/wikimaker_runner.py`
- Test: `tests/test_wikimaker_smoke.py`

**Step 1: Write the failing test**

Add a test fixture that contains a mix of source pages and navigation-like pages, then assert that:
- a page role field exists in the generated analysis/generation output
- index/ledger pages are marked distinctly
- the default browse ordering prefers substantive source pages over generated nav pages

Suggested assertion targets:
- `page_role` or equivalent field exists in `SourcePagePlan`
- dashboard/search output can separate source pages from index/ledger pages
- source pages still appear first in the main source lists

**Step 2: Run the test to verify failure**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: failures showing page roles are missing or not used in ranking/display.

**Step 3: Add the role schema and prompt instructions**

In `code/wikimaker_openai.py`:
- add a `page_role` field to `SourcePagePlan`
- define the allowed roles clearly, at minimum:
  - `knowledge_page`
  - `thread_page`
  - `index_page`
  - `ledger_page`
  - `duplicate_page`
  - `contradiction_page`
- instruct the analysis and generation prompts to classify page roles explicitly
- keep the fallback path aligned with the same role vocabulary

In `code/wikimaker_discovery.py` and `code/wikimaker_runner.py`:
- use role to change ordering and section placement
- keep index/ledger pages visible, but not mixed into the primary discovery feed by default

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: role-aware output and role-based ordering pass.

**Step 5: Commit**

```bash
git add code/wikimaker_openai.py code/wikimaker_discovery.py code/wikimaker_runner.py tests/test_wikimaker_smoke.py
git commit -m "feat: classify page roles and de-emphasize navigation pages"
```

---

## Task 3: Make backlinks and related pages first-class in generation and browser UI

**Objective:** Turn the wiki from isolated summaries into a connected knowledge graph.

**Files:**
- Modify: `code/wikimaker_openai.py`
- Modify: `code/wikimaker_discovery.py`
- Modify: `code/wikimaker_browser.py`
- Modify: `code/wikimaker_runner.py`
- Test: `tests/test_wikimaker_smoke.py`

**Step 1: Write the failing test**

Add assertions that generated source pages and browser data include at least one of:
- `backlinks`
- `outlinks`
- `linked_from`
- `links_to`
- `related_pages`

Also assert the browser detail pane visibly renders those sections.

**Step 2: Run the test to verify failure**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: the browser detail pane or data model lacks explicit backlink sections.

**Step 3: Add explicit link fields and derivation rules**

In `code/wikimaker_openai.py`:
- instruct the model to produce stronger related-page links
- ask it to preserve evidence-based backlinks when a page refers to another page, entity, or wiki set

In `code/wikimaker_discovery.py`:
- derive graph edges from shared entities, normalized aliases, page references, and wiki-set membership
- compute backlink counts and outgoing counts consistently
- keep explicit relationship sections in the generated Markdown outputs

In `code/wikimaker_browser.py`:
- add visible `Links to` / `Linked from` sections in the detail pane
- surface backlink counts in the card metadata
- keep provenance links prominent

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: link sections render and counts are exposed in the browser artifacts.

**Step 5: Commit**

```bash
git add code/wikimaker_openai.py code/wikimaker_discovery.py code/wikimaker_browser.py code/wikimaker_runner.py tests/test_wikimaker_smoke.py
git commit -m "feat: expose backlinks and related pages"
```

---

## Task 4: Make the analysis corpus-aware instead of generic

**Objective:** Improve output quality by adapting prompts to corpus type.

**Files:**
- Modify: `code/wikimaker_scanner.py`
- Modify: `code/wikimaker_openai.py`
- Modify: `code/wikimaker_runner.py`
- Test: `tests/test_wikimaker_smoke.py`

**Step 1: Write the failing test**

Add a corpus fixture that mixes at least two kinds of documents, for example:
- chat-like Markdown
- document/bill-like Markdown
- project note / index-like Markdown

Assert that the analysis detects multiple corpus kinds and that the generated wiki set or source page output differs by corpus kind.

**Step 2: Run the test to verify failure**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: the existing prompt path is still too generic or does not branch clearly enough by corpus kind.

**Step 3: Implement corpus classification and prompt branching**

In `code/wikimaker_scanner.py`:
- enrich the scan record with stable corpus-kind hints when available from frontmatter or structure
- preserve the existing read-only scan behavior

In `code/wikimaker_openai.py`:
- branch analysis instructions for at least these corpus kinds:
  - chats
  - bills/documents
  - mixed notes
  - project artifacts
  - index/ledger pages
- ask for different fields or emphases by kind:
  - chats: participants, threads, decisions, recurring entities
  - bills/documents: dates, amounts, vendors, document type
  - project artifacts: task names, milestones, solution paths
  - index/ledger pages: structure, summaries, navigation role
- keep duplicates, evolution, and contradictions explicit

In `code/wikimaker_runner.py`:
- ensure the new corpus-kind and page-role outputs are written into the generated artifacts

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: mixed-corpus fixtures produce visibly different analysis and page grouping.

**Step 5: Commit**

```bash
git add code/wikimaker_scanner.py code/wikimaker_openai.py code/wikimaker_runner.py tests/test_wikimaker_smoke.py
git commit -m "feat: make analysis corpus-aware"
```

---

## Task 5: Improve root index, dashboard, and search ordering for wiki usability

**Objective:** Make the generated Markdown surface the right pages first.

**Files:**
- Modify: `code/wikimaker_discovery.py`
- Modify: `code/wikimaker_runner.py`
- Test: `tests/test_wikimaker_smoke.py`

**Step 1: Write the failing test**

Assert that the generated output files:
- prioritize most connected pages and recent changes in the dashboard
- keep indexes/ledgers in their own section
- show a clear jump table in the search index
- preserve source links and provenance labels in the root index

**Step 2: Run the test to verify failure**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: at least one ordering or sectioning assertion fails.

**Step 3: Adjust ranking and section layout**

In `code/wikimaker_discovery.py`:
- rank by a blend of backlinks, outlinks, related count, used-in count, and recency
- keep generated navigation pages distinct from primary source pages

In `code/wikimaker_runner.py`:
- keep folder gist and ledger updates intact
- make the dashboard/search/root index easier to scan
- avoid mixing secondary navigation pages into the main source feed

**Step 4: Run the test again**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: the new ordering and sectioning behavior passes.

**Step 5: Commit**

```bash
git add code/wikimaker_discovery.py code/wikimaker_runner.py tests/test_wikimaker_smoke.py
git commit -m "feat: refine wiki ordering and navigation surfaces"
```

---

## Task 6: Run a small end-to-end corpus slice and verify the release gate

**Objective:** Prove the new stage works before another full real-corpus run.

**Files:**
- No new code required unless a bug appears
- Verify: `tests/test_wikimaker_smoke.py`
- Verify: `README.md`
- Verify: `docs/runbook.md`

**Step 1: Run the smoke test suite**

Run:
```bash
pytest tests/test_wikimaker_smoke.py -v
```

Expected: all smoke tests pass.

**Step 2: Run a small corpus slice**

Use a tiny subset of the real corpus and a dry run first, then a normal run if the preview looks good.

Example:
```bash
python <repo-root>/wikimaker.py \
  --corpus-root $HOME/extracts \
  --output-root $HOME/extracts/wiki-build/output \
  --state-root $HOME/extracts/wiki-build/state \
  --telemetry-root $HOME/extracts/wiki-build/telemetry \
  --dry-run
```

Then inspect:
- `output/browser/index.html`
- `output/_dashboard.md`
- `output/_search.md`
- `output/_root_index.md`
- `output/sources/`

**Step 3: Verify the release gate**

Confirm all are true:
- theme toggle works
- page roles are explicit
- backlinks are visible
- corpus-aware outputs are present
- index/ledger pages do not dominate the main browse flow
- provenance links remain one click away

**Step 4: If the slice looks good, run the non-dry corpus pass**

Only after the preview passes:
```bash
python <repo-root>/wikimaker.py --corpus-root $HOME/extracts
```

**Step 5: Record the result in the handoff docs**

If the milestone is complete, update the next-stage analysis note or add a short follow-up note under `docs/plans/` describing what changed and what remains.

---

## Recommended implementation order

1. Task 1 — browser theme + cleaner home
2. Task 2 — page roles and navigation separation
3. Task 3 — backlinks and related pages
4. Task 4 — corpus-aware prompts
5. Task 5 — ranking and section ordering
6. Task 6 — small-corpus verification

---

## Definition of done

The next stage is done when:
- the browser feels like a wiki home, not a debug dashboard
- light and dark mode both work
- source pages, index pages, and ledgers are clearly distinct
- backlinks and related pages are visible
- the analysis adapts to corpus type
- generated outputs stay provenance-safe and local-first
- smoke tests cover the new behavior
