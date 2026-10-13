# bigdft-cross-verify (paper-independent)

This skill re-runs a paper's reported calculations with [BigDFT](https://bigdft.org) and gives each claim one verdict: `reproduced`, `reproduced_trend`, `not_reproduced` or `inconclusive`. It works whether the paper used BigDFT itself or another code (VASP, Quantum ESPRESSO, Gaussian, ...).

This plugin knows nothing about any specific paper or cluster. It takes two inputs:

| Input | Where it comes from |
|---|---|
| **Reproduction profile** | A JSON file with one paper's settings, unknown settings, structures, claims and exclusions (schema in `bigdft-cross-verify/profile-schema.md`). Example: `../paper-specific/fisicaro2023/`. If none exists, the skill drafts one and stops for review. |
| **Compute target** | Where BigDFT runs. Either an installed cluster agent (e.g. `imlab`, `tsubame`, `psc`, `fugaku`), `remotemanager`, or `local`. |

## Requirements

- **BigDFT skills** for input writing, pseudopotentials, structures and logfile parsing:
  ```
  /plugin marketplace add william-dawson/bigdft-skills
  /plugin install bigdft@bigdft-skills
  ```
- **A way to run BigDFT:** a cluster agent plugin for your machine, a RemoteManager setup, or a local build.

## What it enforces

- **Settings map:** every source setting is mapped to BigDFT and marked `matched`, `approximated`, `not_mappable` or `unknown`.
- **Grid convergence:** a scan with a fixed acceptance rule, before any production run.
- **Explicit approval:** every job batch is approved by you before it is submitted.
- **Fixed tolerances:** defaults per quantity, set by whether the paper used BigDFT (`same_code`) or another code (`cross_code`). Absolute energies are never compared across codes.
- **Fixed output files:** `settings-map.json`, `run-plan.json`, `results.json` and `report.md` (see `report-contract.md`).

## Status

The skill has passed planning-only tests on two compute targets (IMLab and TSUBAME), one same-code case and one cross-code case, up to the job-submission approval gate. It has not yet been run end-to-end with a real BigDFT calculation.
