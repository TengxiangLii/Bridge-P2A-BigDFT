# /// script
# requires-python = ">=3.10"
# ///
"""Write run directories for one batch: <out>/<run_id>/{<run_id>.yaml, <run_id>.xyz}, byte-for-byte from the plan.

  export_runs.py --plan run-plan.json [--round round.json] --out DIR

Without --round the plan's initial_batch is exported; with it, the round's next_batch.
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", required=True)
    ap.add_argument("--round")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    batch = json.loads(Path(a.round).read_text())["next_batch"] if a.round else plan["initial_batch"]
    for rid in batch:
        d = Path(a.out) / rid
        d.mkdir(parents=True, exist_ok=True)
        for name, text in plan["runs"][rid]["files"].items():
            (d / name).write_text(text)
    print(json.dumps({"exported": batch, "out": a.out}))


if __name__ == "__main__":
    main()
