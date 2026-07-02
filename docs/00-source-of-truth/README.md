# Source Of Truth

This folder is the canonical input for the Retail Media Platform rewrite.
Hermes and any other coding agent must read it before architecture or
implementation work.

## Read Order

1. `TZ_Retail_Media_Platform_v2_5_Final_Hermes.extracted.md`
2. `rmp_rewrite_starting_decisions.md`
3. `rmp_enterprise_architecture_review.md`
4. Relevant ADRs and contracts in `docs/architecture/`

The original Word document is kept here for traceability:

- `TZ_Retail_Media_Platform_v2_5_Final_Hermes.docx`

## Rules

- The markdown extraction is the working copy for agents.
- The `.docx` is the original source document and must not be edited by agents.
- If a requirement changes, add an ADR or decision document; do not silently
  rewrite the original TZ.
- If code conflicts with this folder, this folder wins until a newer approved
  ADR explicitly changes the decision.
