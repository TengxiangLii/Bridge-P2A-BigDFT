---
name: bigdft-cross-verify
description: Use when re-running a paper's reported calculations with BigDFT to double-check its results, whether the paper used BigDFT itself or another code (VASP, Quantum ESPRESSO, Gaussian, CP2K, ...), on any compute resource the user chooses (an HPC cluster agent, RemoteManager, or a local build).
---

# BigDFT cross-verification

## Overview

This skill recomputes the claims of one paper with BigDFT and gives each claim a verdict from a fixed vocabulary. All paper-specific facts come from a **reproduction profile**, a JSON file with the schema in [profile-schema.md](profile-schema.md). The compute resource is a parameter. The skill itself holds no facts about any paper or cluster.

Use the `bigdft:*` skills for the mechanics:

| Task | Skill |
|---|---|
| Write input files | `bigdft:input` |
| Set up pseudopotentials | `bigdft:pseudopotentials` |
| Build and convert structures | `bigdft:systems` |
| Parse logfiles | `bigdft:logfile` |
| Run through RemoteManager | `bigdft:remote`, `bigdft:dataset` |

## Inputs

| Input | Meaning |
|---|---|
| `profile` | Path to the paper's reproduction profile. If none exists, draft `profile.json` from the paper using [profile-schema.md](profile-schema.md) and validate it. Then **stop and ask the user to review it**. Do not create any other workdir files until the user has approved the profile. |
| `compute_target` | Where BigDFT runs: the name of an installed cluster agent (e.g. `imlab`, `tsubame`, `psc`, `fugaku`), `remotemanager`, or `local`. Ask the user if it is not given. |
| `claims` | Optional subset of claim IDs from the profile. Default: the profile's `default_claims`. |
| `workdir` | Optional; defaults to `./bigdft-verify/<profile.id>/`. |

## Workflow

1. **Validate the profile**: `python3 <skill-dir>/validate_profile.py <profile>`, then copy it to `profile.json`.
2. **Resolve the compute target** from that target's own documentation, never from memory:
   - Cluster agent: load `<target>:<target>-reference` and `<target>:<target>-submitting-jobs`.
   - `remotemanager`: follow `bigdft:remote`.
   - `local`: check PATH for `bigdft`, or follow `bigdft:install`.

   Write `target.json`. If the documentation does not confirm how BigDFT is provided (module, version, MPI stack, path), your first approval request is only the read-only checks that would confirm it (e.g. `module avail bigdft`, `module show bigdft`). Plans made before those checks are marked provisional.
3. **Write the settings map** (`settings-map.json`, format in [report-contract.md](report-contract.md)). It has one row for every source setting and every `unknown_settings` entry.

   | Status | When |
   |---|---|
   | `matched` | BigDFT uses the same setting. |
   | `approximated` | Close but not identical: e.g. a pseudopotential from the cited family whose exact file is unknown, or a spin moment the paper did not state. |
   | `not_mappable` | The setting has no BigDFT counterpart (PAW, a plane-wave cutoff, a Gaussian basis set). Record what replaces it. When the setting controls numerical accuracy, the BigDFT grid is set by the convergence scan instead. |
   | `unknown` | The source does not state the setting. |

   The profile's `affects` lists are a minimum. Add any claim you find that a setting also affects, and say why in `note`.
4. **Prepare the structures** following `profile.structures`:
   - Convert units explicitly, and drop blocks that are not coordinates.
   - Set charge and spin from `profile.electronic_state_rules`, with the electron count taken from the pseudopotential valence charges.
   - Choose pseudopotentials generated for the functional in use, never one made for a different functional. If the exact file is unknown, take one from the cited family (see `bigdft:pseudopotentials`), record where it came from and its sha256, and mark it `approximated`.
   - Save each structure file and its sha256 under `structures/`.
