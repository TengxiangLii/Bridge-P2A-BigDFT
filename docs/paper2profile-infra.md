# Design: infrastructure for re-verifying papers with BigDFT on top of Paper2Agent

Status: draft for review, revised 2026-10-13 after a design review. Nothing described here is implemented yet, except where marked **(exists)**.
Related: [gold profiles and calibration corpus (parked)](paper2profile-gold-profiles.md).

## 0. Prototype scope

The first deliverable is a **runnable prototype for one paper, Fisicaro 2023** (DOI 10.1039/D2MA01088G). We hand it to other developers, who re-verify the paper on their own machines. Each developer brings two things:
- their own P2A agent for the paper, which will have different tool names and tool boundaries from ours;
- their own cluster agent, ported from the `imlab` plugin, so it has the same structure and logic but different tool names, modules and BigDFT build.

The developer asks Claude to re-verify the paper's calculations. Claude calls those two agents and this plugin.

The prototype has to demonstrate four things:
1. **Bridge.** The paper-specific part between a P2A agent and BigDFT is solved.
2. **Portability.** A newly generated P2A agent for the same paper works without changes to the plugin.
3. **Minimal LLM freedom.** Every step where an LLM could improvise is replaced by a contract, a script or a mechanical gate wherever the inputs allow.
4. **High cohesion, low coupling.** Each stage has one job, reads and writes files with a schema, and can be rerun or swapped alone.

The sections below describe the full design. Anything not built in the prototype is marked *deferred* and collected in §14.

## 1. Problem

A researcher finds a paper, builds an agent for it with Paper2Agent (P2A), and then wants to redo some of the paper's calculations with BigDFT. Three pieces are already available:

| Piece | Scope | Status |
|---|---|---|
| P2A outputs: paper skill and, if the paper has code, an MCP server | per paper | exists |
| `bigdft:*` skills (input, pseudopotentials, systems, logfile, remote, ...) | general | exists (external) |
| `bigdft-cross-verify`: workflow, verdicts, tolerances, output contract | paper-independent | exists, v0.1.0, tested to the approval gate |

One piece is missing: the **paper-specific part of the bridge**. That means which calculations the paper ran, with which settings, which claims can be recomputed, where the structures come from, and how results are compared.

In v0.1.0 an LLM generates this part freely, per user. Different researchers, or the same one twice, get different claim sets, definitions and settings, and their results can't be compared. This design replaces improvisation with:
- fixed contracts;
- a generator pipeline with mechanical gates;
- a shared registry;
- deterministic scripts for planning and verdicts.

## 2. Goals and non-goals

**Goals**
- G1. Any P2A agent, in any of the forms P2A produces, can be extended with a paper-specific reproduction profile, with no manual authoring beyond review.
- G2. Two independent generations of a profile for the same paper agree on its scientific content, or their disagreements are surfaced before compute is spent.
- G3. A profile, once reviewed, is reusable by every researcher working on that paper, whatever P2A run produced their agent.
- G4. Every result can be traced to the exact profile, mapping, template, skill and engine versions that produced it.
- G5. The compute resource stays a user parameter.
- G6. Non-experts can drive a re-verification in natural language. Their freedom is in *what* to check and *how thoroughly*, never in the physics numbers.

**Non-goals**
- Reproducing structure searches, MD statistics, excited states or other workflows BigDFT can't run. Those claims are excluded with reasons.
- Making LLM steps deterministic. Consistency comes from contracts, checks and sharing, not from model behaviour.
- Changing P2A itself (upstream). An optional upstream proposal is in §11.
- Calibration corpus and gold profiles (parked; see the related doc).
- In the prototype: any paper other than Fisicaro 2023.

## 3. Core idea: separate paper facts, agent bindings, engine mapping and machine

What we informally called "the paper-specific bridge" mixes four kinds of information. Each gets its own file, with one reason to change:

