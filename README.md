# Bridge-P2A-BigDFT

A Claude Code plugin marketplace that bridges agents built with [Paper2Agent](https://github.com/jmiao24/Paper2Agent) (P2A) to [BigDFT](https://bigdft.org), so a paper's reported calculations can be re-run and checked.

| Plugin | Status |
|---|---|
| [`bigdft-cross-verify`](plugins/bigdft-cross-verify/README.md) | **v2 prototype**, for one paper: Fisicaro et al., Mater. Adv. 2023 |

```
/plugin marketplace add TengxiangLii/Bridge-P2A-BigDFT
/plugin install bigdft-cross-verify@bridge-p2a-bigdft
```

## Design

- [`docs/paper2profile-infra.md`](docs/paper2profile-infra.md): the design this prototype implements. It separates paper facts, engine mapping, agent bindings and machine; the LLM proposes and a script gates; plans are byte-identical; a registry holds reviewed profiles.
- [`docs/paper2profile-gold-profiles.md`](docs/paper2profile-gold-profiles.md): a parked idea, a calibration corpus.

## History

v1 (a single free-text skill plus a hand-written profile) is kept in git history at commit `54a53f9`. It was replaced because its profiles were not reproducible across researchers or P2A agents.

## License

The code and docs are MIT ([LICENSE](LICENSE)). The registry entries quote short excerpts of CC BY 4.0 papers and data records, with attribution. The pseudopotential parameter files come from PyBigDFT's database; their sources are recorded in each `bigdft-mapping.json`.
