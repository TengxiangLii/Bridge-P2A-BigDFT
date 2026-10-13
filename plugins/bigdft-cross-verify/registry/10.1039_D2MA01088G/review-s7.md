# S7 independent review: profile 10.1039_D2MA01088G (fisicaro2023-isomer-stability v2.0.0)

Reviewer: independent S7 reviewer (did not author the profile). Review only; no profile edits.

## Mechanical checks (re-run)

- `validate.py profile ... --registry-entry ...`: `profile: valid`
- `quote_check.py`: 24 quotes checked, 0 failures.
- Structure hashes recomputed with `canonical_structure.py fetch --precision 1e-6`. All three match the profile:
  - al13m1-r0 `a278ce67...a6`, al13m1-r3 `9c0fc9a8...f7`, si10-r0 `eace7238...fb`.
- Archive md5 `d8e75cc8c91d8143fc2ed89259a9741e` matches the local copy. The xyz header energies agree with `KS-Final-energy` to about 1e-9 Ha (min0001: -26.6726823172 vs -26.6726823162; Si10 min000000001: -39.0586617489 vs -39.0586617489). All files have `free` BC.

## What was verified as correct

- **Settings.** Every `stated` value is supported by §II Methods (paper.md l.49): Libxc PBE, Mg LDA, wavelets with free BC, soft norm-conserving NLCC pseudopotentials (refs 50 = GTH 1996 and 51 = Willand 2013), spin polarization for odd electron counts, an assumed singlet for even counts, zero electronic temperature except 3e-3 Ha for odd-electron Mg, and 0.5 meV/Å forces. The structure source is ref 55, doi:10.24435/materialscloud:46-nr. `code_version` and `scf_convergence` are correctly `unknown`: neither the paper nor the ESI states them. `solvation` and `k_points` are correctly `not_applicable`, and the soft-sphere cavity is only a descriptor. Nothing stated in the paper is filed as unknown.
- **Structures.** Dataset `_select('Al13m1', None, k)` gives names min0001..min0006 for ranks 0..5, which matches the members. Si10 rank 0 is min000000001.xyz. Al13^-1 has 40 electrons and Si10 has 40, so charge -1/0 with multiplicity 1 is correct (singlet for even counts, as in §II).
- **Reference values.** Each one equals the dataset value bit-for-bit for the named isomer:
  - gap 1.88213733039336 eV and 2.09055726189791 eV
  - VIE 3.567871607220811 eV
  - VEA -1.4665926176456832 eV
  - hardness 2.517232112433247 eV
  - E_KS -26.672682316180612 Ha
  - degeneracy patterns [1,3,5,1,3,3,4] and [1,1,2,1,2,2,1,1,2,1,1,2,2,1]
  - ordering values = `Fingerprint-distance-GM[0]` of r0..r5 (notebook cell 9: "energy with respect to the global minimum [Ha]")
- **Pattern sums.** Both patterns sum to 20 occupied orbitals, which is 40 electrons.
- **Definitions vs templates.**
  - VIE = E(N-1) - E(N) and VEA = E(N) - E(N+1) at the frozen N geometry. This matches paper.md l.249 (§III.B.2, next to eqn 6).
  - Hardness = (VIE - VEA)/2, which matches eqn (6) and notebook "CH = (VIE - VEA) * 0.5". Numeric check: (3.567871607 + 1.466592618)/2 = 2.517232112, which equals the stored value. This confirms the VEA sign convention.
  - Gap: (Lumo - Homo) = 0.06916727 Ha × 27.2114 = 1.8821 eV.
  - Ordering: the r1 KS-Final-energy difference is 0.035694024 Ha against the stored 0.035694019 Ha.
  - A reference in Ha against an eV template is accepted by `validate.py` l.79, and `evaluate_claims` converts it.
- **Degeneracy threshold.** 1e-4 Ha is the correct value for the dataset key (notebook cell 9: "considered degenerate if their difference is lower than 10^-4 Ha").
- **Cross-checks.**
  - Table 1 rows Al13^-1 (gap 1.88, hardness 2.52) and Si10 (gap 2.09) are the right cells.
  - Table 2 row Al13^-1 "1 (GM)" gives [1, 3, 5, 1, 3, 3, 4], the right cell.
  - Si10 correctly has no table cross-check: Table 1 shows only the distinct-value set "[1,2,3*,7*]".