| Layer | File | Content | Depends on | Shared? |
|---|---|---|---|---|
| Paper facts | `profile.json` | method settings, computable claims, their definitions, reference values, quotes, structure authorities and hashes | the paper only | yes, through the registry |
| Engine mapping | `bigdft-mapping.json` | how each paper setting maps to BigDFT: values, PSP files, `approximated` / `not_mappable` decisions, tolerance overrides | the paper + the engine | yes, through the registry |
| Agent bindings | `bindings.json` | which tool, file or URL supplies each structure or reference value | the specific P2A output | no; derived on each machine, and verified by probes |
| Machine | `target.json` | module/build, MPI×OMP, walltime, scratch | the compute target | no |

The **profile** stores only paper facts plus *abstract* data needs. The **binder** maps those needs to the local agent at run time and verifies the mapping by probing. The **mapping** holds the engine-side judgment, made once at review. The **target** may never change a number in a BigDFT input. This split is what lets one profile serve every agent built for the paper, and lets two developers on different clusters run byte-identical physics.

## 4. Architecture

```
               ┌────────────────────┐
  P2A output ─►│  Agent introspector │──► agent-manifest.json (local)
  (skill, MCP) └────────────────────┘            │
                                                  ▼
 ┌──────────────┐   lookup by DOI   ┌──────────────────┐ --generate ┌───────────────┐
 │ Profile       │◄─────────────────│  cross-verify     │──────────►│ Paper2Profile │
 │ registry      │──── hit ────────►│  orchestrator     │◄──────────│ generator     │
 │ (in-repo)     │                  └──────────────────┘ draft +    └───────────────┘
 └──────────────┘                            │          profile-diff.md     ▲
                                             ▼                              │
                                      ┌────────────┐            ┌──────────────────┐
                                      │  Binder +   │            │ Claim-template    │
                                      │  probes     │            │ library (+ engine │
                                      └────────────┘            │ recipes)          │
                                             ▼                   └──────────────────┘
                                      ┌──────────────────────────┐
                                      │ cross-verify engine       │──► compute target
                                      │ (planner, rounds,         │     (cluster agent / RM / local)
                                      │  verdicts)                │──► results.json, report.md
                                      └──────────────────────────┘
```

