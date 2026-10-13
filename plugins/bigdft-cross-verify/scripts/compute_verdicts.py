# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.21", "pyyaml>=6"]
# ///
"""Verdicts with full provenance -> results.json and report.md. Arithmetic only; no judgment.

  compute_verdicts.py --plan run-plan.json --values claim-values.json --round round.json
                      --profile P --mapping M --params X --target T --manifest MF --bindings B
                      [--bigdft-skills-version V] --out results.json --report report.md

Verdicts: reproduced | reproduced_trend | not_reproduced | inconclusive (with a reason).
  numeric     |computed - reference| <= tolerance (tier + class, mapping overrides)
  categorical exact equality
  ordering    order preserved and every difference within tolerance -> reproduced;
              order preserved only -> reproduced_trend
  figure-confidence references are capped at reproduced_trend; diagnostic templates get no verdict.
"""
import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
HA_EV = 27.211386245988


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def to_units(v, unit, target):
    if unit == "Ha" and target == "eV":
        return [x * HA_EV for x in v] if isinstance(v, list) else v * HA_EV
    return v


def order(v): return sorted(range(len(v)), key=lambda i: v[i])


def verdict(kind, computed, ref, tol):
    if kind == "degeneracy":
        return ("reproduced" if computed == ref else "not_reproduced"), None
    if kind == "energy_ordering":
        diff = [c - r for c, r in zip(computed, ref)]
        if order(computed) != order(ref):
            return "not_reproduced", diff
        return ("reproduced" if max(abs(d) for d in diff) <= tol else "reproduced_trend"), diff
    diff = computed - ref
    return ("reproduced" if abs(diff) <= tol else "not_reproduced"), diff


