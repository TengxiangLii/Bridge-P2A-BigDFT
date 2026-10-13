# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.21"]
# ///
"""Decide the next batch from claim values: the convergence ladder + stop rule, applied by a script.

  next_round.py --plan run-plan.json --values claim-values.json --out round.json

Per claim:
  converged     two consecutive complete steps differ by less than the stop rule (abs, or unchanged
                pattern); the later step is used. A one-step ladder (preset quick) is 'single_step'.
  needs_runs    the next incomplete step's runs go into next_batch (step 0 and 1 together at the start)
  not_converged every step complete, no consecutive pair within the stop rule
  blocked       a run of a needed step failed (reason unconverged | run_failed)
"""
import argparse
import hashlib
import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent


def close(a, b, stop):
    if "rule" in stop:  # unchanged_pattern
        return a == b
    if isinstance(a, list):
        return len(a) == len(b) and max(abs(x - y) for x, y in zip(a, b)) < stop["abs"]
    return abs(a - b) < stop["abs"]


def decide(claim, values):
    steps = values["steps"]
    for i, s in enumerate(steps):
        if s["status"] == "failed":
            return {"status": "blocked", "reason": s["reason"], "step": i}, []
        if s["status"] == "pending":
            want = [i] + ([i + 1] if i == 0 and len(steps) > 1 else [])
            return {"status": "needs_runs", "steps": want}, sorted({r for j in want for r in steps[j]["runs"]})
        if len(steps) == 1:
            return {"status": "converged", "step": 0, "mode": "single_step"}, []
        if i > 0 and close(steps[i - 1]["value"], s["value"], claim["stop"]):
            return {"status": "converged", "step": i, "mode": "stop_rule"}, []
    return {"status": "not_converged", "step": len(steps) - 1}, []


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--values", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan_bytes = Path(a.plan).read_bytes()
    plan, vals = json.loads(plan_bytes), json.loads(Path(a.values).read_text())
    psha = hashlib.sha256(plan_bytes).hexdigest()
    assert vals["run_plan_sha256"] == psha, "claim values belong to a different run plan"
    claims, batch = {}, set()
    for c in plan["claims"]:
        claims[c["id"]], runs = decide(c, vals["claims"][c["id"]])
        batch |= set(runs)
    doc = {"schema": "bridge/round/1", "run_plan_sha256": psha, "next_batch": sorted(batch), "claims": claims,
           "done": not batch}
    jsonschema.validate(doc, json.loads((ROOT / "schemas" / "round.schema.json").read_text()))
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"done": doc["done"], "next_batch": doc["next_batch"],
                      "claims": {k: v["status"] for k, v in claims.items()}}, indent=1))


if __name__ == "__main__":
    main()