- **Excluded.** The adiabatic IE is correctly excluded: the word "adiabatic" does not appear anywhere in paper.md or supplement.md.
- **Note 2.** "22 systems not monotonic" is confirmed: 22 charge states, including Al13m1. Al13m1 ranks 0..5 themselves are monotonic, so the ordering claim is unaffected.

## Findings

### F1 [should-fix] `excluded[3]` (Al12Si) has a wrong statement and an incomplete reason
- **Evidence:**
  - The dataset Al12Si records have exactly 11 keys: Coordination, Dipole, Eccentricity, Fermi-level, Fingerprint-distance-GM, Homo-Lumo, Homo-Lumo-gap, KS-Final-energy, Pointgroup, Shape-factor, Soft-spheres-cavity. `Eigenvalue-degeneracy` is missing too, so "beyond energies, gap and degeneracy" is wrong.
  - The paper itself reports Al12Si hardness and degeneracy sets in Table 1 (row `Al12 Si`: gap 2.00, hardness 2.73, Ih, KS degeneracies [1,3,4,5,6*,7*]; also the -1, +1 and +2 rows). So "no reference for VIE/VEA/hardness" is only true for the dataset.
- **Correction:**
  - Restate as "Al12Si: the dataset has no Eigenvalue-degeneracy, VIE, VEA or hardness keys."
  - Either add a table-confidence claim (`chemical_hardness@1` on the Al12Si GM, value 2.73 eV, `printed_decimals: 2`, plus `homo_lumo_gap@1` with the dataset gap and a Table 1 cross-check of 2.00), or say explicitly that the table-only hardness was deliberately not offered.
  - Al and Si are both mapped, and neutral Al12Si (40 e, Ih) is closed-shell, so the computation is feasible.

### F2 [should-fix] The degeneracy threshold is not documented, and it conflicts with the paper text
- **Location:** `claims[al13m1-eigenvalue-degeneracy].parameters.threshold_Ha`, `claims[si10-eigenvalue-degeneracy]`, `notes[0]`
- **Evidence:**
  - Paper §III.B.1 (paper.md l.165): "We considered KS eigenvalues to have an approximate degeneracy if they differ by less then 10^-2 Ha". This is the starred grouping in Table 1.
  - The dataset uses 10^-4 Ha (all_minima_data_analysis.ipynb cell 9).
  - The profile uses 1e-4, which is correct for the dataset reference, but nothing in the profile says where that number comes from. A reader checking against the paper text would flag it as wrong.
- **Correction:**
  - Add a `definition_note` to both degeneracy claims: "threshold 1e-4 Ha from the dataset notebook (all_minima_data_analysis.ipynb); the paper's 1e-2 Ha approximate-degeneracy threshold applies to the starred entries of Table 1".
  - Extend `notes[0]` with the two thresholds.

### F3 [should-fix] VEA and hardness for an anion require an unbound dianion, so the result depends on box size
- **Location:** `claims[al13m1-vea]`, `claims[al13m1-hardness]`
- **Evidence:**
  - The stored VEA is -1.467 eV: Al13^2- is unbound by 1.47 eV.
  - With free BC and a finite wavelet box, the energy of the extra electron depends on the grid extent (rmult). The paper does not state rmult (see `settings.basis_or_grid`). The mapping only tested rmult sensitivity for the gap.
  - `al13m1-vea` has a `definition_note` mentioning this, but `al13m1-hardness` uses the same N+1 run and carries no note.
- **Correction:**
  - Add the same caveat to `al13m1-hardness`.
  - Prefer a bound-anion hardness test: Si10 has VEA +1.985 eV, VIE 7.865 eV and hardness 2.93985 eV, with a Table 1 cross-check of 2.94 (row Si10, col Chemical Hardness). The structure si10-r0 is already in the profile.
  - Keep both Al13^-1 claims out of `default_claims`, as now.

