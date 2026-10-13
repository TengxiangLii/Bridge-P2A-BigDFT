# /// script
# requires-python = ">=3.10"
# ///
"""Canonical diff of a reference profile (A, the registry) and a generated draft (B) -> profile-diff.md (design C4 S6').

  diff_profiles.py --a registry/profile.json --b draft-profile.json --out profile-diff.md

Claims are matched by (template, parameters with structures resolved to sha256). Three classes:
  scientific  setting state differs; a matched claim's reference value/unit differs; a claim of A missing
              from B (the generator missed it). Exit 1 when there is any.
  scope       claims and structures only in B, and the size of excluded / needs_template (grouping varies).
  wording     setting value text, claim ids. Never counted.
Matched references compare at the coarser of the two: a printed table value (printed_decimals) agrees
with a dataset value that rounds to it, and is listed as scope (precision choice), not as science.
"""
import argparse
import json
from pathlib import Path


def norm_value(v):
    return [round(x, 9) for x in v] if isinstance(v, list) and v and isinstance(v[0], float) else \
        round(v, 9) if isinstance(v, float) else v


def claim_key(c, structs):
    def res(v):
        if isinstance(v, list):
            return tuple(res(x) for x in v)
        return structs.get(v, {}).get("sha256", v) if isinstance(v, str) else v
    return (c["template"], tuple(sorted((k, res(v)) for k, v in c["parameters"].items())))


def same_reference(ra, rb):
    if ra["unit"] != rb["unit"]:
        return False
    va, vb = norm_value(ra["value"]), norm_value(rb["value"])
    if va == vb:
        return True
    for x, y in ((ra, rb), (rb, ra)):  # a printed value agrees with a full-precision one that rounds to it
        if "printed_decimals" in x and isinstance(y["value"], (int, float)):
            return round(y["value"], x["printed_decimals"]) == x["value"]
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", required=True)
    x = ap.parse_args()
    A, B = json.loads(Path(x.a).read_text()), json.loads(Path(x.b).read_text())
    diffs, scope, wording = [], [], []
    for k in sorted(set(A["settings"]) | set(B["settings"])):
        sa, sb = A["settings"].get(k, {}), B["settings"].get(k, {})
        if sa.get("state") != sb.get("state"):
            diffs.append(f"setting `{k}`: state {sa.get('state')} vs {sb.get('state')}")
        elif sa.get("value") != sb.get("value"):
            wording.append(f"setting `{k}`: value wording differs: {sa.get('value')!r} vs {sb.get('value')!r}")
    ident = lambda s: (s["formula"], s["charge"], s["multiplicity"], s["sha256"])
    sa, sb = {ident(s) for s in A["structures"].values()}, {ident(s) for s in B["structures"].values()}
    scope += [f"structure only in B: {s}" for s in sorted(sb - sa)]
    ca = {claim_key(c, A["structures"]): c for c in A["claims"]}
    cb = {claim_key(c, B["structures"]): c for c in B["claims"]}
    for k in sorted(set(ca) | set(cb), key=str):
        if k not in cb:
            diffs.append(f"missed by B: {ca[k]['id']} ({k[0]})")
        elif k not in ca:
            scope.append(f"claim only in B: {cb[k]['id']} ({k[0]})")
        else:
            ra, rb = ca[k]["reference"], cb[k]["reference"]
            if not same_reference(ra, rb):
                diffs.append(f"claim {ca[k]['id']}: reference {ra['value']} {ra['unit']} vs {rb['value']} {rb['unit']}")
            elif norm_value(ra["value"]) != norm_value(rb["value"]):
                scope.append(f"claim {ca[k]['id']}: same value at different precision ({ra['value']} vs {rb['value']})")
            if ca[k]["id"] != cb[k]["id"]:
                wording.append(f"claim id {ca[k]['id']} vs {cb[k]['id']}")
    for f in ("excluded", "needs_template"):
        if len(A[f]) != len(B[f]):
            scope.append(f"{f}: {len(A[f])} vs {len(B[f])} entries (grouping and scope vary)")
    if A["tier"] != B["tier"]:
        diffs.append(f"tier: {A['tier']} vs {B['tier']}")
    L = [f"# Profile diff", "", f"- A: `{x.a}` ({A['id']} v{A['version']})", f"- B: `{x.b}` ({B['id']} v{B['version']})",
         f"- Scientific differences: **{len(diffs)}**; scope: {len(scope)}; wording: {len(wording)}",
         f"- Matched claims: {len(set(ca) & set(cb))} of {len(ca)} in A", ""]
    L += ["## Scientific differences", ""] + ([f"- {d}" for d in diffs] or ["None."])
    L += ["", "## Scope (informational)", ""] + ([f"- {d}" for d in scope] or ["None."])
    L += ["", "## Wording only (not counted)", ""] + ([f"- {w}" for w in wording] or ["None."])
    Path(x.out).write_text("\n".join(L) + "\n")
    print(json.dumps({"scientific": len(diffs), "scope": len(scope), "wording": len(wording),
                      "matched": len(set(ca) & set(cb)), "in_A": len(ca)}))
    raise SystemExit(1 if diffs else 0)


if __name__ == "__main__":
    main()
