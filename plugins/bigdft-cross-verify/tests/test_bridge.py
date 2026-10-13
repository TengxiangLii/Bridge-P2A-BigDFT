"""Unit and regression tests for the bridge scripts (offline; no MCP server, no cluster).

Run: uv run --with pytest --with jsonschema --with pyyaml==6.0.2 --with numpy pytest tests
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registry" / "10.1039_D2MA01088G"
FIX = ROOT / "tests" / "fixtures"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(script, *args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / f"{script}.py"), *map(str, args)],
                          capture_output=True, text=True)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ---------- canonical structures ----------
def test_canonical_selftest():
    load("canonical_structure").selftest()


# ---------- next_round: the stop rule decides, not Claude ----------
NR = load("next_round")
CLAIM = {"stop": {"abs": 0.01}}


def steps(*specs):
    return {"steps": [{"status": s, "value": v, "runs": [f"r{i}"], "reason": "unconverged"} for i, (s, v) in enumerate(specs)]}


def test_start_requests_two_steps():
    d, batch = NR.decide(CLAIM, steps(("pending", None), ("pending", None), ("pending", None)))
    assert d == {"status": "needs_runs", "steps": [0, 1]} and batch == ["r0", "r1"]


def test_converges_on_consecutive_steps():
    d, _ = NR.decide(CLAIM, steps(("complete", 1.0), ("complete", 1.005), ("pending", None)))
    assert d["status"] == "converged" and d["step"] == 1


def test_asks_next_step_when_not_converged():
    d, batch = NR.decide(CLAIM, steps(("complete", 1.0), ("complete", 1.5), ("pending", None)))
    assert d == {"status": "needs_runs", "steps": [2]} and batch == ["r2"]


def test_ladder_exhausted_is_not_converged():
    d, _ = NR.decide(CLAIM, steps(("complete", 1.0), ("complete", 1.5), ("complete", 2.0)))
    assert d["status"] == "not_converged"


def test_failed_run_blocks():
    d, _ = NR.decide(CLAIM, steps(("complete", 1.0), ("failed", None)))
    assert d["status"] == "blocked" and d["reason"] == "unconverged"


def test_single_step_preset():
    d, _ = NR.decide(CLAIM, steps(("complete", 1.0)))
    assert d == {"status": "converged", "step": 0, "mode": "single_step"}


def test_pattern_stop_rule():
    c = {"stop": {"rule": "unchanged_pattern"}}
    assert NR.decide(c, steps(("complete", [1, 3]), ("complete", [1, 3])))[0]["status"] == "converged"
    assert NR.decide(c, steps(("complete", [1, 3]), ("complete", [2, 2]), ("pending", None)))[0]["status"] == "needs_runs"


# ---------- verdict arithmetic ----------
CV = load("compute_verdicts")


def test_numeric_verdicts():
    assert CV.verdict("orbital_gap", 1.8886, 1.8821, 0.02)[0] == "reproduced"
    assert CV.verdict("orbital_gap", 1.95, 1.8821, 0.02)[0] == "not_reproduced"


def test_pattern_verdict():
    assert CV.verdict("degeneracy", [1, 3, 5], [1, 3, 5], None)[0] == "reproduced"
    assert CV.verdict("degeneracy", [1, 3, 4, 1], [1, 3, 5], None)[0] == "not_reproduced"


def test_ordering_verdicts():
    ref = [0.0, 0.97, 1.47]
    assert CV.verdict("energy_ordering", [0.0, 0.972, 1.468], ref, 0.005)[0] == "reproduced"
    assert CV.verdict("energy_ordering", [0.0, 0.90, 1.40], ref, 0.005)[0] == "reproduced_trend"
    assert CV.verdict("energy_ordering", [0.0, 1.50, 1.40], ref, 0.005)[0] == "not_reproduced"


def test_units_conversion():
    assert CV.to_units([0.0, 1.0], "Ha", "eV") == [0.0, CV.HA_EV]


# ---------- evaluate_claims ----------
EC = load("evaluate_claims")


def test_degeneracy_grouping():
    assert EC.degeneracy([0, 5e-5, 1, 1 + 9e-5, 1 + 2e-4], 1e-4)[0] == [2, 2, 1]


def test_energy_linear_vie():
    claim = {"kind": "energy_linear", "units": "eV", "combine": {"N-1": 1.0, "N": -1.0}}
    runs = {"a": {"energy_Ha": -10.0}, "b": {"energy_Ha": -10.1}}
    v, _ = EC.value(claim, {"runs": {"N-1": "a", "N": "b"}}, runs)
    assert abs(v - 0.1 * EC.HA_EV) < 1e-9


# ---------- quote check ----------
def test_quote_normalisation():
    q = load("quote_check")
    assert q.normalise("Al<sub>13</sub><sup>−1</sup> the Perdew–Burke") == q.normalise("Al13-1 the Perdew-Burke")


# ---------- parse_logs on a real BigDFT log (IMLab, 2026-10-05) ----------
def test_parse_real_log(tmp_path):
    p = load("parse_logs")
    d = tmp_path / "run1"
    d.mkdir()
    (d / "log-run1.yaml").write_bytes((FIX / "logs" / "log-Al13m1_min0001_h040_r6-8.yaml").read_bytes())
    r = p.parse_one(d, "run1", 1)
    assert r["status"] == "ok" and r["infocode"] == 0
    assert abs(r["energy_Ha"] - (-63.31112171521119)) < 1e-9
    assert len(r["occupied_Ha"]) == 20 and abs(r["gap_Ha"] * EC.HA_EV - 1.88864) < 1e-4


def test_parse_missing_and_unfinished(tmp_path):
    p = load("parse_logs")
    assert p.parse_one(tmp_path, "nope", 1)["status"] == "missing"
    d = tmp_path / "half"
    d.mkdir()
    (d / "log-half.yaml").write_text("dft: {hgrids: 0.4}\n")
    assert p.parse_one(d, "half", 1)["status"] == "failed"


# ---------- plan determinism (design §12 gate) ----------
def bindings_for(profile_path, structures, statuses=None):
    prof = json.loads(Path(profile_path).read_text())
    return {"schema": "bridge/bindings/1", "profile_sha256": sha(profile_path), "manifest_sha256": "0" * 64,
            "bindings": {f"structure:{s}": {"status": (statuses or {}).get(s, "bound"), "required": True,
                                            "source": {"kind": "authority"}, "method": "hash", "attempts": [],
                                            "observed_sha256": prof["structures"][s]["sha256"],
                                            "canonical_sha256": prof["structures"][s]["sha256"]} for s in structures},
            "findings": []}


def plan(tmp_path, entry, bindings, params, name):
    (tmp_path / f"{name}-b.json").write_text(json.dumps(bindings))
    (tmp_path / f"{name}-p.json").write_text(json.dumps(params))
    r = run("plan_runs", "--profile", entry / "profile.json", "--mapping", entry / "bigdft-mapping.json",
            "--bindings", tmp_path / f"{name}-b.json", "--params", tmp_path / f"{name}-p.json",
            "--registry-entry", entry, "--out", tmp_path / f"{name}.json")
    assert r.returncode == 0, r.stderr
    return tmp_path / f"{name}.json"


PARAMS = {"schema": "bridge/params/1", "claims": "default", "preset": "standard", "species": None, "overrides": []}
ALL = ["al13m1-r0", "al13m1-r1", "al13m1-r2", "al13m1-r3", "al13m1-r4", "al13m1-r5", "si10-r0"]


def test_plan_is_byte_identical(tmp_path):
    b = bindings_for(REG / "profile.json", ALL)
    a1 = plan(tmp_path, REG, b, PARAMS, "a1")
    b["manifest_sha256"] = "1" * 64  # a different agent: bindings differ, plan must not
    for v in b["bindings"].values():
        v["source"] = {"kind": "mcp_tool", "tool": "anything"}
    a2 = plan(tmp_path, REG, b, PARAMS, "a2")
    assert sha(a1) == sha(a2)


def test_case2_plan_hash_independent_of_binding_route(tmp_path):
    e = FIX / "case2" / "registry-entry"
    b = bindings_for(e / "profile.json", ["al13m1-r0"])
    h1 = sha(plan(tmp_path, e, b, PARAMS, "c1"))
    b["bindings"]["structure:al13m1-r0"] |= {"method": "rmsd", "rmsd_A": 0.00086, "observed_sha256": "f" * 64}
    assert sha(plan(tmp_path, e, b, PARAMS, "c2")) == h1


def test_unbound_structure_makes_claim_unplannable(tmp_path):
    b = bindings_for(REG / "profile.json", ALL, {"al13m1-r3": "unbound"})
    p = json.loads(plan(tmp_path, REG, b, PARAMS, "u").read_text())
    assert {"claim": "al13m1-energy-ordering", "reason": "missing_structure"} in p["unplannable"]
    assert "al13m1-homo-lumo-gap" in [c["id"] for c in p["claims"]]


def test_mismatch_blocks_claim(tmp_path):
    b = bindings_for(REG / "profile.json", ALL, {"al13m1-r0": "mismatch"})
    p = json.loads(plan(tmp_path, REG, b, PARAMS, "m").read_text())
    assert {"claim": "al13m1-homo-lumo-gap", "reason": "data_paper_mismatch"} in p["unplannable"]


def test_override_marks_plan_not_comparable(tmp_path):
    b = bindings_for(REG / "profile.json", ALL)
    params = {**PARAMS, "overrides": [{"key": "ladder", "value": [0.25], "reason": "expert: fixed fine grid"}]}
    p = json.loads(plan(tmp_path, REG, b, params, "o").read_text())
    assert p["comparable_with_reference"] is False


@pytest.mark.parametrize("kind,file", [("profile", REG / "profile.json"), ("bigdft-mapping", REG / "bigdft-mapping.json"),
                                       ("target", FIX / "target-imlab.json")])
def test_registry_files_validate(kind, file):
    extra = ["--registry-entry", REG] if kind != "target" else []
    if kind == "bigdft-mapping":
        extra += ["--profile", REG / "profile.json"]
    r = run("validate", kind, file, *extra)
    assert r.returncode == 0, r.stdout + r.stderr


def test_templates_validate():
    assert run("validate", "templates").returncode == 0


# ---------- table row addressing and profile diff classes ----------
def test_table_rowindex(tmp_path):
    q = load("quote_check")
    (tmp_path / "t.csv").write_text("Cluster,Minimum,Gap\nAl13^-1,1 (GM),1.88\n,2,1.21\n")
    assert q.table_cell(tmp_path, "table:t.csv#row=Al13^-1;col=Gap") == "1.88"
    assert q.table_cell(tmp_path, "table:t.csv#rowindex=2;col=Gap") == "1.21"


def test_diff_separates_science_from_scope(tmp_path):
    a = json.loads((REG / "profile.json").read_text())
    b = json.loads(json.dumps(a))
    b["claims"] = [c for c in b["claims"] if c["id"] != "al13m1-vie"]           # a miss: scientific
    extra = {"id": "si10-total-energy", "template": "total_energy@1", "parameters": {"species": "si10-r0"},
             "reference": {"value": -39.05866174887787, "unit": "Ha", "confidence": "dataset", "quote": None,
                           "location": "dataset key KS-Final-energy"}}
    b["claims"].append(extra)                                                   # a claim only in B: scope
    gap = next(c for c in b["claims"] if c["id"] == "al13m1-homo-lumo-gap")
    gap["reference"] = {**gap["reference"], "value": 1.88, "printed_decimals": 2, "confidence": "table"}  # precision only
    (tmp_path / "b.json").write_text(json.dumps(b))
    r = run("diff_profiles", "--a", REG / "profile.json", "--b", tmp_path / "b.json", "--out", tmp_path / "d.md")
    out = json.loads(r.stdout)
    assert r.returncode == 1 and out["scientific"] == 1
    text = (tmp_path / "d.md").read_text()
    assert "missed by B: al13m1-vie" in text and "claim only in B: si10-total-energy" in text
    assert "same value at different precision" in text