### F4 [should-fix] Missing claims: Table 2 degeneracies for Al13^-1 minima 2 and 4, whose structures are already in the profile
- **Evidence:**
  - Table 2 "Minimum" is 1-based, with 1 = GM.
  - Table 2 Al13^-1 minimum 2 gives [1,1,2,2,1,2,1,2,1,2,1,1,2,1]. This equals dataset rank 1 (min0002, structure `al13m1-r1`).
  - Minimum 4 gives [1,1,2,1,2,1,2,1,2,2,1,2,1,1]. This equals dataset rank 3 (min0004, `al13m1-r3`, hash re-verified above).
  - These are cheap: each is one N-electron run on a structure that is already hashed, with both a dataset reference and a table cross-check.
  - Minima 13 and 105 (ranks 12 and 104) are also in Table 2. The dataset rank 12 list [1,1,2,1,2,2,1,1,1,2,3,1,2] matches Table 2 apart from Table 2's "3*" marker.
- **Correction:**
  - Add `al13m1-r1-eigenvalue-degeneracy` and `al13m1-r3-eigenvalue-degeneracy` (threshold 1e-4, dataset reference, cross-check `table-2.csv#row=Al13^-1 minimum 2/4`).
  - Optionally list minima 13 and 105 in `needs_template` or `excluded` (new structures needed; the "3*" marker is ambiguous).

### F5 [should-fix] Paper results that appear in neither `excluded` nor `needs_template`
- **Evidence and correction:** add one `excluded` entry each for:
  - Transition states, barriers and disconnectivity graphs (§II "minima hopping guided path search with the stabilized quasi-Newton saddle optimizer"; Fig. 8 Mg10 saddle; Fig. 16). Reason: needs saddle searches, and no dataset reference exists.
  - DoS under random atomic displacements (Fig. 12, S4; δ = 0.01 and 0.5 Å). Reason: random displacements are not reproducible, and the 0.1 eV Gaussian broadening is figure-only.
  - The Al12X substitution series (§III.C, Figs 19-20: Al12C, Al12Ge, ...). Reason: not in the dataset, and elements are not mapped.
  - Surface/volume ratio, coordination and fingerprint distances (§III.A, Figs 4-7). Reason: geometric descriptors, not DFT quantities; the soft-sphere cavity uses a 0.4 mesh (notebook).

### F6 [note] `reference_needs` covers 3 of 9 claims
- **Location:** `reference_needs`
- **Evidence:** Two of the four `default_claims` have no binding to an agent output: `al13m1-eigenvalue-degeneracy` (dataset key `Eigenvalue-degeneracy`) and `al13m1-energy-ordering` (key `Fingerprint-distance-GM[0]` or KS-Final-energy per isomer). `al13m1-vea`, `al13m1-hardness`, `al13m1-total-energy` and `si10-eigenvalue-degeneracy` are also unbound.
- **Correction:** If agent-side binding is intended for every dataset-confidence reference, add the missing needs (e.g. `ref:al13m1-degeneracy` with quantity `Eigenvalue-degeneracy`). If the omission is deliberate, say so in `notes`.

### F7 [note] `settings.charge_states.value` understates the paper
- **Evidence:** Table 1 itself lists Si15^+3 (table-1.csv row `Si15^+3`), so +3 is not dataset-only. The abstract and §III say q = -1, 0, 1, 2.
- **Correction:** Change the value to "q = -1, 0, 1, 2 (text); Table 1 and the dataset also include Si15^+3".

### F8 [note] `settings.basis_or_grid.value` says "Daubechies"
- **Evidence:** The §II text says only "wavelets". "Daubechies" comes from the title of ref 47.
- **Correction:** This is acceptable, but cite it ("Daubechies wavelets (ref 47)") so the value is traceable.

### F9 [note] The energy-ordering claim has close-lying isomers
- **Location:** `claims[al13m1-energy-ordering]`
- **Evidence:**
  - ΔE(r3) - ΔE(r2) = 2.46 mHa (67 meV).
  - ΔE(r5) - ΔE(r4) = 1.31 mHa (36 meV).
  - The mapping uses SS (Saha 2015) pseudopotentials rather than the paper's files, so a flip of r4/r5 is plausible.
- **Correction:** None required; this is a good discriminating test. Consider adding to `notes` that r4/r5 are 36 meV apart, so a verdict on order alone should be read with the dE tolerance.

