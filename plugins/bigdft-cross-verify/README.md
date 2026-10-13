# bigdft-cross-verify (v2 prototype)

Re-verify a paper's calculations with [BigDFT](https://bigdft.org), starting from an agent built with [Paper2Agent](https://github.com/jmiao24/Paper2Agent) (P2A). The design is in [`docs/paper2profile-infra.md`](../../docs/paper2profile-infra.md).

**Prototype scope:** one paper, Fisicaro et al., *Principles of isomer stability in small clusters*, Mater. Adv. 2023 (doi:10.1039/D2MA01088G).

**The default path is a registry hit.** The run always uses the reviewed profile in `registry/`. Generating a profile (`--generate`) is opt-in, produces only a draft plus a diff against the registry, and never feeds a run.

## What you bring

| You bring | Why |
|---|---|
| Claude Code and [`uv`](https://docs.astral.sh/uv/) | Every script runs with `uv run`; dependencies are declared inline. |
| **Your own** P2A agent for the paper: its paper skill, and its MCP server if it has one | It may use different tool names and tool boundaries from ours, or have no structure tool at all. The plugin binds to it without changes. |
| A compute target: a cluster agent plugin (e.g. one ported from `imlab`), RemoteManager, or a local BigDFT | Only resources come from it; it can't change the physics. |
| `bigdft@bigdft-skills` (`/plugin marketplace add william-dawson/bigdft-skills`) | Background for the agent on BigDFT. The scripts themselves don't need it. |

## Install

```
/plugin marketplace add TengxiangLii/Bridge-P2A-BigDFT
/plugin install bigdft-cross-verify@bridge-p2a-bigdft
```

Then ask, for example: *"Re-verify the HOMO–LUMO gap and degeneracy claims of the Fisicaro 2023 paper with BigDFT on imlab, quick look."* The `cross-verify` skill takes it from there.

## How it works

```text
your P2A agent ──► p2a_introspect ──► agent-manifest.json
registry/<doi>/  ──► profile.json (paper facts) + bigdft-mapping.json (engine choices) + structures/ + psp/
Claude proposes ──► binding-candidates.json ──► probe_bindings (script gate) ──► bindings.json
Claude: request ──► params.json ──► plan_runs ──► run-plan.json   (byte-identical on any machine)
Claude: target  ──► target.json   (resources only)
rounds: export_runs → submit (your approval) → parse_logs → evaluate_claims → next_round
compute_verdicts ──► results.json + report.md
```

| Script | In → out |
|---|---|
| `p2a_introspect.py` | paper skill + `.mcp.json` → `agent-manifest.json` |
| `validate.py` | any file → schema (and cross-reference) check |
| `quote_check.py` | profile + paper skill → every quote and table cell found |
| `canonical_structure.py` | structure + precision → canonical bytes + sha256; RMSD compare |
| `probe_bindings.py` | profile + manifest + candidates → `bindings.json` (accepted only by hash, RMSD or exact value) |
| `plan_runs.py` | profile + mapping + bindings + params → `run-plan.json` |
| `export_runs.py` | plan (+ round) → run directories |
| `parse_logs.py` | BigDFT logs → `parsed-results.json` |
| `evaluate_claims.py` | parsed results → claim values per ladder step |
| `next_round.py` | claim values → next batch, or converged |
| `compute_verdicts.py` | everything → `results.json`, `report.md` |
| `diff_profiles.py` | two profiles → `profile-diff.md` |

How the design is applied:
- **Independent scripts:** scripts never import each other; they share only `schemas/`.
- **Three judgment jobs:** Claude does only binding candidates, request → parameters, and target resolution, and a script gates each one.

## Acceptance levels (what to run, what to send back)

| Level | You do | Passes when |
|---|---|---|
| **L0 dry run** | Install the plugin and your P2A agent. Ask for the default claims with the `standard` preset, and stop after the plan, with no cluster. | All probes pass, or each mismatch is reported with a reason; your `run-plan.json` sha256 equals ours: `bfaea0fb0c2d6db2fc2e3c8810b7d36b6447887da319c6a04072434f279d222e` (default claims, `standard` preset, profile 2.0.0, mapping 1.0.0) |
| **L1 quick run** | Add your cluster agent. Ask for 2–3 claims with the `quick` preset, e.g. Al13⁻ gap, degeneracy and VIE. | `results.json` with full provenance; verdicts match ours within the tolerance class |
| **L2 generate** | Add `--generate` to the request. | `profile-diff.md` produced: empty, or every difference explained |

Send back these small files (no logs): `agent-manifest.json`, `bindings.json`, the `run-plan.json` sha256, `results.json`, and for L2 `profile-diff.md`.

## Our results so far (2026-10-13)

| Level | Result |
|---|---|
| L0 | Our agent and a simulated foreign agent (different tool names, no structure tool; a fresh Claude driven by a plain-language request) produced the same `run-plan.json`: `bfaea0fb…` |
| L1 (IMLab, `quick`, 2 jobs) | Al13⁻ gap 1.8886 vs 1.8821 eV: **reproduced**. Degeneracy [1,3,5,1,3,3,4]: **reproduced**. VIE: **inconclusive (unconverged)**: the open-shell neutral Al13 SCF stopped at gnrm 1.1e-3 after 3×100 iterations (infocode 1). Fixing this is a mapping decision for the BigDFT expert review, not a run-time change. |
| L2 | With the fixed generation rules, a fresh agent's generated profile matches all 12 registry claims: **0 scientific differences** |

## Review status

| Artifact | Status |
|---|---|
| `registry/10.1039_D2MA01088G/profile.json` | reviewed (S7 reviewer agent + us), see `REVIEW.md` |
| `bigdft-mapping.json`, `templates/` | **draft**: not yet reviewed by a BigDFT expert. Results carry the label *unreviewed mapping*. |

## Known limits of the prototype

- **One paper.** The miss flow (a run on a generated profile), dual generation and an external registry are deferred (design §14).
- **Elements.** Pseudopotentials are mapped for Al and Si only (SS NLCC files from PyBigDFT). Mg needs LDA, and Na and Ge have no file, so claims for those elements are reported as unplannable.
- **Absolute energies.** They are diagnostic only, because the paper's exact pseudopotential files are unknown.
- **No relaxation recipe yet.** Point group, average bond distance and shape factor are listed under `needs_template`.

## Development

```bash
uv run --python 3.12 --with pytest --with jsonschema --with pyyaml==6.0.2 --with numpy pytest tests
```

`tests/fixtures/` holds the following. All real BigDFT logs in it come from IMLab.

| Fixture | What it is |
|---|---|
| `alt_agent/` | A simulated foreign P2A agent: different tool names, no structure tool |
| `case2/` | Coordinates printed only in a paper table: rotated frame, 3 decimals |
| `logs/` | Three real BigDFT logs for the Al13⁻ global minimum |
| `target-imlab.json` | The IMLab target file |
