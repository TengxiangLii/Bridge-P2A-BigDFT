---
name: paper2profile
description: Use when asked to generate, draft or regenerate a BigDFT reproduction profile for a paper from its Paper2Agent paper skill, or when cross-verify runs with --generate. Produces a draft profile and a diff against the registry; the draft is never used for a run.
---

# Paper2Profile (generator, stages S1–S5 and S6′)

Turn a P2A paper skill into a **draft** reproduction profile, then diff it against the registry profile. In the prototype the draft never feeds a run; the diff measures how consistently profiles are generated.

`PLUGIN` is two levels above this file; run scripts as `uv run -q PLUGIN/scripts/<name>.py`. Inputs are the paper skill directory (`SKILL_DIR`) and, if present, the agent manifest (`WORK/agent-manifest.json`). Outputs go to `WORK/generate/`.

The output must validate against `PLUGIN/schemas/profile.schema.json`. Read it, and read every `PLUGIN/templates/*.yaml` (claim templates with `synonyms` and `not_equivalent_to`) before you start.

## Stages

| Stage | Do | Gate (must pass before the next stage) |
|---|---|---|
| S1 Scope | Read `SKILL_DIR/references/index.md`. Locate Methods/Computational details, results tables (`assets/table/*.csv`) and the SI. | Methods located; if not, record `methods_not_found` in `notes` and stop |
| S2 Settings | Fill **every** fixed setting key in the schema: `state: stated` with `value`, a verbatim `quote` (≤ 300 chars, copied from `references/*.md` and not spanning citation superscripts), and `location`; or `unknown` with a `note`; or `not_applicable` with a `reason`. Never infer a value the paper doesn't state. | `quote_check.py` passes (S5) |
| S3 Claims | For each computational result the paper reports, find the matching template by its `quantity`, `definition` and `synonyms`. Reject a match listed in `not_equivalent_to`. A claim with no matching template goes to `needs_template`; a claim BigDFT can't recompute (structure searches, MD statistics, excited states) goes to `excluded`, each with a location. Reference values come from a table cell (`location: "table:assets/table/<file>.csv#row=<first column>;col=<header>"`, `confidence: table`, `printed_decimals`), from a quoted sentence (`confidence: text`), or from the agent's stored data read through its MCP tools (`confidence: dataset`, `quote: null`, location = the dataset key). Values only in figures: `confidence: figure` with an explicit `uncertainty`. | every claim has a template id and a checkable reference |
| S4 Structures | One `structures` entry per structure a claim uses, with formula, charge, multiplicity (singlet for even electron counts unless the paper says otherwise), and an `authority`: a machine-readable source (`kind: dataset`, locator url/member/format) or a paper table (`kind: paper_table`, locator file). Compute `sha256` with `canonical_structure.py fetch --locator '<json>' --precision <precision_A> --paper-skill SKILL_DIR`. | every hash comes from the script, not typed |
| S5 Validate | `validate.py profile WORK/generate/draft-profile.json` and `quote_check.py --profile WORK/generate/draft-profile.json --paper-skill SKILL_DIR` | both exit 0; otherwise fix the draft and rerun |
| S6′ Diff | `diff_profiles.py --a PLUGIN/registry/<doi-key>/profile.json --b WORK/generate/draft-profile.json --out WORK/generate/profile-diff.md` | `profile-diff.md` written (differences are a result, not an error) |

Set `status: draft`, `id: <registry id>-generated`, `version: 0.0.0`, and `reviewers: []`.

## Fixed rules (apply these; don't choose)

1. **Which structures.** Claim the systems whose results the paper discusses in its main-text tables. For each of them use the dataset's global minimum (rank 0), plus any isomer the paper names explicitly (e.g. Table 2 minima).
2. **Which quantities.** For every claimed structure, claim every template quantity that the paper defines (in text or an equation) **and** that the dataset stores for that structure, even if the paper prints no value. Include `total_energy` whenever the dataset stores the KS energy.
3. **Reference preference.** The dataset value at full precision is the reference. A table value (with `printed_decimals`) or a text value goes into `cross_checks`. Only a quantity with no dataset value uses a table, then a text, then a figure value as its reference.
4. **Energy ordering.** One `relative_energy_ordering` claim per system that has a stored ordering, over dataset ranks 0–5 (six isomers), in rank order.
5. **Degeneracy threshold.** Use the dataset's grouping threshold, with a `definition_note` naming any looser criterion the paper uses.
6. **Multiplicity.** Even electron count → 1; odd → 2 (minimal moment), unless the paper states otherwise.
7. **Table locations.** `table:<csv>#row=<first-column value>;col=<header>`. For continuation rows with an empty first column, use `#rowindex=<n>` (1-based data row).
8. **Dataset locations.** `dataset key <Key> (<record>, <file>)`, e.g. `dataset key Homo-Lumo-gap (Materials Cloud j7hwv-81q79, all_minima_data.npy)`.
9. **Grouping.** One `excluded` or `needs_template` entry per distinct reason; list the affected items inside it.
10. **Structure precision.** `precision_A = 1e-6` for machine-readable coordinates stored as floating point; the printed precision for coordinates in a paper table.

## What you never do

- Fill a setting or reference value that has no quote, table cell or dataset key behind it.
- Invent a template, or write a free-text computation in place of one.
- Type a structure hash.
- Edit the registry entry.
- Use the draft for a run.
