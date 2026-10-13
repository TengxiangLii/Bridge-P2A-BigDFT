---
name: cross-verify
description: Use when the user wants to re-run, recompute, re-verify or double-check the calculations of a paper with BigDFT, starting from a Paper2Agent (P2A) agent for that paper (its paper skill and MCP server) and a compute resource such as a cluster agent (imlab, tsubame, psc, fugaku), RemoteManager or a local BigDFT.
---

# Cross-verify a paper with BigDFT

You sequence scripts. Every number in a BigDFT input, every convergence decision and every verdict comes from a script or a reviewed registry file, never from you. You have exactly three jobs that need judgment. Each one is checked by a script before anything uses it:

1. propose binding candidates (`probe_bindings.py` gates them);
2. turn the request into `params.json` (schema-validated);
3. resolve the compute target into `target.json` (schema-validated; it can't touch the physics).

`PLUGIN` is the directory two levels above this file. Run every script as `uv run -q PLUGIN/scripts/<name>.py`; `--help` shows its arguments. Work in `WORK=./bridge-verify/<doi-key>/`, where the DOI key is the DOI with `/` replaced by `_`, e.g. `10.1039_D2MA01088G`.

## Inputs

| Input | How to get it |
|---|---|
| P2A paper skill | The installed skill folder of the paper (its `SKILL.md` sits next to `references/paper.md`). |
| P2A MCP server | A Claude-style config file `{"mcpServers": {name: {command, args, env}}}`: the P2A agent's own config (its plugin's `.mcp.json`, or a file the user names), never this plugin's. If the server was added with `claude mcp add`, write `WORK/agent-mcp.json` from `claude mcp get <name>` with the same command, args and env. A paper-only P2A agent has no server; skip `--mcp-json`. |
| Compute target | The name of an installed cluster agent, `remotemanager` or `local`. Ask if it isn't given. |
| Request | What to check and how thoroughly, in the user's words. |

## Steps

1. **Manifest.** Run `p2a_introspect.py --paper-skill SKILL_DIR --mcp-json CONFIG --out WORK/agent-manifest.json`.
2. **Registry lookup.** Find `PLUGIN/registry/<doi-key>/`, where the DOI comes from the manifest.
   - If there is no entry, stop and tell the user: the prototype only runs papers with a reviewed registry entry. With `--generate`, the `paper2profile` skill can still draft one, but the run never uses a draft.
3. **Check the registry entry against this agent:**
   - `validate.py profile ENTRY/profile.json --registry-entry ENTRY`
   - `validate.py bigdft-mapping ENTRY/bigdft-mapping.json --profile ENTRY/profile.json --registry-entry ENTRY`
   - `quote_check.py --profile ENTRY/profile.json --paper-skill SKILL_DIR`

   A quote failure means this paper skill is not the text the profile was reviewed against. Report it and stop.
4. **Binding candidates (judgment job 1).**
   - `probe_bindings.py --profile ENTRY/profile.json --list-needs` prints every need.
   - To see what a tool returns, use `probe_bindings.py --manifest WORK/agent-manifest.json --sample TOOL --args '{...}'`. This is one read-only call, logged by the script; use it for listing tools (system labels, isomer names) and for one sample call per tool you intend to use. Don't write your own MCP client.
   - Write `WORK/binding-candidates.json` (schema `PLUGIN/schemas/binding-candidates.schema.json`). For each need, list candidate tools from the manifest with their arguments and an `extract` path into the tool's result.
   - **Structures:** a tool that returns coordinates (`atoms_list` with `units_path`, `xyz_text`, or `artifact_xyz`).
   - **References:** a tool that returns the stored quantity (`scalar`).
   - Propose only what the manifest's tool descriptions and schemas support. Use the system label and rank or name the paper skill or tool docs give for the structure's `label`.
   - Leave a need with no candidates if no tool fits; the script falls back to the profile's authority.
   - Never write values, only where to read them.
