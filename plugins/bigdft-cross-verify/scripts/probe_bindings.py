# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "jsonschema>=4.21"]
# ///
"""Gate binding candidates by probing them; write bindings.json with only accepted bindings.

  probe_bindings.py --profile P --list-needs            (what candidates must cover; no agent needed)
  probe_bindings.py --manifest M --sample TOOL --args JSON   (one read-only call: shows a tool's result shape)
  probe_bindings.py --profile P --manifest M --candidates C --registry-entry DIR --out bindings.json

Structures: canonicalise what a candidate returns at the authority precision (canonical_structure.py)
and accept on sha256 equality, or on RMSD <= 2 x precision (then the registry's canonical structure is
used). A candidate that returns the right formula but the wrong geometry is a data_paper_mismatch: no
fallback, the dependent claims stay inconclusive. Only when no candidate yields a structure does the
script fall back to the profile's authority locator.
Reference values (optional needs): accept when the returned value equals the profile reference
(dataset: |d| <= 1e-9 relative; table: equal at the printed decimals).
"""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
CANON = ["uv", "run", "-q", str(ROOT / "scripts" / "canonical_structure.py")]  # a CLI, never imported


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check(obj, kind):
    jsonschema.validate(obj, json.loads((ROOT / "schemas" / f"{kind}.schema.json").read_text()))


def dig(obj, path):
    for k in path.split(".") if path else []:
        obj = obj[int(k)] if isinstance(obj, list) else obj[k]
    return obj


def canon(cmd: list[str]) -> dict:
    r = subprocess.run(CANON + cmd, capture_output=True, text=True)
    if r.returncode not in (0, 1) or not r.stdout.strip():
        raise RuntimeError(r.stderr.strip()[-400:])
    return json.loads(r.stdout)


