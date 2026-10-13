# Idea (parked): gold profiles and a calibration corpus for Paper2Profile

Status: parked 2026-10-09. Revisit once the Paper2Profile infrastructure exists.

## Why

Paper2Profile (paper → reproduction profile for `bigdft-cross-verify`) is LLM-driven. Its consistency can't be assumed; it has to be measured. Gold profiles are what we would measure it against.

## The idea

- **Template library first.** Draft the claim templates from BigDFT's capabilities and standard definitions, not from papers. That gives about 20–40 quantities: energies, eigenvalues and gaps, IE/EA, ordering, geometry, dipoles, and energy differences. Existing taxonomies of computed quantities, such as NOMAD metainfo, are worth checking as a starting vocabulary.
- **Calibration corpus.** Collect about 15–25 papers chosen for variety rather than volume:
  - source code: same code (BigDFT), plane-wave (VASP, QE), localized basis (Gaussian, ORCA), CP2K;
  - system: molecules and clusters, charged species, bulk, surfaces;
  - quantity type;
  - data availability: SI or archive, tables only, none;
  - how completely the settings are stated.
- **Gold profiles.** A hand-reviewed profile per corpus paper. Fisicaro et al. 2023 is the first candidate: `inorganic-small-clusters/dist/small_cluster_isomers-agent/reproduction/bigdft-profile.json`.
- **Uses of the corpus:**
  - Coverage: how many claims map to a template, and which are out of BigDFT's scope and go to excluded.
  - Wording variants: synonyms and definition variants that templates must recognise.
  - Regression tests for every change to the generator, templates or schema. Metrics: claim recall, citation-check pass rate, agreement between two independent generations, field-level match with the gold profile.
- **After launch.** The "needs template" queue from real users drives growth. Each new template is reviewed once, and the paper that prompted it joins the corpus.

## Main cost

Writing the gold profiles: they encode the expert judgment the pipeline is measured against.