5. **Probe.** Run `probe_bindings.py --profile ENTRY/profile.json --manifest WORK/agent-manifest.json --candidates WORK/binding-candidates.json --registry-entry ENTRY --out WORK/bindings.json`.
   - Report every finding, and say which structures came from the profile's authority because the agent has no tool that returns coordinates. That is a capability gap of the agent, not an error.
   - A `data_paper_mismatch` is a result, not something to work around. Don't re-propose a different tool just to make a probe pass.
   - You may correct an obvious argument or path mistake once (e.g. a wrong key name), and say so.
6. **Parameters (judgment job 2).** Write `WORK/params.json` (schema `params.schema.json`):
   - **`claims`:** `"default"`, `"all"`, or claim ids from the profile. Map the user's words to claim ids by the claim's template and parameters.
   - **`preset`:** "quick look / quick check" → `quick`; nothing said, or "normal / usual / standard" → `standard`; "properly / converged / thorough / publication quality" → `tight`.
   - **`species`:** structure ids or formulas when the user narrows the scope, else `null`.
   - **`overrides`:** only when the user explicitly gives a value (e.g. "hgrid 0.25, no scan"), with their reason. Tell the user overrides make the results *not comparable with the reference profile*.
7. **Plan.** Run `plan_runs.py --profile ... --mapping ... --bindings WORK/bindings.json --params WORK/params.json --registry-entry ENTRY --out WORK/run-plan.json`. Show the claims, the run count, the initial batch size, and the `unplannable` claims with their reasons.
8. **Target (judgment job 3).** Load the target's own reference and job-submission skills (e.g. `imlab:imlab-reference`, `imlab:imlab-submitting-jobs`). Write `WORK/target.json` (schema `target.schema.json`):
   - BigDFT module, version and executable, the launch command with a `{run_id}` placeholder, and resources;
   - one run per job; MPI ranks ≤ occupied orbitals; memory set explicitly;
   - `remote_workdir`, plus `sources` saying where each fact came from.

   If the docs don't confirm BigDFT, ask before any read-only check (`module avail bigdft`). Validate with `validate.py target WORK/target.json`. **Nothing in `target.json` may change a BigDFT input.** If the plan can't run as written on this target, report a target failure.
9. **Rounds.** Repeat until `round.json` says `done`:
   1. `export_runs.py --plan WORK/run-plan.json [--round WORK/round.json] --out WORK/runs`; the first round has no `--round`.
   2. Show the batch (run ids, job count, resources, walltime) and **get the user's approval**.
   3. Upload each `WORK/runs/<run_id>/` to `remote_workdir/<run_id>/` and submit one job per run with the target's tools: `pre_launch`, then `command_template` with `{run_id}` filled in, working directory = the run directory.
   4. Monitor. Download `log-<run_id>.yaml` and `exit_status` into `WORK/runs/<run_id>/`.
   5. `parse_logs.py --plan WORK/run-plan.json --runs-dir WORK/runs --out WORK/parsed-results.json`
   6. `evaluate_claims.py --plan WORK/run-plan.json --parsed WORK/parsed-results.json --out WORK/claim-values.json`
   7. `next_round.py --plan WORK/run-plan.json --values WORK/claim-values.json --out WORK/round.json`

   The script decides the next batch. A failed run is reported; don't resubmit with changed inputs.
10. **Verdicts.** Run `compute_verdicts.py --plan --values --round --profile --mapping --params --target --manifest --bindings --out WORK/results.json --report WORK/report.md`. Give the user the verdict table and labels from `report.md` as written, plus the path to `results.json`.

## Review status of the registry entry

The prototype runs with a **reviewed** profile and a **draft** mapping and templates (see the entry's `REVIEW.md`). That is allowed; `compute_verdicts.py` labels the results *unreviewed mapping*. Tell the user once, before step 9.

## `--generate`

If the user asks to also test profile generation, run the `paper2profile` skill on the same paper skill and manifest after step 1. It writes `WORK/generate/draft-profile.json` and `WORK/generate/profile-diff.md`. Steps 2–10 still use the registry profile.

## What you never do

- Edit `run-plan.json`, `bindings.json`, the registry entry, or any generated BigDFT input.
- Choose a grid, pseudopotential, spin, charge or tolerance.
- Pick a converged value, judge a verdict, or write a value into a profile, a binding or a report.
- Submit a batch without the user's approval.