class Agent:
    """One stdio session with the agent's MCP server, launched from the manifest."""

    def __init__(self, server, launch, env):
        cfg_env = {}
        if launch.get("config_file"):  # env values stay in the agent's own config; the manifest has names only
            cfg_env = json.loads(Path(launch["config_file"]).read_text())["mcpServers"][server].get("env", {})
        self.params = StdioServerParameters(command=launch["command"], args=launch["args"],
                                            env={**os.environ, **cfg_env, **env})

    async def run(self, calls):
        out = []
        async with stdio_client(self.params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                for tool, args in calls:
                    try:
                        res = await s.call_tool(tool, args)
                        if res.isError:
                            out.append(("error", " ".join(getattr(c, "text", "") for c in res.content)[:300]))
                            continue
                        data = res.structuredContent
                        if data is None:
                            data = json.loads(res.content[0].text)
                        if isinstance(data, dict) and set(data) == {"result"}:
                            data = data["result"]
                        out.append(("ok", data))
                    except Exception as e:  # report, never crash the gate
                        out.append(("error", repr(e)[:300]))
        return out


def structure_file(src, data, tmp: Path, paper_skill: Path):
    """Write what a candidate returned as a file canonical_structure.py can read; return (path, format)."""
    if src["kind"] == "paper_table":
        return paper_skill / src["file"], "paper_table_csv"
    ex = src["extract"]
    val = dig(data, ex["path"])
    if ex["format"] == "artifact_xyz":
        return Path(val), "bigdft_xyz"
    if ex["format"] == "xyz_text":
        p = tmp / "s.xyz"
        p.write_text(val)
        return p, "bigdft_xyz" if len(val.splitlines()[0].split()) > 1 else "xyz"
    if ex["format"] == "atoms_list":
        units = dig(data, ex["units_path"]) if ex.get("units_path") else ex.get("units", "angstroem")
        p = tmp / "s.xyz"
        p.write_text(f"{len(val)} {units}\nfree\n" + "".join(f"{a['element']} {a['x']!r} {a['y']!r} {a['z']!r}\n" for a in val))
        return p, "bigdft_xyz"
    raise ValueError(f"format {ex['format']} is not a structure")


def judge_structure(path, fmt, need, entry: Path, tmp: Path):
    prec = need["authority"]["precision_A"]
    out = tmp / "obs.canon"
    info = canon(["canon", "--in", str(path), "--format", fmt, "--precision", repr(prec), "--out", str(out)])
    want = need["formula"]
    if info["formula"] != want:
        return {"result": "wrong_formula", "observed_sha256": info["sha256"], "formula": info["formula"]}
    if info["sha256"] == need["sha256"]:
        return {"result": "bound", "method": "hash", "observed_sha256": info["sha256"], "rmsd_A": 0.0}
    cmp = canon(["compare", "--a", str(out), "--b", str(entry / "structures" / f"{need['sha256']}.xyz"),
                 "--threshold", repr(2 * prec)])
    return {"result": "bound" if cmp["match"] else "mismatch", "method": "rmsd",
            "observed_sha256": info["sha256"], "rmsd_A": cmp["rmsd_A"]}


def ref_matches(value, ref):
    exp = ref["value"]
    if isinstance(exp, (int, float)) and isinstance(value, (int, float)):
        if ref["confidence"] == "table" and "printed_decimals" in ref:
            return round(value, ref["printed_decimals"]) == exp
        return abs(value - exp) <= 1e-9 * max(1.0, abs(exp))
    return value == exp


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile")
    ap.add_argument("--sample")
    ap.add_argument("--args", default="{}")
    for k in ("manifest", "candidates", "registry-entry", "out"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--list-needs", action="store_true")
    ap.add_argument("--env", action="append", default=[], help="KEY=VALUE for the agent's MCP server")
    a = ap.parse_args()
    env = dict(e.split("=", 1) for e in a.env)
    if a.sample:
        man = json.loads(Path(a.manifest).read_text())
        if a.sample not in {t["name"] for t in man["mcp"]["tools"]}:
            sys.exit(f"{a.sample} is not a tool of this agent")
        [(status, data)] = asyncio.run(Agent(man["mcp"]["server"], man["mcp"]["launch"], env).run([(a.sample, json.loads(a.args))]))
        print(json.dumps({"status": status, "result": data}, indent=1, ensure_ascii=False, default=str))
        return
    prof = json.loads(Path(a.profile).read_text())
    if a.list_needs:
        used = sorted({s for c in prof["claims"] for v in c["parameters"].values()
                       for s in (v if isinstance(v, list) else [v]) if isinstance(s, str) and s in prof["structures"]})
        out = {f"structure:{s}": {"kind": "structure", "formula": prof["structures"][s]["formula"],
                                  "charge": prof["structures"][s]["charge"], "label": prof["structures"][s].get("label", "")}
               for s in used}
        out |= {n: {"kind": "reference", **v} for n, v in sorted(prof.get("reference_needs", {}).items())}
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return
    if not all((a.manifest, a.candidates, a.registry_entry, a.out)):
        sys.exit("--manifest, --candidates, --registry-entry and --out are required")
    man = json.loads(Path(a.manifest).read_text())
    cand = json.loads(Path(a.candidates).read_text())
    check(man, "agent-manifest"); check(cand, "binding-candidates")
    entry, skill = Path(a.registry_entry), Path(man["paper_skill"]["path"])
    claims_by_struct = {}
    for c in prof["claims"]:
        for v in c["parameters"].values():
            for s in (v if isinstance(v, list) else [v]):
                if isinstance(s, str) and s in prof["structures"]:
                    claims_by_struct.setdefault(s, []).append(c["id"])
    needs = {f"structure:{s}": ("structure", prof["structures"][s]) for s in sorted(claims_by_struct)}
    claims = {c["id"]: c for c in prof["claims"]}
    needs |= {nid: ("reference", n) for nid, n in sorted(prof.get("reference_needs", {}).items())}
    unknown = set(cand["needs"]) - set(needs)
    if unknown:
        sys.exit(f"candidates for unknown needs: {sorted(unknown)}")

    calls = [(s["tool"], s.get("arguments", {})) for n in needs for s in cand["needs"].get(n, []) if s["kind"] == "mcp_tool"]
    answers = iter(asyncio.run(Agent(man["mcp"]["server"], man["mcp"]["launch"], env).run(calls)) if calls and man["mcp"] else [])

    bindings, findings = {}, []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for nid, (kind, need) in needs.items():
            attempts, bound = [], None
            for src in cand["needs"].get(nid, []):
                status, data = next(answers) if src["kind"] == "mcp_tool" else ("ok", None)
                att = {"source": src}
                try:
                    if status != "ok":
                        raise RuntimeError(data)
                    if kind == "structure":
                        path, fmt = structure_file(src, data, tmp, skill)
                        att |= judge_structure(path, fmt, need, entry, tmp)
                    else:
                        val = dig(data, src["extract"]["path"])
                        ref = claims[need["claim"]]["reference"]
                        att |= {"result": "bound" if ref_matches(val, ref) else "mismatch", "method": "value",
                                "observed": val, "expected": ref["value"]}
                except Exception as e:
                    att |= {"result": "error", "detail": str(e)[:300]}
                attempts.append(att)
                if att["result"] in ("bound", "mismatch"):
                    bound = att
                    break
            if bound is None and kind == "structure":  # nothing usable from the agent: authority fallback
                src = {"kind": "authority"}
                out = tmp / "auth.canon"
                try:
                    info = canon(["fetch", "--locator", json.dumps(need["authority"]["locator"]),
                                  "--precision", repr(need["authority"]["precision_A"]), "--paper-skill", str(skill),
                                  "--out", str(out)])
                    att = {"source": src, "result": "bound" if info["sha256"] == need["sha256"] else "mismatch",
                           "method": "hash", "observed_sha256": info["sha256"], "rmsd_A": None}
                except Exception as e:
                    att = {"source": src, "result": "error", "detail": str(e)[:300]}
                attempts.append(att)
                bound = att if att["result"] in ("bound", "mismatch") else None
            required = kind == "structure"
            if bound is None:
                status = "unbound"
                findings.append({"kind": "unbound_required" if required else "unbound_optional", "need": nid,
                                 "detail": "no candidate produced a usable result"})
            else:
                status = bound["result"]
                if status == "mismatch":
                    findings.append({"kind": "data_paper_mismatch", "need": nid,
                                     "detail": json.dumps({k: bound.get(k) for k in ("observed", "expected", "rmsd_A", "observed_sha256")})})
            bindings[nid] = {"status": status, "required": required, "source": bound["source"] if bound else None,
                             "method": bound.get("method", "none") if bound else "none",
                             "observed_sha256": bound.get("observed_sha256") if bound else None,
                             "canonical_sha256": need["sha256"] if kind == "structure" and status == "bound" else None,
                             "rmsd_A": bound.get("rmsd_A") if bound else None,
                             "observed": bound.get("observed") if bound else None,
                             "expected": bound.get("expected") if bound else None,
                             "attempts": attempts}
    doc = {"schema": "bridge/bindings/1", "profile_sha256": sha(a.profile), "manifest_sha256": sha(a.manifest),
           "bindings": bindings, "findings": findings}
    check(doc, "bindings")
    Path(a.out).write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    summary = {n: b["status"] + (f" via {b['source']['kind']}/{b['method']}" if b["source"] else "") for n, b in bindings.items()}
    print(json.dumps({"bindings": summary, "findings": len(findings)}, indent=1))


if __name__ == "__main__":
    main()
