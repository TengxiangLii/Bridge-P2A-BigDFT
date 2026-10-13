# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26"]
# ///
"""Canonical structures: one place that turns any structure source into canonical bytes + sha256.

  canon   --in FILE --format bigdft_xyz|xyz|paper_table_csv --precision P [--out FILE]
  fetch   --locator JSON --precision P [--paper-skill DIR] [--cache DIR] [--out FILE]
  compare --a CANON_FILE --b CANON_FILE --threshold A          (RMSD in Angstrom after alignment)

Canonical form (design C3): coordinates in Angstrom, centred at the centroid, rounded to the
authority precision, atoms sorted by (element, x, y, z), fixed text format. Output is JSON on stdout.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np

BOHR_A = 0.529177210903
UNIT_TOKENS = {"angstroem": 1.0, "angstroemd0": 1.0, "angstrom": 1.0, "a": 1.0,
               "atomic": BOHR_A, "atomicd0": BOHR_A, "bohr": BOHR_A, "bohrd0": BOHR_A}


def parse(text: str, fmt: str) -> list[tuple[str, float, float, float]]:
    """Atoms in Angstrom from a BigDFT xyz, plain xyz, or element,x,y,z CSV (Angstrom)."""
    if fmt == "paper_table_csv":
        rows = list(csv.DictReader(io.StringIO(text)))
        return [(r["element"].strip(), float(r["x"]), float(r["y"]), float(r["z"])) for r in rows]
    lines = text.splitlines()
    head = lines[0].split()
    n = int(head[0])
    scale = 1.0
    if fmt == "bigdft_xyz":
        unit = head[1].lower() if len(head) > 1 else "angstroem"
        if unit not in UNIT_TOKENS:
            raise ValueError(f"unknown BigDFT xyz units {head[1]!r}")
        scale = UNIT_TOKENS[unit]
    atoms = []
    for line in lines[2:2 + n]:  # BigDFT files carry a forces block after the coordinates; it is ignored
        t = line.split()
        atoms.append((t[0], float(t[1]) * scale, float(t[2]) * scale, float(t[3]) * scale))
    if len(atoms) != n:
        raise ValueError(f"expected {n} atoms, read {len(atoms)}")
    return atoms


def canonical(atoms, precision: float) -> str:
    d = round(-math.log10(precision))
    if abs(10 ** -d - precision) > 1e-12:
        raise ValueError("precision must be a power of ten, e.g. 1e-6")
    xyz = np.array([a[1:] for a in atoms])
    xyz -= xyz.mean(axis=0)
    rows = []
    for (el, *_), (x, y, z) in zip(atoms, xyz):
        r = [round(v, d) + 0.0 for v in (x, y, z)]  # + 0.0 turns -0.0 into 0.0
        rows.append((el, *r))
    rows.sort()
    body = "".join(f"{el} {x:.{d}f} {y:.{d}f} {z:.{d}f}\n" for el, x, y, z in rows)
    return f"canonical-structure/1\nprecision_A {precision:g}\nnatoms {len(rows)}\n{body}"


def read_canonical(text: str):
    lines = text.splitlines()
    assert lines[0] == "canonical-structure/1", "not a canonical structure"
    atoms = [(t[0], *map(float, t[1:4])) for t in (l.split() for l in lines[3:])]
    return [a[0] for a in atoms], np.array([a[1:] for a in atoms])


def rmsd(a_text: str, b_text: str) -> float:
    """RMSD after centring and optimal rotation: nearest-neighbour matching + Kabsch, iterated (ICP).
    ponytail: converges for sources of the same isomer that differ by rounding, precision or a small
    rotation (< ~0.3 rad); a large rotation needs a global matcher (e.g. Hungarian over invariants)."""
    ea, A = read_canonical(a_text)
    eb, B = read_canonical(b_text)
    if sorted(ea) != sorted(eb):
        return math.inf

    def match(P):  # greedy nearest neighbour of the same element
        order, used = [], set()
        for i, p in enumerate(P):
            j = min((float(np.linalg.norm(p - B[j])), j) for j in range(len(B)) if j not in used and eb[j] == ea[i])[1]
            used.add(j)
            order.append(j)
        return B[order]

    P, best = A, math.inf
    for _ in range(10):
        Q = match(P)
        H = A.T @ Q
        U, _, Vt = np.linalg.svd(H)
        D = np.diag([1.0, 1.0, float(np.sign(np.linalg.det(Vt.T @ U.T)))])
        P = A @ (Vt.T @ D @ U.T).T
        r = float(np.sqrt(((P - Q) ** 2).sum(axis=1).mean()))
        if r >= best - 1e-12:
            break
        best = r
    return best


def fetch_text(loc: dict, paper_skill: str | None, cache: Path) -> str:
    if loc.get("file"):
        if not paper_skill:
            raise ValueError("--paper-skill is required for a file locator")
        return (Path(paper_skill) / loc["file"]).read_text()
    url = loc["url"]
    cache.mkdir(parents=True, exist_ok=True)
    local = cache / hashlib.sha256(url.encode()).hexdigest()
    if not local.exists():
        part = local.with_suffix(".part")
        urllib.request.urlretrieve(url, part)
        if loc.get("md5") and hashlib.md5(part.read_bytes()).hexdigest() != loc["md5"]:
            raise ValueError(f"md5 mismatch for {url}")
        part.replace(local)
    if loc.get("member"):
        with tarfile.open(local) as tar:
            m = tar.getmember(loc["member"])  # only the named member; never extractall
            if not m.isfile():
                raise ValueError(f"{loc['member']} is not a regular file")
            return tar.extractfile(m).read().decode()
    return local.read_text()


def emit(text: str, out: str | None, extra: dict | None = None):
    if out:
        Path(out).write_text(text)
    names = [l.split()[0] for l in text.splitlines()[3:]]
    formula = "".join(f"{e}{names.count(e)}" for e in sorted(set(names)))
    print(json.dumps({"sha256": hashlib.sha256(text.encode()).hexdigest(), "natoms": len(names),
                      "formula": formula, **(extra or {})}, sort_keys=True))


def selftest():
    a = [("Al", 0.0, 0.0, 0.0), ("Al", 1.0, 0.0, 0.0), ("Al", 0.0, 1.0, 0.0)]
    t = canonical(a, 1e-3)
    shifted = [(e, x + 5, y - 2, z + 1) for e, x, y, z in reversed(a)]  # translation + reordering
    assert canonical(shifted, 1e-3) == t
    bohr = "3 atomicd0 0 (Ha)\nfree\n" + "".join(f"Al {x / BOHR_A} {y / BOHR_A} {z / BOHR_A}\n" for _, x, y, z in a)
    assert canonical(parse(bohr, "bigdft_xyz"), 1e-3) == t
    c, s = math.cos(0.05), math.sin(0.05)
    rot = [(e, c * x - s * y, s * x + c * y, z) for e, x, y, z in reversed(a)]  # small rotation, shuffled
    assert canonical(rot, 1e-3) != t and rmsd(canonical(rot, 1e-3), t) < 2e-3
    other = [("Al", 0.0, 0.0, 0.0), ("Al", 1.5, 0.0, 0.0), ("Al", 0.0, 1.0, 0.0)]  # a different structure
    assert rmsd(canonical(other, 1e-3), t) > 0.1
    print("selftest ok")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("canon"); c.add_argument("--in", dest="inp", required=True); c.add_argument("--format", required=True)
    c.add_argument("--precision", type=float, required=True); c.add_argument("--out")
    f = sub.add_parser("fetch"); f.add_argument("--locator", required=True); f.add_argument("--precision", type=float, required=True)
    f.add_argument("--paper-skill"); f.add_argument("--cache", default=str(Path.home() / ".cache" / "bridge-p2a-bigdft"))
    f.add_argument("--out")
    m = sub.add_parser("compare"); m.add_argument("--a", required=True); m.add_argument("--b", required=True)
    m.add_argument("--threshold", type=float, required=True)
    sub.add_parser("selftest")
    a = p.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "canon":
        emit(canonical(parse(Path(a.inp).read_text(), a.format), a.precision), a.out)
    elif a.cmd == "fetch":
        loc = json.loads(a.locator)
        emit(canonical(parse(fetch_text(loc, a.paper_skill, Path(a.cache)), loc["format"]), a.precision), a.out)
    else:
        r = rmsd(Path(a.a).read_text(), Path(a.b).read_text())
        print(json.dumps({"rmsd_A": r, "match": r <= a.threshold}, sort_keys=True))
        sys.exit(0 if r <= a.threshold else 1)


if __name__ == "__main__":
    main()
