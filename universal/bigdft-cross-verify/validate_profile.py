"""Validate a bigdft-cross-verify reproduction profile (structure only, stdlib).

Usage: python3 validate_profile.py <profile.json>   |   python3 validate_profile.py --selftest
Exit 0 when valid; prints one error per line otherwise.
"""
import json
import sys

SCHEMA = "bigdft-cross-verify/profile/1"
TIERS = {"same_code", "cross_code"}
TYPES = {"numeric", "categorical", "ordering"}
CLASSES = {"relative_energy", "absolute_energy", "orbital_gap", "ionization_affinity", "bond_length", "categorical"}
CLAIM_FIELDS = ["id", "statement", "source", "type", "tolerance_class", "systems", "computation", "reference"]


def validate(p: dict) -> list[str]:
    err = []
    need = lambda obj, keys, where: [err.append(f"{where}: missing '{k}'") for k in keys if k not in obj]
    need(p, ["schema", "id", "paper", "tier", "source_method", "unknown_settings", "structures",
             "electronic_state_rules", "reference_data", "claims", "default_claims"], "profile")
    if p.get("schema") != SCHEMA:
        err.append(f"profile: schema must be '{SCHEMA}'")
    if p.get("tier") not in TIERS:
        err.append(f"profile: tier must be one of {sorted(TIERS)}")
    sm = p.get("source_method", {})
    need(sm, ["code", "settings"], "source_method")
    if p.get("tier") == "same_code" and str(sm.get("code", "")).lower() != "bigdft":
        err.append("profile: tier same_code requires source_method.code BigDFT")
    for i, s in enumerate(sm.get("settings", [])):
        need(s, ["name", "value", "source"], f"source_method.settings[{i}]")
    ids = [c.get("id") for c in p.get("claims", [])]
    if len(ids) != len(set(ids)):
        err.append("claims: duplicate ids")
    for c in p.get("claims", []):
        where = f"claim {c.get('id')!r}"
        need(c, CLAIM_FIELDS, where)
        if c.get("type") not in TYPES:
            err.append(f"{where}: type must be one of {sorted(TYPES)}")
        if c.get("tolerance_class") not in CLASSES:
            err.append(f"{where}: tolerance_class must be one of {sorted(CLASSES)}")
        want = {"categorical": {"categorical"}, "ordering": {"relative_energy"}}.get(c.get("type"))
        if want and c.get("tolerance_class") not in want:
            err.append(f"{where}: {c.get('type')} claims use tolerance_class {sorted(want)[0]}")
        if c.get("type") == "numeric" and c.get("tolerance_class") == "categorical":
            err.append(f"{where}: numeric claims need a numeric tolerance_class")
        if c.get("tolerance_class") == "absolute_energy" and p.get("tier") == "cross_code":
            err.append(f"{where}: absolute_energy is not a claim under cross_code")
        if not c.get("systems"):
            err.append(f"{where}: systems must be a non-empty list")
    for u in p.get("unknown_settings", []):
        need(u, ["name", "affects", "source"], f"unknown_settings {u.get('name')!r}")
        for a in u.get("affects", []):
            if a not in ids:
                err.append(f"unknown_settings {u.get('name')!r}: affects unknown claim {a!r}")
    for d in p.get("default_claims", []):
        if d not in ids:
            err.append(f"default_claims: unknown claim {d!r}")
    for i, x in enumerate(p.get("excluded_claims", [])):
        need(x, ["statement", "reason"], f"excluded_claims[{i}]")
    for o in p.get("tolerance_overrides", []):
        need(o, ["class", "value", "reason"], "tolerance_overrides")
    return err


def _selftest():
    good = {"schema": SCHEMA, "id": "x", "paper": {}, "tier": "cross_code",
            "source_method": {"code": "VASP", "settings": [{"name": "xc", "value": "PBE", "source": "§2"}]},
            "unknown_settings": [], "structures": {}, "electronic_state_rules": {}, "reference_data": {},
            "claims": [{"id": "gap", "statement": "s", "source": "T1", "type": "numeric", "tolerance_class": "orbital_gap",
                        "systems": ["A"], "computation": "c", "reference": 2.1}],
            "default_claims": ["gap"]}
    assert validate(good) == [], validate(good)
    bad = json.loads(json.dumps(good))
    bad["claims"][0]["tolerance_class"] = "absolute_energy"
    bad["default_claims"] = ["nope"]
    bad["tier"] = "same_code"
    e = validate(bad)
    assert any("absolute_energy" not in x and "same_code" in x for x in e), e
    assert any("default_claims" in x for x in e), e
    bad2 = json.loads(json.dumps(good))
    bad2["claims"][0].update(type="ordering", tolerance_class="categorical")
    bad2["excluded_claims"] = [{"statement": "x"}]
    e2 = validate(bad2)
    assert any("ordering claims use" in x for x in e2) and any("excluded_claims[0]" in x for x in e2), e2
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        _selftest()
        sys.exit(0)
    errors = validate(json.load(open(sys.argv[1])))
    print("\n".join(errors) if errors else "profile valid")
    sys.exit(1 if errors else 0)
