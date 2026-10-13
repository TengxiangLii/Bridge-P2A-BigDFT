# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "jsonschema>=4.21"]
# ///
"""Parse BigDFT YAML logs for the runs of a plan -> parsed-results.json.

  parse_logs.py --plan run-plan.json --runs-dir DIR --out parsed-results.json

Looks for DIR/<run_id>/log-<run_id>.yaml (and an optional exit_status file). Reads only keys of a
finished BigDFT log: 'Energy (Hartree)', 'BigDFT infocode', 'Complete list of energy eigenvalues'
(e_occ entries and 'HOMO LUMO gap (AU, eV)'), falling back to the last 'Orbitals' list.
Plain PyYAML, so it also runs on cluster login nodes without numpy.
"""
import argparse
import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def find_all(x, key):
    if isinstance(x, dict):
        for k, v in x.items():
            if k == key:
                yield v
            yield from find_all(v, key)
    elif isinstance(x, list):
        for v in x:
            yield from find_all(v, key)


def parse_one(rdir: Path, rid: str, nspin: int) -> dict:
    log = rdir / f"log-{rid}.yaml"
    if not log.exists():
        return {"status": "missing", "log_sha256": None, "energy_Ha": None, "detail": "no log"}
    out = {"log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "nspin": nspin,
           "energy_Ha": None, "infocode": None, "occupied_Ha": None, "homo_Ha": None, "lumo_Ha": None, "gap_Ha": None}
    st = rdir / "exit_status"
    try:
        d = yaml.load(log.read_text(), Loader=Loader)
    except yaml.YAMLError as e:
        return {**out, "status": "failed", "detail": f"log is not valid YAML: {str(e)[:200]}"}
    if not isinstance(d, dict) or "Energy (Hartree)" not in d:
        return {**out, "status": "failed", "detail": "log has no final energy (run did not finish)"}
    if st.exists() and st.read_text().strip() != "0":
        return {**out, "status": "failed", "detail": f"exit status {st.read_text().strip()}"}
    out["energy_Ha"] = float(d["Energy (Hartree)"])
    out["infocode"] = int(d.get("BigDFT infocode", -1))
    if nspin == 1:
        full = d.get("Complete list of energy eigenvalues")
        occ = [e["e_occ"] for e in full if isinstance(e, dict) and "e_occ" in e] if isinstance(full, list) else []
        if not occ:
            orbs = list(find_all(d.get("Ground State Optimization"), "Orbitals"))
            occ = [o["e"] for o in orbs[-1] if o.get("f", 0) > 0] if orbs else []
        out["occupied_Ha"] = sorted(float(e) for e in occ) or None
        out["homo_Ha"] = out["occupied_Ha"][-1] if out["occupied_Ha"] else None
        gap = list(find_all(d, "HOMO LUMO gap (AU, eV)"))
        if gap:
            out["gap_Ha"] = float(gap[-1][0])
            out["lumo_Ha"] = out["homo_Ha"] + out["gap_Ha"] if out["homo_Ha"] is not None else None
    out["status"] = "ok" if out["infocode"] == 0 else "scf_not_converged"
    out["detail"] = "" if out["status"] == "ok" else f"BigDFT infocode {out['infocode']}"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--runs-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    runs = {rid: parse_one(Path(a.runs_dir) / rid, rid, r["nspin"]) for rid, r in sorted(plan["runs"].items())}
    doc = {"schema": "bridge/parsed-results/1",
           "run_plan_sha256": hashlib.sha256(Path(a.plan).read_bytes()).hexdigest(), "runs": runs}
    jsonschema.validate(doc, json.loads((ROOT / "schemas" / "parsed-results.schema.json").read_text()))
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    counts = {}
    for r in runs.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
