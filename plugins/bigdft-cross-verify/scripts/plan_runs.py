# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.21", "pyyaml==6.0.2"]
# ///
"""Physics plan: profile + mapping + bindings + params -> run-plan.json (target-independent, byte-identical).

  plan_runs.py --profile P --mapping M --bindings B --params X --registry-entry DIR --out run-plan.json

Claims expand through their template's BigDFT recipe; runs shared by several claims are deduplicated.
Each run carries its full input YAML and canonical posinp as text, so the same inputs give the same bytes
on any machine. Nothing about the compute target enters this file. pyyaml is pinned because its output
is part of the plan bytes.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
HA_EV = 27.211386245988  # CODATA 2018


def sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()


def check(obj, kind):
    jsonschema.validate(obj, json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text()))


def templates():
    out = {}
    for p in sorted((ROOT / "templates").glob("*.yaml")):
        t = yaml.safe_load(p.read_text())
        if "id" in t:
            out[f"{t['id']}@{t['version']}"] = (t, sha(p.read_bytes()))
    return out


def structure_atoms(entry: Path, s: dict):
    lines = (entry / "structures" / f"{s['sha256']}.xyz").read_text().splitlines()[3:]
    return [l.split() for l in lines]


def select_claims(prof, params):
    ids = [c["id"] for c in prof["claims"]]
    want = prof["default_claims"] if params["claims"] == "default" else ids if params["claims"] == "all" else params["claims"]
    bad = [w for w in want if w not in ids]
    if bad:
        sys.exit(f"unknown claims in params: {bad}")
    chosen = [c for c in prof["claims"] if c["id"] in want]
    if params["species"]:
        sp = set(params["species"])
        def struct_ids(c):
            return [s for v in c["parameters"].values() for s in (v if isinstance(v, list) else [v]) if s in prof["structures"]]
        chosen = [c for c in chosen if any(s in sp or prof["structures"][s]["formula"] in sp for s in struct_ids(c))]
    return chosen


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for k in ("profile", "mapping", "bindings", "params", "registry-entry", "out"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    raw = {k: Path(getattr(a, k)).read_bytes() for k in ("profile", "mapping", "bindings", "params")}
    prof, mp, bnd, params = (json.loads(raw[k]) for k in ("profile", "mapping", "bindings", "params"))
    for obj, kind in ((prof, "profile"), (mp, "bigdft-mapping"), (bnd, "bindings"), (params, "params")):
        check(obj, kind)
    if (mp["profile_id"], mp["profile_version"]) != (prof["id"], prof["version"]):
        sys.exit("mapping does not belong to this profile")
    if bnd["profile_sha256"] != sha(raw["profile"]):
        sys.exit("bindings were made for a different profile")
    entry = Path(a.registry_entry)
    T = templates()
    common = yaml.safe_load((ROOT / "templates" / "_common.yaml").read_text())
    ov = {o["key"]: o["value"] for o in params["overrides"]}
    ladder = [float(h) for h in ov.get("ladder", common["convergence"]["ladders"][params["preset"]])]
    dft_defaults = {**mp["dft_defaults"], **({"rmult": ov["rmult"]} if "rmult" in ov else {}),
                    **({"gnrm_cv": ov["gnrm_cv"]} if "gnrm_cv" in ov else {})}

    runs, claims_out, unplannable, used_templates, psp_used = {}, [], [], {}, {}
    for c in select_claims(prof, params):
        t, tsha = T[c["template"]]
        used_templates[c["template"]] = {"status": t["status"], "sha256": tsha}
        recipe = t["engine_recipes"]["bigdft"]
        sids = c["parameters"].get("isomers") or [c["parameters"]["species"]]

        def block(reason):
            unplannable.append({"claim": c["id"], "reason": reason})

        st = [bnd["bindings"].get(f"structure:{s}", {}).get("status") for s in sids]
        refs = [b for n, b in bnd["bindings"].items() if prof.get("reference_needs", {}).get(n, {}).get("claim") == c["id"]]
        if "mismatch" in st or any(b["status"] == "mismatch" for b in refs):
            block("data_paper_mismatch"); continue
        if any(x != "bound" for x in st):
            block("missing_structure"); continue
        elems = sorted({at[0] for s in sids for at in structure_atoms(entry, prof["structures"][s])})
        unmapped = [e for e in elems if mp["elements"].get(e, {"status": "not_mappable"})["status"] == "not_mappable"]
        if unmapped:
            block(f"element_not_mapped:{','.join(unmapped)}"); continue
        ixc = {mp["elements"][e]["ixc"] for e in elems}
        if len(ixc) != 1:
            block("mixed_xc_in_one_structure"); continue
        ixc = ixc.pop()
        steps, blocked = [], None
        for h in ladder:
            step = {"hgrids": h, "runs": {}}
            for s in sids:
                S = prof["structures"][s]
                atoms = structure_atoms(entry, S)
                for role, r in recipe["runs"].items():
                    charge = S["charge"] + r["charge_offset"]
                    electrons = sum(mp["elements"][at[0]]["valence_electrons"] for at in atoms) - charge
                    if t.get("requires", {}).get("closed_shell") and electrons % 2:
                        blocked = "definition_ambiguous:open_shell"
                    nspin = 2 if electrons % 2 else 1  # mapping spin_rule: odd -> collinear, minimal moment
                    rid = f"{S['formula']}q{charge:+d}-{S['sha256'][:8]}-h{round(h * 100):03d}"
                    run = runs.setdefault(rid, {"structure": s, "structure_sha256": S["sha256"], "charge": charge,
                                                "electrons": electrons, "nspin": nspin, "hgrids": h, "virtual": False,
                                                "elements": elems, "ixc": ixc})
                    run["virtual"] |= r["virtual"]
                    step["runs"][role if len(sids) == 1 else f"{s}:{role}"] = rid
            steps.append(step)
        if blocked:
            block(blocked); continue
        claims_out.append({"id": c["id"], "template": c["template"], "kind": t["kind"], "units": t["units"],
                           "diagnostic": bool(t.get("diagnostic")), "tolerance_class": t["tolerance_class"],
                           "parameters": c["parameters"], "combine": recipe.get("combine"),
                           "stop": {"abs": recipe["stop_abs"]} if "stop_abs" in recipe else {"rule": recipe["stop_rule"]},
                           "isomers": c["parameters"].get("isomers"), "steps": steps})
        for e in elems:
            psp_used[e] = {"file": mp["elements"][e]["psp_file"], "sha256": mp["elements"][e]["psp_sha256"]}

    psp = {e: yaml.safe_load((entry / v["file"]).read_text()) for e, v in psp_used.items()}
    vo = mp["virtual_orbitals"]
    for rid, r in sorted(runs.items()):
        dft = {"ixc": r["ixc"], "hgrids": r["hgrids"], "rmult": dft_defaults["rmult"], "qcharge": r["charge"],
               "nspin": r["nspin"], "gnrm_cv": dft_defaults["gnrm_cv"], "itermax": dft_defaults["itermax"],
               "nrepmax": dft_defaults["nrepmax"]}
        if r["nspin"] == 2:
            dft["mpol"] = 1
        if r["virtual"]:
            dft |= vo
        inp = {"dft": dft, **{f"psppar.{e}": psp[e] for e in r["elements"]}}
        atoms = structure_atoms(entry, prof["structures"][r["structure"]])
        r["files"] = {f"{rid}.yaml": yaml.safe_dump(inp, sort_keys=True, default_flow_style=False),
                      f"{rid}.xyz": f"{len(atoms)} angstroemd0\nfree\n" + "".join(" ".join(at) + "\n" for at in atoms)}
        del r["ixc"], r["elements"]

    first = sorted({rid for c in claims_out for st in c["steps"][:2] for rid in st["runs"].values()})
    plan = {"schema": "bridge/run-plan/1",
            "inputs": {"profile": {"id": prof["id"], "version": prof["version"], "status": prof["status"], "sha256": sha(raw["profile"])},
                       "mapping": {"version": mp["version"], "status": mp["status"], "sha256": sha(raw["mapping"])},
                       "params": params, "templates": used_templates,
                       "template_library_version": common["library_version"],
                       "psp": psp_used, "tier": prof["tier"],
                       "structures": {s: prof["structures"][s]["sha256"] for c in claims_out
                                      for s in (c["isomers"] or [c["parameters"]["species"]])}},
            "claims": claims_out, "runs": runs, "initial_batch": first, "unplannable": unplannable,
            "comparable_with_reference": not params["overrides"]}
    check(plan, "run-plan")
    text = json.dumps(plan, indent=1, sort_keys=True, ensure_ascii=True) + "\n"
    Path(a.out).write_text(text)
    print(json.dumps({"sha256": sha(text.encode()), "claims": [c["id"] for c in claims_out], "runs": len(runs),
                      "initial_batch": len(first), "unplannable": unplannable}, indent=1))


if __name__ == "__main__":
    main()
