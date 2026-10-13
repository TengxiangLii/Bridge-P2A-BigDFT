---
name: fisicaro2023-bigdft-profile
description: Use when re-running or double-checking results of Fisicaro et al. 2023, "Principles of isomer stability in small clusters" (Mater. Adv.), with BigDFT, e.g. HOMO-LUMO gaps, eigenvalue degeneracies, isomer energy ordering, ionization energies or hardness of the Na, Mg, Al, Al12Si, Si and Ge clusters.
---

# Fisicaro 2023 reproduction profile

[profile.json](profile.json) in this directory is the reproduction profile for this paper. It is the paper-specific input to the paper-independent `bigdft-cross-verify` skill, which must be installed (plugin `bigdft-cross-verify`).

Run that skill with `profile` = the absolute path of `profile.json` here, and the compute target the user names. Do not copy facts from this profile into the workflow; the skill reads them from the file.

What the profile provides:

- **Tier:** `same_code`, since the paper used BigDFT.
- **Sources:** structures and reference values come from the `small_cluster_isomers` MCP tools of this plugin. The method settings cite the paper's Methods section and the dataset notebook.
- **Claims:** 9 claims, plus 5 excluded claims with reasons. The default set runs on the Al13^-1 global minimum: `gm-homo-lumo-gap`, `gm-eigenvalue-degeneracy`, `isomer-energy-ordering`, `gm-vertical-ionization-energy`.
- **Notes for whoever runs it:** unknown settings (grid, exact pseudopotential files, BigDFT version), plus dataset notation caveats in `known_notes`.

To change which claims run, pass a `claims` subset to the skill. To change a definition or tolerance, edit `profile.json` and re-validate it with the skill's `validate_profile.py`.