### F10 [note] `needs_template[0]` (point group) lacks the dataset tolerance
- **Evidence:** Notebook: "Point group from get_pymatgen_pointgroup(filename, tol=0.0009)".
- **Correction:** Add "pymatgen PointGroupAnalyzer, tol = 0.0009" to `suggested_quantity`.

### F11 [note] `claims[al13m1-energy-ordering].reference.location` could name the equivalent key
- **Evidence:** `Fingerprint-distance-GM[0]` is the stored ΔE. It agrees with KS-Final-energy differences to 5e-9 Ha.
- **Correction:** Optionally add "(equals KS-Final-energy(k) - KS-Final-energy(0) to 5e-9 Ha)".

## default_claims

`[al13m1-homo-lumo-gap, al13m1-eigenvalue-degeneracy, al13m1-energy-ordering, al13m1-vie]` is a sensible small set. It uses the one mapped element that has been tested (Al), covers four different quantity kinds, and costs about 8 single points of 13 atoms. It keeps out the box-sensitive dianion claims and the diagnostic total energy. No change required. Once F3 is addressed, a Si10 claim (gap or hardness) could be swapped in for element diversity, but that is optional because Si is still untested in the mapping.

## Notes field

- `notes[0]`: correct, but add the thresholds (F2).
- `notes[1]`: correct; 22 charge states verified.
- `notes[2]` and `notes[3]`: consistent with the mapping, where Mg, Na and Ge are `not_mappable`.

## Severity counts

- blocking: 0
- should-fix: 5 (F1-F5)
- note: 6 (F6-F11)

VERDICT: changes required

## Re-review (after fixes)

Re-ran the checks. `validate.py` reports `profile: valid`. `quote_check.py` checked 28 quotes with 0 failures.

- **F1: resolved.** The wrong `excluded` entry is gone. The new `notes[4]` matches the data: 11 stored keys (no VIE, VEA, hardness or Eigenvalue-degeneracy), and Table 1 gives the gap as 2.00 eV and the hardness as 2.73 eV. Deferring Al12Si because the Si+Al pseudopotential pair is untested is acceptable.
- **F2: resolved.** All four degeneracy claims carry a `definition_note` that names the notebook's 1e-4 Ha threshold and the paper's 10^-2 Ha criterion (§III.B).
- **F3: resolved.**
  - Both al13m1-vea and al13m1-hardness now carry the unbound-dianion and rmult caveat.
  - The new `si10-hardness` reference 2.939850016660852 eV equals the dataset value. The Table 1 cell (row Si10, Chemical Hardness = 2.94) is correct, and the bound anion (VEA +1.98 eV) is stated correctly.
  - `default_claims` is unchanged, which is correct.
- **F4: resolved.**
  - The al13m1-r1 pattern [1,1,2,2,1,2,1,2,1,2,1,1,2,1] and the al13m1-r3 pattern [1,1,2,1,2,1,2,1,2,2,1,2,1,1] equal the dataset values for ranks 1 and 3. They also equal Table 2 minima 2 and 4.
  - Leaving out the table cross-check is acceptable: the CSV rows have an empty Cluster cell. The `definition_note` records the Table 2 correspondence.
- **F5: resolved.**
  - The four new `excluded` entries are accurate. Fig. 8 and Fig. 16 cover saddles; Fig. 12 uses random displacements; the paper discusses the Al12X series at paper.md l.273 (Al12C, Ge, Sn, N+1, P+1, As+1, Sb+1).
  - Minor and not required: Al12Si belongs to that series but is in the dataset, so "..." slightly overstates "not in the record". Coordination numbers are not listed among the geometric descriptors.
- **F6: partially resolved, which is acceptable.** `ref:al13m1-degeneracy` was added. The energy-ordering and non-default claims are still unbound. This is a note only.
- **F7: resolved.** The value now reads "Si15 also has q = +3 (Table 1 and dataset)".
- **F8: resolved.** "Daubechies per the title of ref. 47".
- **F9: resolved** through the ordering claim's `definition_note` (ranks 4 and 5 are 36 meV apart).
- **F10: resolved.** The pymatgen tol=0.0009 is in `needs_template[0]`.
- **F11: resolved.** The `definition_note` states the 5e-9 Ha equivalence.

The changes introduce no new issues. Blocking: 0. Open should-fix: 0.

VERDICT: approve
