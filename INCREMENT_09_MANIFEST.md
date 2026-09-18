# Increment 9 manifest — Dynamic Elastic Properties and QC

Project: Poseidon 2 1D MEM. Tier C: screening-level, uncalibrated, educational.
Package version: **0.9.0**. Increment 10 has not been started.

## Foundation and scope

The cumulative package starts from `Poseidon_1D_MEM_Increment_08_v8.0.1.zip`,
independently verified as SHA-256
`ad6ef2ece0937203baee582e9be67950a8b4ca78176bdd21ac7e187d1d63bd7c`.
All 263 baseline files remain present. Only README.md, pyproject.toml and
p2mem/__init__.py change; all prior implementations, tests, configs, notebooks,
records and scientific outputs remain byte-identical. Baseline tests were
re-run before implementation: **1,632 passed**.

This increment calculates dynamic isotropic elastic estimates at original LAS
sample positions. It adds no static conversion, strength correlation, NCT,
pore-pressure prediction, horizontal stress or wellbore-stability calculation.
It does not rerun or reinterpret upstream stress scenarios.

## Methods and units

The approved per-file contracts convert DTCO/DTSM from us/ft to m/s using the
locked conversion and RHOB from g/cc to kg/m3. Most raw curve mnemonics are
empty: the exact contract ordinal is retained instead of inventing a mnemonic.

For isotropic linear elasticity, with r = Vp/Vs:

- G = rho Vs².
- K = rho (Vp² − 4 Vs²/3).
- ν = (r² − 2) / [2(r² − 1)].
- E = 9KG / (3K + G) = 2G(1 + ν).