Components:
- **C1** agent introspector and manifest;
- **C2** claim-template library;
- **C3** profile schema v2 (and the mapping file);
- **C4** Paper2Profile generator;
- **C5** binder and probes;
- **C6** cross-verify engine (replaces the existing skill's v1 path);
- **C7** profile registry.

Design rule across all components: **the LLM proposes, a script gates.** Wherever an LLM produces something (claim extraction, binding candidates, target facts, request parameters), a script validates it against a schema and against the paper or the profile before anything downstream uses it.

## 5. Components

### C1. Agent introspector and manifest

P2A delivers no machine-readable description of an agent. The selection reports stay in its workspace. The introspector builds one from what is always delivered.

**Inputs:**
- the paper skill directory, whose layout is fixed: `SKILL.md`, `references/{index,paper,supplement}.md`, `assets/{figure,supp_figs,table,supp_table}/`;
- optionally, the agent's MCP server. The introspector reads the plugin's `.mcp.json`, launches the server itself over stdio, and calls `list_tools` (names, descriptions, input and output schemas);
- the package's `USAGE.md` and any data notes.

**Output:** `agent-manifest.json`, local and never shared.

```json
{
  "manifest_version": 1,
  "paper": {"doi": "10.1039/D2MA01088G", "title": "...", "detected_from": "paper.md front matter"},
  "paper_skill": {"path": "...", "sha256_tree": "...", "tables": ["assets/table/table-1.csv"],
                  "image_only_regions": ["supplement Figs S3–S8"]},
  "mcp": {"server": "small_cluster_isomers", "launch": {"command": "uv", "args": ["..."]},
          "tools": [{"name": "...", "description": "...", "input_schema": {}}]},
  "data_resources": [{"kind": "archive", "url": "https://archive.materialscloud.org/records/j7hwv-81q79"}],
  "p2a_mode": "paper_only | code_only | combined"
}
```

The introspector is deterministic code: a script, not an agent. It runs through `uv run --with mcp`, because it needs an MCP client; `uv` is already required to launch P2A servers. Paper-only P2A outputs produce a manifest with `mcp: null`.

### C2. Claim-template library

This is a versioned, code-independent catalogue of computable quantities. A profile may only reference templates; that rule is the main lever for consistency.

```yaml
id: vertical_ionization_energy
version: 1
quantity: "energy to remove one electron at fixed geometry"
definition: "VIE = E(N-1) - E(N), both at the relaxed N-electron geometry"
parameters:
  species: {type: species_ref, required: true}
  geometry: {type: enum, values: [source, relaxed], default: source}
units: eV
tolerance_class: ionization_affinity
synonyms: ["vertical ionization potential", "VIP", "vertical IE"]
not_equivalent_to: ["-epsilon_HOMO (Koopmans)", "adiabatic_ionization_energy"]
data_needs: [{need: structure, of: species, which: geometry}]
engine_recipes:
  bigdft:
    runs: ["sp(N)", "sp(N-1, spin_rule)"]
    extract: ["energy"]
    combine: "E[N-1] - E[N]"
    convergence:                      # used when the user asks for converged results
      knob: hgrid
      ladders: {quick: [0.40], standard: [0.45, 0.40, 0.35], tight: [0.45, 0.40, 0.35, 0.30, 0.25]}
      stop_rule: "|ΔE| between consecutive steps < 1 meV/atom"
```

- **Scope.** The full library covers what BigDFT computes: total, relative and binding energies; orderings; IE and EA, vertical and adiabatic; HOMO–LUMO and KS gaps; eigenvalue degeneracy; optimized geometry descriptors; dipoles and charges; and formation and reaction energies built from these. That is roughly 20–40 templates. **The prototype ships only the templates Fisicaro needs (about 5–8).**
- **`synonyms` and `not_equivalent_to`** drive claim discovery in C4. The negative list stops the generator from mapping a Koopmans IP onto a ΔSCF IE.
- **Engine recipes** are per engine, so a QE or CP2K engine could reuse the same templates later. Convergence ladders and stop rules live in the recipe, so an expert writes them once and every user inherits them.
- **Growth.** An unmatched claim in C4 goes to a `needs_template` queue, never into an improvised profile entry. New templates are reviewed by a domain expert and released as a new library version.
- **Prototype status:** templates ship as `draft` until a BigDFT expert reviews them (§13).

### C3. Profile schema v2 and mapping file

v1 is the current `bigdft-cross-verify/profile/1`. v2 replaces it; the v1 path is dropped (§10).

| v1 (exists) | v2 |
|---|---|
| free-text `computation` per claim | `template` + `parameters`, with optional `definition_note` only for documented variants |
| free-form `settings` list | **fixed setting keys**, each `value` + `quote` + `location`, or `unknown` |
| tool names inside `structures` / `reference_data` | **abstract data needs** (`structure`, `reference_value`, `dataset_property`), with no tool names |
| no structure identity | per-structure **`authority`** record + canonical **sha256** |
| citations as free text | `quote` (verbatim, ≤ 300 chars) + `location` (section, table, figure, equation) |
| BigDFT values mixed into the profile | moved to a separate `bigdft-mapping.json` |
| no status | `status`: `draft`, then `reviewed`, then `verified-by-run`, with reviewer records |

Fixed setting keys, the same for every paper:
- `code`, `code_version`
- `xc_functional`, `xc_per_element_exceptions`
- `basis_or_grid`, `pseudopotentials_or_projectors`
- `boundary_conditions`
- `spin_treatment`, `charge_states`
- `smearing_or_electronic_temperature`
- `scf_convergence`
- `geometry_relaxation_criterion`
- `dispersion_correction`, `solvation`
- `k_points`
- `structure_source`

Each key is filled with value + quote + location, or set to `unknown`. Keys that don't apply are `not_applicable` with a reason.

A claim in v2:

```json
{"id": "al13m1-vie", "template": "vertical_ionization_energy@1",
 "parameters": {"species": "Al13^-1", "geometry": "source"},
 "reference": {"value": 3.568, "unit": "eV", "confidence": "dataset",
               "quote": "...", "location": "dataset key Vertical-Ionization-energy"},
 "data_needs": ["structure:Al13^-1:global_minimum"]}
```

**Reference confidence.** `reference.confidence` is one of `table`, `text`, `dataset` or `figure`.
- Figure-only values are **digitised once, at review**, and stored in the profile with an explicit uncertainty (e.g. ± half a grid division). Claude never reads a plot at run time.
- Verdicts for `figure` claims are capped at `reproduced_trend`.
- `figure` claims are excluded from the default claim set of the `quick` preset.
- If the same quantity is also in a dataset, the dataset value is the reference and the figure value is only a cross-check.

**Structure authority and canonical hash.** Each structure need carries an authority record and a hash:

```json
"structure:Al13^-1:global_minimum": {
  "authority": {"kind": "dataset", "locator": "materialscloud:j7hwv-81q79/…", "precision_A": 1e-5},
  "charge": -1, "multiplicity": 1,
  "sha256": "…"
}
```

- **Canonical form (code, global):** atoms sorted by (element, x, y, z); coordinates in Å; centred at the centroid; rounded to the authority's `precision_A`; serialised with fixed formatting.
- **Authority (data, per structure).** The prototype implements two cases:
  - **Case 1, machine-readable coordinates** (Materials Cloud, Zenodo, NOMAD, SI `.xyz`, a code repository): hash at the source's precision. Fisicaro is this case.
  - **Case 2, coordinates printed only in the paper or SI** (e.g. a PDF table to 3 decimals): canonicalised from the paper-skill table at the printed precision. Tested with a synthetic fixture derived from Fisicaro.
- Case 3, where no coordinates are published, is deferred (§14).

The hash does three jobs: it identifies the right isomer (composition alone can't, in an isomer database), it makes the run plan byte-identical across agents, and it checks the agent's data against the paper.

**Mapping file.** `bigdft-mapping.json` sits next to the profile in the registry. For every setting key it gives `bigdft_value`, `status` (`exact`, `approximated` or `not_mappable`) and `note`. It also lists the PSP files with their sha256, and any tolerance overrides with a reason. It is reviewed once and never filled at run time. A future QE engine adds `qe-mapping.json` alongside it, with no change to the profile.

Structural checks are `validate_profile.py` (profile and mapping). Semantic checks happen in C4.

### C4. Paper2Profile generator

This is a skill plus helper scripts. It turns a manifest and the paper skill into a profile draft through gated stages. Every gate is mechanical unless marked *review*.

**In the prototype, generation is opt-in (`--generate`) and never feeds a run.** The normal path is a registry hit. With `--generate`, the generator runs S1–S5 and then diffs its draft against the registry profile (S6′). The run always uses the registry profile. The README states this explicitly.

| Stage | Work | Gate |
|---|---|---|
| S1 Scope | Read `index.md`; find the Methods/Computational details, results tables and SI sections | Methods located, or the profile is marked `methods_not_found` |
| S2 Settings | Fill the fixed setting keys, with quote + location | **Quote check**: each quote is found in the paper skill after normalisation (`<sub>`/LaTeX/Unicode minus/whitespace) |
| S3 Claim discovery | Scan tables, captions and results text; map candidates to templates via synonyms; list unmatched claims in `needs_template`, and claims outside BigDFT's scope in `excluded` | Every claim has a template id, and every reference value has a quote or table cell |
| S4 Data needs | Derive data needs from template parameters; mark needs that only image-only content can satisfy | Each need is typed; image-only references are flagged `confidence: figure` |
| S5 Schema | v2 validation | `validate_profile.py` passes |
| S6′ Diff against registry (prototype) | Canonical diff of the draft against the registry profile: settings, claim sets, parameters, references | `profile-diff.md` written; empty, or each difference listed |
| S6 Dual generation (*deferred*) | A second, independent generation from scratch; canonical diff | The diff is empty, or each difference is listed for review |
| S7 Review (*deferred to the miss flow*) | A fresh reviewer agent, then the human, check every setting and claim against the paper | *review*; `status` set to `reviewed` with reviewer identities |

Text normalisation is part of the generator, because P2A paper skills mix notations. It applies identical rules to quotes and to the paper text: HTML sub/superscripts become plain text, LaTeX is stripped to symbols, Unicode minus becomes a hyphen, and whitespace is collapsed.

The `profile-diff.md` files that developers send back measure generator consistency across machines and P2A agents.

### C5. Binder and probes

The binder runs on the researcher's machine and maps each abstract data need to a concrete source. It follows the propose/gate rule:

1. **Propose (LLM).** Claude reads the manifest and the profile's data needs and writes `binding-candidates.json`: for each need, one or more candidate sources (an MCP tool with its argument mapping, a file in the paper skill, a `data_resources` entry). Matching a need to an arbitrary tool name and description is semantic, so this step stays with the LLM.
2. **Gate (script).** `probe_bindings.py` launches the MCP server itself (`uv run --with mcp`), calls each candidate on probe cases, and accepts or rejects it:
   - **Scalar references:** a species with a reference value quoted from the paper. Accept if the returned value matches within the paper's printed precision. For example, Table 1 prints a gap of 1.88 eV, so the tool's value must round to 1.88.
   - **Structures:** canonicalise what the source returns at the authority's precision, then compare with the pinned sha256. Accept on a match. A source that is less precise than the authority is matched by RMSD after alignment (threshold from the authority's precision), and the **registry's canonical structure** is then used, so the plan bytes stay identical.
3. **Fallbacks, in order:** paper-skill tables or SI coordinates; downloading the archive named in `data_resources`; asking the user for files. Every source used is recorded with its hash.
4. **Unbound needs** make the dependent claims `inconclusive (missing_structure | missing_reference)`. They are never filled by inventing data.

Output: `bindings.json`, local and recorded in the run's results. Only accepted bindings appear in it.

The probes do two jobs. They verify the mapping, and they check that the agent's data and the paper agree. A failing probe on a correctly identified tool is itself a finding, reported as `data_paper_mismatch`; the dependent claims are `inconclusive`. There is no "close enough".

### C6. Cross-verify engine

These changes to the existing `bigdft-cross-verify` move judgment out of the LLM wherever the inputs allow.

**Plan parameters.** The user talks to Claude in natural language ("check the ionization energies", "just a quick look", "do it properly, converged", "only Al13⁻"). Claude's job is to turn that into `params.json`, validated against a schema:
- `claims`: a list of claim ids, or a named set (`default`);
- `preset`: `quick`, `standard` or `tight`, selecting the convergence ladder in each template recipe;
- `species` filter;
- `overrides`: explicit expert changes (e.g. "hgrid 0.25, no scan"), each with a reason. An override changes the plan hash, and the report marks those results as *not comparable with the reference profile*.

**Physics plan (target-independent).** `plan_runs.py`: profile + mapping + bindings + params → `run-plan.json`.
- Claims expand through template engine recipes; shared runs are deduplicated; dependencies are explicit (e.g. N and N−1 share a geometry).
- Each run carries its full BigDFT input YAML, canonical `posinp`, and PSP files by sha256.
- Convergence is a **ladder plus stop rule**, not a fixed list and not a free choice.
- Output is canonical (sorted keys, fixed float formatting), so the same inputs give a **byte-identical file on any machine and any cluster**.

**Target (resources only).** Claude resolves the target from the cluster agent's own docs, as in v0.1.0, and writes `target.json`: module/build, BigDFT version, MPI×OMP, walltime, scratch path. A schema check gates it. **Nothing in `target.json` may change a number in the BigDFT input.** If the target can't run the plan as written (a missing PSP, not enough memory for the grid), that is reported as a target failure. Claude does not adjust the physics.

**Execution in rounds.**
1. Claude submits the current batch through the cluster agent's `submit_job`, after per-batch user approval.
2. Results are parsed via `bigdft:logfile`.
3. `next_round.py`: run-plan + parsed results → the next batch, or "converged at step k" per claim. A script decides, not Claude.

**Verdicts.** `compute_verdicts.py`: parsed results + profile + mapping (tolerance overrides) + tolerance table → `results.json`.

| Today (v0.1.0) | Prototype |
|---|---|
| The LLM plans runs from claim text | `plan_runs.py` → byte-identical `run-plan.json` |
| Convergence decided ad hoc | Ladder + stop rule from the template, advanced by `next_round.py` |
| The LLM computes verdicts | `compute_verdicts.py` |
| Profile path is a user input | Registry-first lookup by DOI (C7); generation only with `--generate` |
| Settings map written by the LLM at run time | `bigdft-mapping.json`, reviewed once, read from the registry |
| Physics and machine mixed | `run-plan.json` and `target.json` separate |

Unchanged:
- target resolution from the target's own docs;
- per-batch user approval;
- parsing via `bigdft:logfile`;
- the verdict vocabulary;
- the output contract, extended with `bindings.json`, `run-plan.json`, `target.json` and version stamps (§7).

### C7. Profile registry

In the prototype, the registry is a **`registry/` directory inside the plugin repo**, keyed by DOI and read-only.

```text
registry/
  10.1039_D2MA01088G/
    profile.json            # v2, status reviewed
    bigdft-mapping.json     # status draft in the prototype
    structures/             # canonical structures referenced by sha256
    REVIEW.md               # reviewers, dates, artifact sha256, decisions
  INDEX.json                # DOI → profile version + sha256
```

- **Lookup:** the orchestrator resolves the DOI from the manifest and reads the profile and mapping from `registry/`, pinned by sha256.
- **Versioning:** profiles and mappings are immutable once released; corrections create a new version with a changelog. Because the registry ships with the plugin, a registry update is a plugin release.
- **Trust:** profiles and mappings are data only. The engine never executes anything from them, and registry content passes the same validator as local content.
- Contributions and an external registry are deferred (§14).

## 6. End-to-end flows

**Normal flow: registry hit (the default)**
1. `p2a_introspect.py` builds the manifest from the developer's P2A agent.
2. The orchestrator looks up the DOI in `registry/` and gets the profile and mapping.
3. Claude proposes binding candidates; `probe_bindings.py` gates them and writes `bindings.json`.
4. Claude turns the user's request into `params.json`; `plan_runs.py` writes `run-plan.json`.
5. Claude resolves the target from the cluster agent's docs and writes `target.json`.
6. Rounds: the user approves each batch, the runs execute, and `next_round.py` decides what comes next.
7. `compute_verdicts.py` writes `results.json`, stamped with all hashes (§7), and the report is generated.

**Opt-in: `--generate`**
- Same as the normal flow, plus C4 S1–S5 on the developer's paper skill and S6′ against the registry profile, producing `profile-diff.md`.
- The run still uses the registry profile.

**Paper-only agent (no MCP server)**
- The same flows apply; the binder falls back to SI and table coordinates or to archive downloads.
- If no structures can be found, structure-dependent claims are `inconclusive (missing_structure)`, and the report says so up front.

The miss flow, where no registry entry exists and the run uses a generated, reviewed profile, is deferred (§14).

## 7. Provenance

Every `results.json` records:
- profile id, version, status and sha256;
- mapping version, status and sha256;
- template library version, and the status of each template used;
- profile schema version;
- `bigdft-cross-verify` version;
- `bigdft-skills` version;
- manifest, `bindings.json`, `params.json`, `run-plan.json` and `target.json` sha256;
- overrides, if any;
- compute target and BigDFT build identity (module, version);
- pseudopotential files with their sha256;
- per claim: the convergence step the stop rule chose.

Two results for the same claim are comparable only if their `run-plan.json` hashes match. The report states this. While the mapping or templates are `draft`, the report labels results *unreviewed mapping*.

## 8. How consistency is achieved (summary)

| Mechanism | Removes this variation |
|---|---|
| Template library + negative synonyms | different definitions of "the same" quantity |
| Fixed setting keys | settings forgotten, or invented under ad-hoc names |
| Quote check after normalisation | hallucinated settings and claims |
| Abstract data needs + probes | dependence on tool names and per-run P2A tool choices |
| Canonical structures + pinned hashes | wrong isomer, formatting differences between sources |
| Reviewed mapping file | per-run PSP and settings-mapping choices |
| Plan/target split | physics changed silently to fit a machine |
| Planner, round and verdict scripts | differences in run plans, convergence stops and verdict arithmetic |
| Registry diff of generated profiles | residual extraction randomness, made visible |
| Registry reuse | every researcher regenerating their own profile |
| Provenance stamps | results that can't be compared |

The judgment that remains is made **once, at review, and recorded**:
- pseudopotential choice when the exact file is unknown, and the mapping of `approximated` / `not_mappable` settings (in `bigdft-mapping.json`);
- tolerance overrides (in `bigdft-mapping.json`, with a reason);
- digitised figure values (in `profile.json`, with uncertainty).

At run time the LLM chooses only binding candidates (gated by probes), target resources (unable to touch physics) and request parameters (overrides recorded and flagged).

## 9. Packaging

One plugin, `bigdft-cross-verify` v2, with Paper2Profile included. Low coupling comes from file contracts, not plugin boundaries:

```text
bigdft-cross-verify/
  skills/
    cross-verify/        # orchestrator: the only skill a user talks to
    paper2profile/       # C4, invoked only with --generate
  scripts/               # each is a standalone CLI, run via `uv run`
    p2a_introspect.py    #  .mcp.json + paper skill → agent-manifest.json
    validate_profile.py  #  profile.json / bigdft-mapping.json → pass/fail
    quote_check.py       #  profile + paper skill → pass/fail
    canonical_structure.py  # structure + precision → canonical bytes + sha256
    probe_bindings.py    #  profile + manifest + binding-candidates → bindings.json
    plan_runs.py         #  profile + mapping + bindings + params → run-plan.json
    next_round.py        #  run-plan + parsed results → next batch | converged
    compute_verdicts.py  #  parsed results + profile + mapping → results.json
    diff_profiles.py     #  profile A + B → profile-diff.md
  schemas/               # JSON Schema for every file above
  templates/             # claim-template library (YAML)
  registry/              # C7
  tests/fixtures/        # incl. the synthetic case-2 paper-skill table
```

Rules:
1. Scripts never import each other. They share only `schemas/` (and `canonical_structure.py` is called as a CLI, not imported).
2. Every intermediate file is validated against its schema when it is written and when it is read.
3. Each script runs standalone, so a developer can rerun or replace one stage.
4. The orchestrator skill holds no logic. It sequences the steps and does the three LLM jobs: binding candidates, target resolution, and request → parameters.

Paper-specific content lives only in the registry and in P2A agents that choose to bundle a profile.

## 10. Migration from today

- **Fisicaro 2023 profile.** It is v1 and names our MCP tools. Convert it to v2 (templates, fixed setting keys, abstract data needs, quotes, structure authorities and hashes, digitised figure values) plus a `bigdft-mapping.json`, and make it the first registry entry.
- **`bigdft-cross-verify` v0.1.0.** The v1 path is **dropped**, with no version switch. v0.1.0 has no external users, and carrying two engines adds coupling.
- **P2A-Fisicaro-2023 repo.** The `fisicaro2023-bigdft-profile` skill (prepared, not pushed) becomes a pointer to the registry entry.

## 11. Optional upstream proposal to P2A

Once the introspector works, propose two optional P2A additions: an `agent-manifest.json` in its deliverables, and an optional "reproduction profile" stage that runs C4 after the paper skill and MCP stages. Neither is required; the introspector covers the gap.

## 12. Acceptance

### Handoff acceptance (on another developer's machine)

| Level | Developer does | Passes when | Shows |
|---|---|---|---|
| L0 Dry run | Install the plugin + their own P2A agent; run through `plan_runs.py`, no cluster | All probes pass, or each mismatch is reported with a reason; `run-plan.json` **sha256 equals ours** for the same parameters | Bridge and portability (points 1, 2), with zero compute |
| L1 Quick run | Add their cluster agent; `quick` preset, 2–3 claims (e.g. Al13⁻ VIE + one gap) | `results.json` with full provenance; verdicts match ours within the tolerance class | End to end on a foreign cluster |
| L2 Generate | `--generate` | `profile-diff.md` produced; empty, or every difference explained | Less LLM freedom (point 3) |

Developers send back `agent-manifest.json`, `bindings.json`, the `run-plan.json` hash, `results.json` and, for L2, `profile-diff.md`. All are small files; no logs.

### Our gate before handoff

- L0, L1-planning and L2 pass on **both** existing P2A agents for Fisicaro 2023 (ours and the Codex run). The Codex agent's missing structure tool is reported, then resolved through the archive fallback, and its `run-plan.json` hash equals ours.
- L1 passes on IMLab with real BigDFT.
- Same inputs give a byte-identical `run-plan.json` across repeated runs; `next_round.py` and `compute_verdicts.py` have unit tests.
- The synthetic case-2 fixture binds through the RMSD path and produces the same plan hash.

### Build order

| Milestone | Deliverable |
|---|---|
| M1 | Fisicaro templates (≈5–8, `draft`) + schema v2 + mapping schema + validator + Fisicaro v2 profile and mapping |
| M2 | Introspector + normalisation + quote checker + canonical structures |
| M3 | Binder + probes (both agents, archive fallback, case-2 fixture) |
| M4 | `plan_runs.py` + `next_round.py` + `compute_verdicts.py` → L0 passes |
| M5 | Generator S1–S5 + S6′ diff → L2 passes |
| M6 | Real run on IMLab → L1 passes; README written, stating that the default is a registry hit and generation is opt-in |

## 13. Prototype review status

- `profile.json`: reviewed by a fresh reviewer agent (S7) and by us; `status: reviewed`.
- `bigdft-mapping.json` and `templates/`: **`draft`** until a BigDFT expert reviews them. The README says so, and results are labelled *unreviewed mapping*.
- Target state, once an expert is available: mapping signed off by us plus one BigDFT expert; templates signed off by one domain expert. Every sign-off is recorded in `REVIEW.md` with name, date and artifact sha256.

### Open questions

1. **Licensing.** Quotes are short excerpts (≤ 300 chars), which should be fine for CC BY papers; is that still true for closed-access ones? Do registry entries for closed papers drop quotes and keep only locations?
2. **Template ownership.** One library shared across engines, or per-engine forks?
3. **Dual generation.** Once papers without a registry entry are supported, should S6 be required for `reviewed` status, or only recommended?
4. **Bundling.** Should P2A agents bundle a snapshot of their profile (offline use) or always resolve through the registry?
5. **Registry governance.** Once the registry accepts contributions: who reviews them, and how many sign-offs make `reviewed`?

## 14. Deferred designs

Recorded so they can be implemented later without re-deciding.

**D1. Registry with a configurable source (option C).** The registry client accepts `--registry <path-or-git-url>`, with the bundled `registry/` as the default. The interface stays "DOI in, profile path + sha256 out", so moving to a separate repo changes only the default. Adds contributions by pull request, with CI running schema validation and the quote check (using the contributor-supplied paper skill hash where licensing allows), and contributed `results.json` files under `results/`.

**D2. Miss flow: run on a generated profile.** With no registry entry (or `--generate --use-generated`), the generator runs S1–S7, including human sign-off, and the run uses the generated profile. Results are comparable with others only if their profile hashes match. Needed once a second paper is supported.

**D3. Dual generation (S6).** A second, independent generation from scratch, with a canonical diff, for papers with no registry entry to diff against.

**D4. Structure authority case 3: no coordinates published.** The paper states only how structures were obtained ("we relaxed the structures with PBE…"). No hash against the paper is possible; claims are marked `structure_provenance: reconstructed`, and the report says geometry is not verified against the paper. Three reconstruction routes:
- **R1 Registry-shipped:** a reviewer builds the structure once; it ships in `registry/…/structures/` with its hash, authority `reconstructed_by_reviewer`. Same bytes for everyone.
- **R2 User-supplied:** the user gives a file; it is canonicalised and hashed, and the hash is recorded in `bindings.json`. Deterministic within one user only, so the L0 hash differs across users unless the file is shared.
- **R3 Relax recipe:** the profile gives a starting structure and "relax with the paper's settings"; `plan_runs.py` emits a relax stage before the claim runs. The plan is identical across users, but the relaxed geometry may differ slightly across BigDFT builds. This couples structure binding to compute and to the round executor.

**D5. Two plugins.** Split Paper2Profile (generator) from the engine if their release cycles diverge. File contracts already provide the decoupling, so the split is only about distribution.

**D6. Other engines.** QE or CP2K engines add their own recipes in the templates and their own `<engine>-mapping.json` per paper; profiles are unchanged.