def fmt(v):
    if isinstance(v, list):
        return "[" + ", ".join(fmt(x) for x in v) + "]" if v and isinstance(v[0], float) else str(v)
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("plan", "values", "round", "profile", "mapping", "params", "target", "manifest", "bindings", "out", "report"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--bigdft-skills-version", default="unknown")
    a = ap.parse_args()
    plan, vals, rnd, prof, mp, target = (json.loads(Path(getattr(a, k)).read_text())
                                         for k in ("plan", "values", "round", "profile", "mapping", "target"))
    jsonschema.validate(target, json.loads((ROOT / "schemas" / "target.schema.json").read_text()))
    if not rnd["done"]:
        sys.exit("the round is not done: run next_round.py and finish the next batch first")
    if not (vals["run_plan_sha256"] == rnd["run_plan_sha256"] == sha(a.plan)):
        sys.exit("plan, claim values and round do not belong together")
    if plan["inputs"]["profile"]["sha256"] != sha(a.profile) or plan["inputs"]["mapping"]["sha256"] != sha(a.mapping):
        sys.exit("profile or mapping differ from the ones the plan was made from")
    tier = prof["tier"]
    tols = yaml.safe_load((ROOT / "templates" / "tolerances.yaml").read_text())
    over = {o["class"]: o["value"] for o in mp["tolerance_overrides"]}
    refs = {c["id"]: c for c in prof["claims"]}

    claims, diags = [], []
    for c in plan["claims"]:
        ref = refs[c["id"]]["reference"]
        refv = to_units(ref["value"], ref["unit"], c["units"])
        dec = rnd["claims"][c["id"]]
        steps = vals["claims"][c["id"]]["steps"]
        last = next((s for s in reversed(steps) if s["status"] == "complete"), None)
        row = {"id": c["id"], "template": c["template"], "reference": refv, "unit": c["units"],
               "reference_confidence": ref["confidence"], "convergence": dec}
        if c["diagnostic"]:
            diags.append({**row, "computed": last["value"] if last else None,
                          "note": "diagnostic only: depends on settings that are unknown or approximated"})
            continue
        tol = over.get(c["tolerance_class"], tols[c["tolerance_class"]][tier])
        if dec["status"] != "converged":
            claims.append({**row, "computed": last["value"] if last else None, "tolerance": tol,
                           "verdict": "inconclusive", "reason": dec.get("reason", "unconverged")})
            continue
        s = steps[dec["step"]]
        v, diff = verdict(c["kind"], s["value"], refv, tol)
        if ref["confidence"] == "figure" and v == "reproduced":
            v = "reproduced_trend"
        extra = {k: s[k] for k in s if k not in ("status", "runs", "value", "hgrids")}
        cross = []
        for x in refs[c["id"]].get("cross_checks", []):
            xv = to_units(x["value"], x["unit"], c["units"])
            if isinstance(xv, float) and "printed_decimals" in x:
                cross.append({"location": x["location"], "value": xv,
                              "computed_rounded": round(s["value"], x["printed_decimals"]),
                              "agrees": round(s["value"], x["printed_decimals"]) == xv})
        claims.append({**row, "computed": s["value"], "difference": diff, "tolerance": tol, "verdict": v,
                       "hgrids": s["hgrids"], "runs": s["runs"], **({"details": extra} if extra else {}),
                       **({"cross_checks": cross} if cross else {})})
    for u in plan["unplannable"]:
        claims.append({"id": u["claim"], "verdict": "inconclusive", "reason": u["reason"]})

    labels = []
    tstat = {t: v["status"] for t, v in plan["inputs"]["templates"].items()}
    if mp["status"] == "draft" or "draft" in tstat.values():
        labels.append("unreviewed mapping")
    if not plan["comparable_with_reference"]:
        labels.append("not comparable with the reference profile (overrides)")
    if plan["inputs"]["params"]["preset"] == "quick":
        labels.append("single-step preset: grid convergence not checked")
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    prov = {"profile": plan["inputs"]["profile"], "mapping": plan["inputs"]["mapping"],
            "template_library_version": plan["inputs"]["template_library_version"], "templates": plan["inputs"]["templates"],
            "profile_schema": prof["schema"], "bigdft_cross_verify_version": plugin["version"],
            "bigdft_skills_version": a.bigdft_skills_version,
            "files_sha256": {k: sha(getattr(a, k)) for k in ("manifest", "bindings", "params", "plan", "target")},
            "overrides": plan["inputs"]["params"]["overrides"],
            "target": {"name": target["name"], "bigdft": target["bigdft"]},
            "psp": plan["inputs"]["psp"], "structures": plan["inputs"]["structures"], "tier": tier}
    doc = {"schema": "bridge/results/1", "provenance": prov, "claims": claims, "diagnostics": diags, "labels": labels}
    jsonschema.validate(doc, json.loads((ROOT / "schemas" / "results.schema.json").read_text()))
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")

    L = [f"# BigDFT cross-verification: {prof['paper']['title']}", "",
         f"- **Paper:** doi:{prof['paper']['doi']}",
         f"- **Profile:** {prof['id']} v{prof['version']} ({prof['status']}); **mapping** v{mp['version']} ({mp['status']}); **tier** {tier}",
         f"- **Compute target:** {target['name']}, {target['bigdft']['module']} (BigDFT {target['bigdft']['version']})",
         f"- **Run plan sha256:** `{prov['files_sha256']['plan']}`. Results are comparable only with runs of the same plan hash.",
         f"- **Date:** {date.today().isoformat()}"]
    if labels:
        L += [f"- **Labels:** {'; '.join(labels)}"]
    L += ["", "## Verdicts", "", "| Claim | Reference | Computed | Tolerance | Grid (hgrids) | Verdict |", "|---|---|---|---|---|---|"]
    for r in claims:
        if "template" not in r:
            L.append(f"| {r['id']} | | | | | inconclusive ({r['reason']}) |")
            continue
        verdict_txt = r["verdict"] + (f" ({r['reason']})" if "reason" in r else "")
        conv = r["convergence"]
        grid = f"{r.get('hgrids', '')} ({conv['status']}{', ' + conv.get('mode', '') if conv.get('mode') else ''})"
        L.append(f"| {r['id']} | {fmt(r['reference'])} {r['unit']} | {fmt(r['computed'])} | {fmt(r['tolerance'])} | {grid} | **{verdict_txt}** |")
    if diags:
        L += ["", "## Diagnostics (no verdict)", ""] + [f"- {d['id']}: reference {fmt(d['reference'])} {d['unit']}, computed {fmt(d['computed'])}. {d['note']}." for d in diags]
    L += ["", "## Provenance", "", "```json", json.dumps(prov, indent=1, sort_keys=True), "```", ""]
    Path(a.report).write_text("\n".join(L))
    print(json.dumps({r["id"]: r["verdict"] for r in claims}, indent=1))


if __name__ == "__main__":
    main()
