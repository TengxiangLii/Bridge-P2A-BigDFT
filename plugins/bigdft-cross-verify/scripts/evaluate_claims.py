# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.21"]
# ///
"""Claim values per ladder step from parsed runs -> claim-values.json (the one place quantities are computed).

  evaluate_claims.py --plan run-plan.json --parsed parsed-results.json --out claim-values.json

Per claim and step: status complete | pending | failed, and the value in the template's units:
  energy_linear  sum(coefficient x E[role]), Ha -> eV when the template unit is eV
  orbital_gap    LUMO - HOMO (eV), from the run's 'HOMO LUMO gap'
  degeneracy     sizes of groups of consecutive occupied levels closer than threshold_Ha
  energy_ordering  E(isomer k) - E(isomer 0) in eV, in the claim's isomer order
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
HA_EV = 27.211386245988  # CODATA 2018


def degeneracy(occ, thr):
    groups = [[occ[0]]]
    for a, b in zip(occ, occ[1:]):
        (groups[-1].append(b) if b - a < thr else groups.append([b]))
    return [len(g) for g in groups], max(g[-1] - g[0] for g in groups), \
        min((b[0] - a[-1] for a, b in zip(groups, groups[1:])), default=None)


def value(claim, step, runs):
    """(value, extra) for one complete step."""
    kind, R = claim["kind"], step["runs"]
    if kind == "energy_linear":
        e = sum(c * runs[R[role]]["energy_Ha"] for role, c in claim["combine"].items())
        return (e * HA_EV if claim["units"] == "eV" else e), {}
    if kind == "orbital_gap":
        r = runs[R["N"]]
        if r["gap_Ha"] is None:
            raise ValueError("no HOMO-LUMO gap in the log (virtual orbitals missing?)")
        return r["gap_Ha"] * HA_EV, {"homo_Ha": r["homo_Ha"], "lumo_Ha": r["lumo_Ha"]}
    if kind == "degeneracy":
        occ = runs[R["N"]]["occupied_Ha"]
        if not occ:
            raise ValueError("no occupied eigenvalues in the log")
        pattern, split, spacing = degeneracy(occ, claim["parameters"]["threshold_Ha"])
        return pattern, {"max_split_in_group_Ha": split, "min_spacing_between_groups_Ha": spacing}
    if kind == "energy_ordering":
        e = [runs[R[f"{s}:N"]]["energy_Ha"] for s in claim["isomers"]]
        return [(x - e[0]) * HA_EV for x in e], {}
    raise ValueError(f"unknown kind {kind}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--parsed", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan_bytes = Path(a.plan).read_bytes()
    plan, parsed = json.loads(plan_bytes), json.loads(Path(a.parsed).read_text())
    psha = hashlib.sha256(plan_bytes).hexdigest()
    if parsed.get("run_plan_sha256") not in (None, psha):
        sys.exit("parsed results belong to a different run plan")
    runs = parsed["runs"]
    out = {}
    for c in plan["claims"]:
        steps = []
        for st in c["steps"]:
            rs = {rid: runs.get(rid, {"status": "missing"}) for rid in st["runs"].values()}
            bad = {rid: r["status"] for rid, r in rs.items() if r["status"] in ("failed", "scf_not_converged")}
            entry = {"hgrids": st["hgrids"], "runs": sorted(rs)}
            if bad:
                entry |= {"status": "failed", "reason": "unconverged" if "scf_not_converged" in bad.values() else "run_failed",
                          "detail": bad}
            elif any(r["status"] != "ok" for r in rs.values()):
                entry |= {"status": "pending"}
            else:
                try:
                    v, extra = value(c, st, runs)
                    entry |= {"status": "complete", "value": v, **extra}
                except (ValueError, KeyError, TypeError) as e:
                    entry |= {"status": "failed", "reason": "run_failed", "detail": str(e)[:200]}
            steps.append(entry)
        out[c["id"]] = {"kind": c["kind"], "units": c["units"], "steps": steps}
    doc = {"schema": "bridge/claim-values/1", "run_plan_sha256": psha, "claims": out}
    jsonschema.validate(doc, json.loads((ROOT / "schemas" / "claim-values.schema.json").read_text()))
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: [s["status"] for s in v["steps"]] for k, v in out.items()}))


if __name__ == "__main__":
    assert degeneracy([0, 5e-5, 1, 1 + 9e-5, 1 + 2e-4], 1e-4)[0] == [2, 2, 1]
    main()
