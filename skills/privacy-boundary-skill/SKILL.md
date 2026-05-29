---
name: privacy-boundary-skill
description: Enforce WikiMaker privacy boundaries for generated artifacts and telemetry.
---

# Privacy Boundary Skill

Generated Markdown, browser data, and public telemetry must not expose absolute local paths, raw prompts, raw source text, API keys, secrets, or unintended network topology.

Use relative source identifiers, stable card ids, and safe labels such as `configured corpus`, `generated output`, and `state root redacted`.
