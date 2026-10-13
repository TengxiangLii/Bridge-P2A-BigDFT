# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.21", "pyyaml>=6"]
# ///
"""Validate any bridge file against its schema; profiles, mappings and templates also get cross-reference checks.

  validate.py KIND FILE [--profile FILE] [--registry-entry DIR]
  validate.py templates            (checks every file in templates/)

KIND: profile | bigdft-mapping | agent-manifest | binding-candidates | bindings | params | run-plan |
      target | parsed-results | claim-values | round | results
Exit 0 when valid; one error per line otherwise.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent


def schema_errors(obj, kind):
    schema = json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text())
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in v.iter_errors(obj)]


def load_templates():
    return {t["id"]: t for t in (yaml.safe_load(p.read_text()) for p in sorted((ROOT / "templates").glob("*.yaml")))
            if "id" in t}


def template_errors():
    err = []
    for p in sorted((ROOT / "templates").glob("*.yaml")):
        t = yaml.safe_load(p.read_text())
        if "id" not in t:
            continue  # _common.yaml, tolerances.yaml
        err += [f"{p.name}: {e}" for e in schema_errors(t, "template")]
        r = t["engine_recipes"]["bigdft"]
        if t["kind"] == "energy_linear" and set(r.get("combine", {})) != set(r["runs"]):
            err.append(f"{p.name}: combine roles must equal run roles")
        if t["kind"] == "degeneracy" and r.get("stop_rule") != "unchanged_pattern":
            err.append(f"{p.name}: degeneracy needs stop_rule unchanged_pattern")
        if t["kind"] != "degeneracy" and "stop_abs" not in r:
            err.append(f"{p.name}: numeric templates need stop_abs")
    return err


def profile_errors(p, registry_entry):
    err = schema_errors(p, "profile")
    if err:
        return err
    T = load_templates()
    ids = [c["id"] for c in p["claims"]]
    if len(ids) != len(set(ids)):
        err.append("claims: duplicate ids")
    for c in p["claims"]:
        tid, ver = c["template"].split("@")
        t = T.get(tid)
        if not t or t["version"] != int(ver):
            err.append(f"claim {c['id']}: unknown template {c['template']}")
            continue
        for name, spec in t["parameters"].items():
            val = c["parameters"].get(name)
            if spec.get("required") and val is None:
                err.append(f"claim {c['id']}: missing parameter {name}")
            refs = [val] if spec["type"] == "structure_ref" else (val or []) if spec["type"] == "structure_ref_list" else []
            err += [f"claim {c['id']}: unknown structure {r}" for r in refs if r not in p["structures"]]
            if spec["type"] == "structure_ref_list" and len(refs) < spec.get("min_items", 1):
                err.append(f"claim {c['id']}: {name} needs at least {spec.get('min_items')} items")
        extra = set(c["parameters"]) - set(t["parameters"])
        if extra:
            err.append(f"claim {c['id']}: unknown parameters {sorted(extra)}")
        if c["reference"]["unit"] not in (t["units"], "Ha" if t["units"] == "eV" else t["units"]):
            err.append(f"claim {c['id']}: reference unit {c['reference']['unit']} incompatible with {t['units']}")
    err += [f"default_claims: unknown claim {d}" for d in p["default_claims"] if d not in ids]
    for nid, n in p.get("reference_needs", {}).items():
        if n["claim"] not in ids or n["structure"] not in p["structures"]:
            err.append(f"reference_needs {nid}: unknown claim or structure")
    if registry_entry:
        for nid, s in p["structures"].items():
            f = Path(registry_entry) / "structures" / f"{s['sha256']}.xyz"
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != s["sha256"]:
                err.append(f"structure {nid}: registry file missing or hash mismatch")
    return err


def mapping_errors(m, profile, registry_entry):
    err = schema_errors(m, "bigdft-mapping")
    if err:
        return err
    if profile and (m["profile_id"], m["profile_version"]) != (profile["id"], profile["version"]):
        err.append("mapping: profile_id/profile_version do not match the profile")
    if registry_entry:
        for el, e in m["elements"].items():
            if e["status"] == "not_mappable":
                continue
            f = Path(registry_entry) / e["psp_file"]
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != e["psp_sha256"]:
                err.append(f"element {el}: psp file missing or hash mismatch")
    return err


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--profile")
    ap.add_argument("--registry-entry")
    a = ap.parse_args()
    if a.kind == "templates":
        err = template_errors()
    else:
        obj = json.loads(Path(a.file).read_text())
        if a.kind == "profile":
            err = profile_errors(obj, a.registry_entry)
        elif a.kind == "bigdft-mapping":
            prof = json.loads(Path(a.profile).read_text()) if a.profile else None
            err = mapping_errors(obj, prof, a.registry_entry)
        else:
            err = schema_errors(obj, a.kind)
    print("\n".join(err) if err else f"{a.kind}: valid")
    sys.exit(1 if err else 0)


if __name__ == "__main__":
    main()
