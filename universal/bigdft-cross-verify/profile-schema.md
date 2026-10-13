# Reproduction profile schema (`bigdft-cross-verify/profile/1`)

A profile is one JSON file that holds everything paper-specific. Every fact in it must cite where in the paper, supplement or dataset it came from. A value the source does not state goes in `unknown_settings`; never fill it with a guess. `validate_profile.py` checks the structure. A human, or an independent reviewer agent, checks the content against the paper.

```json
{
  "schema": "bigdft-cross-verify/profile/1",
  "id": "short-kebab-id",
  "paper": {"title": "... or null", "doi": "... or null", "paper_skill": "optional installed paper skill name"},
  "tier": "same_code | cross_code",
  "source_method": {
    "code": "BigDFT | VASP | ...", "version": "string or null",
    "settings": [
      {"name": "xc_functional", "value": "PBE", "source": "paper §II"}
    ]
  },
  "unknown_settings": [
    {"name": "grid_spacing", "affects": ["claim-id", "..."], "source": "not stated in paper §II or ESI"}
  ],
  "structures": {
    "provider": "mcp_tool | files | inline",
    "details": "how to obtain each structure (tool name + arguments pattern, or paths)",
    "units": "Angstrom | Bohr | per-file rule",
    "notes": "format quirks (extra blocks, headers)"
  },
  "electronic_state_rules": {
    "charge": "rule for mapping a system label to its net charge",
    "spin": "rule (e.g. spin-polarized with minimal moment when the electron count is odd)",
    "smearing": "rule or 'none'",
    "source": "paper §..."
  },
  "reference_data": {"provider": "mcp_tool | table | text", "details": "where the reference values are read"},
  "claims": [
    {
      "id": "kebab-id",
      "statement": "claim as the paper states it",
      "source": "Table 1 / Fig. 7 / §III.B / dataset key",
      "type": "numeric | categorical | ordering",
      "tolerance_class": "categorical (categorical claims) | relative_energy (ordering claims) | relative_energy | absolute_energy | orbital_gap | ionization_affinity | bond_length (numeric claims)",
      "systems": ["system labels or structure ids"],
      "computation": "exact definition to recompute (runs needed, formula, geometry fixed or relaxed)",
      "reference": "reference value, or how to fetch it",
      "qualitative_property": "for numeric claims: what reproduced_trend means (optional)"
    }
  ],
  "default_claims": ["claim ids run when the user gives no subset"],
  "tolerance_overrides": [{"class": "orbital_gap", "value": 0.05, "reason": "..."}],
  "excluded_claims": [{"statement": "...", "reason": "why it cannot be re-verified with BigDFT"}],
  "known_notes": ["notation or dataset caveats a verifier would otherwise misread"]
}
```

## Rules

- **`tier`:** `same_code` only when the source code is BigDFT. Otherwise use `cross_code`.
- **`source` fields** cite the most specific location available: a table, figure, section or dataset key. For a source without numbered sections, quote a short phrase ("Methods paragraph: 'relaxed until forces < 0.01 eV/Å'").
- **`unknown_settings`** holds settings the source does not state. A setting the source states but that has no BigDFT counterpart (a plane-wave cutoff, PAW) goes in `source_method.settings`; the settings map then marks it `not_mappable`.
- **Geometry:** each claim's `computation` names its geometry, either "source geometry" or "BigDFT-relaxed from the source geometry".
- **`qualitative_property`:** without one, a numeric claim cannot be `reproduced_trend`. Ordering claims have an implicit one: the order is preserved.
- **`computation` must be executable as written.** For example: "vertical IE = E(m−1 electrons) − E(m electrons), both at the relaxed m-electron geometry", not "compute the IE". If the paper does not define a quantity, write the definition you use and set the claim's `qualitative_property`, or move the claim to `excluded_claims` with the reason.
- **Parameterized claims:** a claim can apply to several systems through `systems`. `default_claims` should be a small set that runs quickly.
- **What stays out of a profile:**
  - compute-resource details, which belong to the run;
  - results;
  - BigDFT input syntax, which comes from `bigdft:input` at run time.
