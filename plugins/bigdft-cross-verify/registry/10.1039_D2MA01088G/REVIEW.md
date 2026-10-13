# Review record: 10.1039/D2MA01088G

| Artifact | Version | Status | sha256 |
|---|---|---|---|
| `profile.json` | 2.0.0 | **reviewed** | e871ed66be796cd2a1dabdf0ea8619c7683efc8a1d02847a18241cfcc79fba3b |
| `bigdft-mapping.json` | 1.0.0 | **draft** | 2fd9ffe73c6eaccc0fadc476d027fb87be645e866aa41ae418013cc82a0ee4c5 |
| `psp/psppar.Al.yaml` | from PyBigDFT `BigDFT/Database/psppar/SS` | used by the mapping | b72340e5ee6d7e7fb63e260c952b544ee3114da8b20648c4a708652a306457d6 |
| `psp/psppar.Si.yaml` | same source | used by the mapping | 168ab62c7eb787e1647bede9889b1d3557ddd1dec5e405f277ad53738ef98a9f |

## Profile

- **2026-10-13, S7 independent reviewer agent.** Verdict: changes required, with 0 blocking, 5 should-fix and 6 notes (`review-s7.md`).
- **2026-10-13, authors.** Applied F1–F5 and five of the six notes; the open note (F6, reference needs for non-default claims) stays open. Two optional wording nits were also applied.
- **2026-10-13, S7 re-review.** Verdict: approve (`review-s7.md`, "Re-review").
- **Mechanical checks on the released bytes:** `validate.py profile` passes; `quote_check.py` passes 28 of 28 against the P2A paper skill `fisicaro2023-isomer-stability-paper`. Structure hashes were recomputed independently by the reviewer for al13m1-r0, al13m1-r3 and si10-r0.

## Mapping and templates

- **Status:** draft until a BigDFT expert reviews them (design §13). Every result is labelled *unreviewed mapping*.
- **Evidence so far:** a 2026-10-05 IMLab run with the same Al file and dft block reproduced the Al13⁻ gap (1.8886 vs 1.8821 eV) and degeneracy, while the absolute energy differed (−63.31 vs −26.67 Ha). The absolute energy is therefore diagnostic only.
- **To sign off:** a BigDFT expert, plus us. Record name, date and the artifact sha256 here.
