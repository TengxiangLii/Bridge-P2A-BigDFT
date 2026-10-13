# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2", "numpy>=1.26"]
# ///
"""Test fixture: a simulated *foreign* P2A agent for Fisicaro 2023, modelled on a Codex P2A run.

It exposes the same archive data as our agent, but with different tool names, argument names and
property keys, and no structure tool. The bridge must bind to it without any plugin change.
Data: the three Materials Cloud files in $CLUSTER_DATA_DIR.
"""
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cluster_isomers_alt")
RENAME = {"Homo-Lumo-gap": "homo_lumo_gap_eV", "Vertical-Ionization-energy": "vertical_ionization_energy_eV",
          "Vertical-Electron-Affinity": "vertical_electron_affinity_eV", "Chemical-Hardness": "chemical_hardness_eV",
          "KS-Final-energy": "total_energy_hartree", "Pointgroup": "point_group"}


@lru_cache
def db():
    d = Path(os.environ["CLUSTER_DATA_DIR"])
    names = np.load(d / "all_minima_names.npy", allow_pickle=True).item()
    data = np.load(d / "all_minima_data.npy", encoding="latin1", allow_pickle=True).item()
    return names, data


def family(label):
    names, _ = db()
    return next(c for c in names if label in names[c])


@mcp.tool()
def cluster_list_systems() -> list[str]:
    """List every system label (cluster family + charge suffix, e.g. Al13m1)."""
    names, _ = db()
    return sorted(s for c in names for s in names[c])


@mcp.tool()
def cluster_summarize_isomer_counts() -> dict:
    """Number of isomers per system label."""
    names, _ = db()
    return {s: len(names[c][s]) for c in names for s in names[c]}


@mcp.tool()
def cluster_list_isomers(system_label: str, limit: int = 20) -> list[str]:
    """Isomer file names of a system, lowest energy first."""
    names, _ = db()
    return list(names[family(system_label)][system_label])[:limit]


@mcp.tool()
def cluster_get_isomer_properties(system_label: str, isomer_index: int = 0) -> dict:
    """Selected stored properties of one isomer (index 0 = global minimum)."""
    names, data = db()
    c = family(system_label)
    name = list(names[c][system_label])[isomer_index]
    rec = data[c][system_label][name]
    return {"isomer": name, "properties": {RENAME[k]: float(v) if not isinstance(v, str) else v
                                           for k, v in rec.items() if k in RENAME}}


if __name__ == "__main__":
    mcp.run()
