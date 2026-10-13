# /// script
# requires-python = ">=3.10"
# ///
"""Check that every quote and table reference in a profile exists in the P2A paper skill.

  quote_check.py --profile PROFILE --paper-skill DIR

Table locations: "table:<csv>#row=<first-column value>;col=<header>" or "table:<csv>#rowindex=<n>;col=<header>"
(n = 1-based data row, for continuation rows whose first column is empty).
Quotes are matched after the same normalisation on both sides: HTML tags dropped (content kept),
markdown emphasis and LaTeX markup removed, every dash and minus mapped to '-', whitespace collapsed,
case folded. Table references ("table:<csv>#row=<first-column value>;col=<header>") are checked by
reading the cell. Dataset references are not in the paper skill; the binder's probes check those.
Exit 0 when every check passes.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d"), "-")


def normalise(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)                         # <sub>13</sub> -> 13
    s = re.sub(r"\\(?:mathrm|text|mathit|mathbf)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)                    # remaining LaTeX commands
    s = re.sub(r"[$*_{}^]", "", s)                        # math delimiters, emphasis, braces
    s = s.translate(DASHES)
    return re.sub(r"\s+", " ", s).strip().casefold()


def corpus(skill: Path) -> str:
    parts = [p.read_text() for p in sorted((skill / "references").glob("*.md"))]
    parts += [p.read_text() for p in sorted((skill / "assets").rglob("*.csv"))]
    return normalise("\n".join(parts))


def table_cell(skill: Path, location: str) -> str:
    m = re.fullmatch(r"table:([^#]+)#(row|rowindex)=(.*);col=(.*)", location)
    if not m:
        raise ValueError(f"bad table location {location!r}")
    rows = list(csv.reader((skill / m[1]).open()))
    header, how, key, col = rows[0], m[2], m[3], m[4]
    if col not in header:
        raise ValueError(f"column {col!r} not in {m[1]}")
    if how == "rowindex":
        n = int(key)
        if not 1 <= n < len(rows):
            raise ValueError(f"rowindex {n} out of range in {m[1]}")
        return rows[n][header.index(col)]
    for r in rows[1:]:
        if r and r[0] == key:
            return r[header.index(col)]
    raise ValueError(f"row {key!r} not in {m[1]}")


def check_reference(ref: dict, skill: Path, text: str) -> str | None:
    """None if fine, else the reason it fails."""
    loc = ref["location"]
    if loc.startswith("table:"):
        try:
            cell = table_cell(skill, loc)
        except ValueError as e:
            return str(e)
        v = ref["value"]
        if isinstance(v, (int, float)):
            dec = ref.get("printed_decimals")
            same = cell.strip() == f"{v:.{dec}f}" if dec is not None else float(cell.translate(DASHES)) == v
        else:
            same = normalise(cell) == normalise(v if isinstance(v, str) else json.dumps(v))
        return None if same else f"table cell {cell!r} != reference {v!r}"
    if ref.get("quote"):
        return None if normalise(ref["quote"]) in text else "quote not found in the paper skill"
    if ref["confidence"] in ("dataset",):
        return None
    return "a table/text/figure reference needs a quote or a table location"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--paper-skill", required=True)
    a = ap.parse_args()
    skill = Path(a.paper_skill)
    prof = json.loads(Path(a.profile).read_text())
    text = corpus(skill)
    failures, checked = [], 0
    for key, s in prof["settings"].items():
        if s["state"] == "stated":
            checked += 1
            if normalise(s["quote"]) not in text:
                failures.append({"where": f"settings.{key}", "reason": "quote not found", "quote": s["quote"]})
    for c in prof["claims"]:
        for i, ref in enumerate([c["reference"], *c.get("cross_checks", [])]):
            checked += 1
            why = check_reference(ref, skill, text)
            if why:
                failures.append({"where": f"claim {c['id']} " + ("reference" if i == 0 else f"cross_check {i}"), "reason": why})
    print(json.dumps({"checked": checked, "failures": failures}, indent=1, ensure_ascii=False))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    assert normalise("Al<sub>13</sub><sup>−1</sup> the Perdew–Burke") == normalise("Al13-1 the Perdew-Burke")
    assert normalise(r"$E_{\mathrm{KS}}$") == "eks"
    main()