Moduli are computed in SI and exported in GPa; ν is dimensionless.
The wave-speed relations are documented in
[MIT Introduction to Seismology, p. 2](https://ocw.mit.edu/courses/12-510-introduction-to-seismology-spring-2010/d77d74b5471755994a9dae8a19eddba0_lec1.pdf).
The E/G/ν and bulk-modulus identities are documented in
[MIT Structural Mechanics, Note L.4, sections 2.1–2.2](https://ocw.mit.edu/courses/22-314j-structural-mechanics-in-nuclear-power-technology-fall-2006/137e6469e37e9d347b7b3b69292da2f3_l4_2.pdf).
Combining those relations gives the implemented inversion. These constitutive
identities are not empirical calibrations for the supplied logs.

## Coverage and policy

All primary properties require mapped depth. Curve screening bounds remain
Vp 1000–8000 m/s, Vs 300–5000 m/s and RHOB 1000–3500 kg/m3, inclusive.

- Primary ν requires Vp/Vs within the inherited inclusive sqrt(2)–4 policy.
  Density is not required.
- G requires Vs and density. A G estimate alone does not establish that the
  complete Vp/Vs pair supports a stable isotropic model.
- Primary K and E additionally require density. Their mask is compared
  sample-by-sample to the locked Increment 6 full dynamic-elastic mask.
- sqrt(4/3) < r < sqrt(2) is stable-negative-ν diagnostic territory; these
  samples retain `nu_stable_diagnostic` while primary ν/K/E remain withheld.
- r <= sqrt(4/3) implies non-positive bulk modulus within the assumed model.
  r > 4 is a separate plausibility-policy exclusion, not a physical boundary.

No missing interval is interpolated, bridged, clipped, resampled or filled.
Every output profile retains original sample index, MD, TVD and TVDSS.
Boreas 1 is evaluated from its velocity/density evidence independently of GR.
The inherited source-trace depth basis remains explicit in the provenance.

## Independently regenerated real-data results

| Well | Original samples | ν | G | K/E | Median E (GPa) |
|---|---:|---:|---:|---:|---:|
| Boreas 1 | 32,845 | 2,713 | 2,602 | 2,565 | 51.237880 |
| Poseidon 2 | 31,897 | 4,125 | 3,877 | 3,855 | 44.673950 |
| Poseidon North 1 | 31,310 | 9,465 | 7,395 | 7,388 | 17.612664 |
| Proteus 1ST2 | 31,235 | 979 | 956 | 953 | 46.377650 |

Every well is fully depth-mapped; no sample is extrapolated. Counts cover the
whole original LAS population, not only the plotted depth window. Statistics
are unweighted percentiles of each property's own valid samples, not depth-
weighted averages; medians of different properties need not satisfy identities
that hold sample-by-sample. Figures zoom to the available elastic interval.

Ratio diagnostics use samples with both velocities inside their individual
screening bounds, independently of density:

- Boreas 1: 0 non-positive-K ratios; 1 stable negative-ν ratios.
- Poseidon 2: 0 non-positive-K ratios; 22 stable negative-ν ratios.
- Poseidon North 1: 4 non-positive-K ratios; 3 stable negative-ν ratios.
- Proteus 1ST2: 0 non-positive-K ratios; 3 stable negative-ν ratios.

## Assumptions and limitations

The isotropic, linear, dynamic interpretation is assumed. Input measurement
uncertainty, borehole/tool-quality effects, anisotropy and frequency/strain
dependence are unquantified. The available input set supplies no dynamic-to-
static calibration; no static property is inferred. Finite density inside a
broad screen does not prove a measurement correct. Sparse Vs/RHOB coverage
remains visible, and well-wide estimates are not extrapolated from it.

`K_velocity_condition_number = (2r² + 8/3)/(r² − 4/3)` is derived by summing
absolute logarithmic partial derivatives of K with respect to Vp and Vs, at
fixed density. It expresses first-order worst-case sensitivity to equal
fractional perturbations. It supplies no perturbation magnitude, probability
distribution, calibrated error bar or confidence interval. No arbitrary
measurement-uncertainty percentage is introduced.

## Data products and provenance

Four profile CSVs, one summary CSV, one manifest JSON and four QC PNGs are
published under `outputs/09_dynamic_elasticity/`. The JSON identifies the
actual source basenames and hashes, curve conversions, depth datum, config
hashes, per-well counts and statistics, and hashes of the other nine artifacts.
The manifest cannot contain its own checksum; the release ledger covers it.
No raw LAS or deviation survey is packaged.

Generated scientific tables have exact schemas and no arbitrary interpretation
or lithology-classification fields. Serialized records are validated for
coverage, missingness, finite numbers, boolean values, index order, ratio
regimes, elastic identities, summaries and provenance structure. This is a
defined output contract, not a natural-language geology detector.

All ten artifacts are staged and validated before directory publication.
Publication uses an exclusive writer lock and rollback if the swap fails.
The workflow refuses to overwrite an unrelated output folder. As with ordinary
filesystem publication, sudden process termination or storage failure is not
a universal durability guarantee. The Colab workflow publishes on local
runtime storage and saves a separate results ZIP to Drive.

## Notebook execution and validation

The notebook contains 15 cells, including 7 code cells, with unique IDs and
zero saved outputs. It writes no implementation via `%%writefile`. Default
review mode validates the packaged results; optional regeneration requires the
private inputs and compares regenerated CSVs and scientific JSON with the
packaged results. PNG bytes may vary with Matplotlib; figure hashes are checked
for each individual bundle and compared separately between environments.

The runner selects its package root explicitly, checks the release and baseline
ledgers, and runs pytest in a disposable copy with local fixture paths. Some
locked integration tests regenerate prior QC figures; isolation lets those
tests run unchanged while preserving the reviewed package byte-for-byte. It
parses the XML test report and rejects failures, errors and skipped tests.
The original 1,632 tests remain unchanged; newly added test counts and final
clean-room observations are reported in the external completion record.

Review mode does not claim that private sources were re-read. A local Linux
notebook execution does not claim a hosted Google Colab execution. Read the
completion record for the exact verified environment and results.

## Exact file delta

Changed (3):

- `README.md`
- `p2mem/__init__.py`
- `pyproject.toml`

Added (20):

- `09_Dynamic_Elastic_Properties_and_QC.ipynb`
- `INCREMENT_09_MANIFEST.md`
- `INCREMENT_09_QUICKSTART.md`
- `INCREMENT_09_SHA256SUMS.txt`
- `config/dynamic_elasticity.json`
- `outputs/09_dynamic_elasticity/Boreas_1_elastic.csv`
- `outputs/09_dynamic_elasticity/Boreas_1_elastic_qc.png`
- `outputs/09_dynamic_elasticity/Poseidon_2_elastic.csv`
- `outputs/09_dynamic_elasticity/Poseidon_2_elastic_qc.png`
- `outputs/09_dynamic_elasticity/Poseidon_North_1_elastic.csv`
- `outputs/09_dynamic_elasticity/Poseidon_North_1_elastic_qc.png`
- `outputs/09_dynamic_elasticity/Proteus_1ST2_elastic.csv`
- `outputs/09_dynamic_elasticity/Proteus_1ST2_elastic_qc.png`
- `outputs/09_dynamic_elasticity/elastic_manifest.json`
- `outputs/09_dynamic_elasticity/elastic_summary.csv`
- `p2mem/dynamic_elasticity.py`
- `p2mem/io/elastic_workflow.py`
- `scripts/run_increment_09.py`
- `tests/test_dynamic_elasticity.py`
- `tests/test_elastic_workflow.py`

Removed: 0. Total package files: 283.
The separately delivered completion record is external to the ZIP so it can
record the final archive hash without a circular checksum dependency.
