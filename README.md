# Bridge-P2A-BigDFT (v1 snapshot, archived)

> **Status: recorded snapshot. The bridge is being rebuilt from scratch, so this version will not be developed further.**
> It is kept as a reference for the rebuild. See `docs/paper2profile-infra.md` for the design direction.

This bridge connects agents built with [Paper2Agent](https://github.com/jmiao24/Paper2Agent) (P2A) to the [BigDFT](https://bigdft.org) skills ([bigdft-skills](https://github.com/william-dawson/bigdft-skills)). Its purpose is to re-run a paper's reported calculations with BigDFT and give each claim a verdict.

## Layout: universal and paper-specific parts

```text
universal/                         PAPER-INDEPENDENT: same for every paper
  README.md
  bigdft-cross-verify/
    SKILL.md                       workflow, verdict vocabulary, tolerance defaults, approval gates
    profile-schema.md              reproduction profile schema (bigdft-cross-verify/profile/1)
    report-contract.md             required output files
    validate_profile.py            structural validator (stdlib; --selftest)
paper-specific/                    ONE FOLDER PER PAPER: facts only, no workflow
  fisicaro2023/
    profile.json                   reproduction profile for Fisicaro et al., Mater. Adv. 2023, 4, 1746
    SKILL.md                       pointer skill that hands profile.json to bigdft-cross-verify
docs/
  paper2profile-infra.md           design for the rebuild (Paper2Profile, templates, binder, registry)
  paper2profile-gold-profiles.md   parked idea: calibration corpus and gold profiles
```

The two parts meet only in the profile file. The universal skill reads every paper fact from `profile.json` and holds none itself.

## What this snapshot is

- **Universal skill (`bigdft-cross-verify`, v0.1.0).** Tested in planning-only runs:
  - a same-code case (this paper) and a cross-code case (a VASP paper);
  - on two compute targets, IMLab and TSUBAME;
  - each run went up to the job-submission approval gate.

  It has **not** been run end-to-end with a real BigDFT calculation.
- **Fisicaro 2023 profile.** It validates against the schema, with 9 claims, 5 excluded claims and 6 unknown settings. Its reference values were checked against the database. Two definitions were verified against the data rather than taken from the paper's wording: the ζ-weighted average bond distance, and the Table 1 degeneracy notation.

## Known limitations (reasons for the rebuild)

- **Free-text definitions.** Each claim's `computation` field is written per paper, so two independently generated profiles can disagree.
- **Tool names in the profile.** The profile names the MCP tools of one specific P2A output (`minima_database_*`). Other P2A runs for the same paper expose different tools; one run's tools were `cluster_*`, with no structure tool.
- **No generator or registry.** Profiles are hand-written, and there is no way to share one profile across researchers.

The rebuild design in `docs/paper2profile-infra.md` addresses all three, with claim templates, abstract data needs plus a binder, a Paper2Profile generator and a profile registry.

## Related

- Paper agent this profile was written for: [P2A-Fisicaro-2023](https://github.com/TengxiangLii/P2A-Fisicaro-2023)
- Paper: G. Fisicaro, B. Schaefer, J. A. Finkler, S. Goedecker, *Mater. Adv.* 2023, 4, 1746, doi:[10.1039/D2MA01088G](https://doi.org/10.1039/D2MA01088G)

## License

The code and docs are MIT ([LICENSE](LICENSE)). The profile quotes short facts from the CC BY 4.0 paper and its CC BY 4.0 data record (doi:10.24435/materialscloud:46-nr), with attribution.
