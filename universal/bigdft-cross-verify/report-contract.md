# Output contract

Everything goes under `<workdir>/`:

```text
profile.json          copy of the profile used (sha256 recorded in results.json)
target.json           compute target and how BigDFT is provided there (sources cited)
settings-map.json     one row per source setting and unknown setting (below)
run-plan.json         batches, runs, claims served per run, job specs, approval status per batch
structures/           input geometries as used, with sha256
runs/<run-id>/        input yaml, posinp, log, job spec, exit status
results.json          machine-readable verdicts (below)
report.md             human summary (below)
```

## settings-map.json

```json
[{"setting": "xc_functional", "source_value": "PBE", "bigdft_value": "ixc: PBE",
  "status": "matched | approximated | not_mappable | unknown",
  "affects": ["claim ids"], "note": "why / expected effect"}]
```

## run-plan.json

```json
{"batches": [{"id": "availability | scan | production", "approved": false, "provisional": true,
  "commands": ["read-only checks, availability batch only"],
  "runs": [{"id": "...", "system": "...", "geometry": "source | bigdft_relaxed", "charge": -1, "nspin": 1,
            "grid": {"hgrid": 0.35, "rmult": [6, 8]}, "claims": ["claim ids"], "jobspec": "runs/<id>/jobspec.json"}]}]}
```

A batch is submitted only after `approved` has been set from an explicit user confirmation. Before submission, the workdir contains `profile.json`, `target.json`, `settings-map.json`, `structures/`, `run-plan.json` and `runs/`. `results.json` and `report.md` come after the runs.

## results.json

```json
{
  "profile_id": "...", "profile_sha256": "...", "tier": "same_code",
  "compute_target": {"name": "imlab", "bigdft": "module bigdft (from imlab-reference)"},
  "tolerances": {"orbital_gap": 0.02},
  "claims": [
    {"id": "...", "system": "...", "reference": 1.882, "computed": 1.879, "unit": "eV",
     "difference": -0.003, "tolerance": 0.02, "geometry": "source | bigdft_relaxed",
     "verdict": "reproduced | reproduced_trend | not_reproduced | inconclusive",
     "reason": "required for inconclusive or reproduced_trend",
     "runs": ["run ids"], "affected_by": ["unknown/approximated settings"]}
  ],
  "diagnostics": [{"quantity": "absolute KS energy", "geometry": "source", "reference": -26.6727, "computed": -26.6719, "note": "grid unknown"}],
  "convergence": {"hgrid": 0.35, "rmult": [6, 8], "evidence": "run ids and per-quantity changes"}
}
```

## report.md

The report has these parts, in this order:

1. **Header:** the paper, the tier, the compute target, and the date.
2. **Verdict table:** one row per claim, giving claim, system, reference, computed value, tolerance and verdict.
3. **Settings map summary:** only the rows that are not `matched`, with the claims each one affects.
4. **Diagnostics:** values reported without a verdict.
5. **Scope:** what was not tested (excluded claims, and global-minimum scope).
