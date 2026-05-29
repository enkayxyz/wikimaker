---
name: source-card-skill
description: Build privacy-safe WikiMaker SourceCards from deterministic facts, enriching only semantic fields when useful.
---

# Source Card Skill

Use deterministic scan facts as the source of truth. Enrich only the compact SourceCard fields needed for wiki organization: summary, topics, entities, candidate links, source quality, warnings, and confidence.

Do not include raw source text unless the run explicitly selected `sampled`, `deep`, or `original` card mode. Preserve provenance, avoid unsupported claims, and keep the result compact.