5. **Plan the runs** in `run-plan.json`. Each run lists the claims it serves, so one single point can serve several claims. The batches, in order:
   0. **Availability** (only if step 2 left BigDFT unconfirmed). This batch has an empty `runs` list and a `commands` list of read-only checks.
   1. **Convergence scan**, at the source geometries:
      - Systems: the reference structure of each claim system, plus every structure that enters a relative-energy or ordering claim.
      - Scan `hgrid` from 0.45 to 0.30 bohr in steps of 0.05, at `rmult` [6, 8].
      - If any claim involves anions, virtual orbitals or electron affinities, also scan `rmult` [5, 8], [6, 8] and [7, 9] at the converged `hgrid`.
      - The grid is converged when every affected claim quantity changes by less than tolerance/5 between successive grids. For degeneracy claims, the largest splitting within each group must also stay below the degeneracy threshold.
      - Claims derived from a geometry (bond length, point group) are not scanned. They use relaxations done at the converged grid.
   2. **Production runs** at the converged grid, using the geometry each claim's `computation` names.
      - Energies of relaxed structures come from the final relaxation step, which uses the same settings.
      - Gaps and eigenvalues come from a separate single point with virtual orbitals.
      - Input keys, including virtual orbitals and the relaxation method, follow `bigdft:input`. Record the choice in `run-plan.json`, and check it on the first completed run.

   Job size: follow the target documentation, rounding to the target's nearest allowed resource shape. Where the docs have nothing on BigDFT, use at most one MPI rank per occupied orbital (per spin channel) and fill the remaining cores with OpenMP threads. Run one calculation per job.

   Files in `runs/` written before availability is confirmed are marked `provisional`. If a structure or pseudopotential file is not available yet, record its path with a null sha256. Production does not start until all of those hashes are filled in.

   Show the user the plan and job specs, and get explicit approval before each batch.
6. **Run and monitor** with the target's own tools and skills (e.g. `imlab:imlab-submitting-jobs`, `imlab:imlab-monitoring-jobs`). Keep each run's input, log and exit status under `runs/<run-id>/`.
7. **Parse** with `bigdft:logfile`. A run counts as usable only if its SCF converged, and, for relaxations, if the force criterion was met.
8. **Give verdicts** and write `results.json` and `report.md` as described in [report-contract.md](report-contract.md).

## Geometry per claim

The claim's `computation` states which geometry it uses. If it doesn't:

- **`same_code`:** use the source geometries, which are already minima at the source settings.
- **`cross_code`:** use the BigDFT-relaxed geometries for the verdict, and also report the source-geometry values as diagnostics. The two together separate method differences from structural relaxation.

## Verdicts and tolerances

| Verdict | Meaning |
|---|---|
| `reproduced` | Within the claim's tolerance. For orderings: the order is preserved and every energy difference is within tolerance. |
| `reproduced_trend` | Outside tolerance, but the claim's `qualitative_property` holds. For orderings: the order is preserved but some energy differences are outside tolerance. Not available when the claim has no `qualitative_property`. |
| `not_reproduced` | Outside tolerance and the qualitative property fails. For orderings: the order changes. |
| `inconclusive` | Cannot be judged. Give one reason: `unconverged`, `run_failed`, `unknown_setting_dominates`, `missing_reference`, or `definition_ambiguous`. |

Categorical claims (point group, degeneracy pattern) take only `reproduced`, `not_reproduced` or `inconclusive`.

Tolerances come from the claim's `tolerance_class` and the profile's `tier`. The profile's `tolerance_overrides` may change them, but every override needs a reason. Defaults:

| Class | `same_code` | `cross_code` |
|---|---|---|
| `relative_energy` (eV) | 0.005 | 0.05 |
| `absolute_energy` (Ha) | 0.001, diagnostic only | not a claim |
| `orbital_gap` (eV) | 0.02 | 0.15 |
| `ionization_affinity` (eV) | 0.05 | 0.15 |
| `bond_length` (Å) | 0.01 | 0.03 |

- **Absolute energies:** under `cross_code`, compare only energy differences. Under `same_code`, an absolute energy is diagnostic if any setting affecting it is `unknown` or `approximated`: it goes into `report.md` without a verdict.
- **Global minimum claims:** a claim that a structure is the global minimum can only be tested among the structures supplied. Word its verdict as "lowest among N supplied structures". Confirming a true global minimum needs a structure search, which is outside this workflow.
