# Increment 7.0.3 Manifest — Closed P05 Scenario-Percentile Contract

## 1. Identity and scope

- **Project:** Poseidon 2 — 1D Mechanical Earth Model
- **Package version:** `p2mem 0.7.3`
- **Direct baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.2.zip`
- **Verified baseline SHA-256:** `3f18d6bd7266f1ca3e0b3ccf0810a776bb76547b04e4c6e627bae9a6748be949`
- **Patch scope:** one configuration-to-computation provenance correction
- **Configuration schema:** remains `7.0.1`; no YAML key or packaged value changes
- **Increment 8:** not started

This is a narrow assurance patch. It changes no private input, density value, mapping,
mask, gap disposition, threshold, equation, eligibility status, stress result,
scientific CSV/JSON artifact, or figure.

## 2. Reproduced finding

Increment 7 stores the measured fifth-percentile density as
`DensityQcStats.rhob_p05_kg_m3`, and the high shallow-column scenario consumes that exact
field. The public configuration nevertheless accepted any finite
`scenario_high_percentile` strictly between 0 and 100. Against a synthetic density ramp,
configurations labelled 5, 50, and 95 therefore all published the same high-scenario
density of 1575 kg/m3, even though the independently calculated P05, P50, and P95 values
were 1575, 2250, and 2925 kg/m3. The numerical calculation remained P05; only the
configurable provenance label was false.

The shipped project configuration already declares `high_percentile: 5.0`, so no
approved real-data result was numerically wrong. The defect was latent: a user could
select another advertised value and receive a result still computed from P05 but labelled
as that other percentile.

## 3. Correction

The Increment 7 statistic and scenario remain deliberately P05-specific. Both public
configuration entry points now require `scenario_high_percentile == 5.0` exactly:

1. `load_overburden_config()` rejects a YAML value other than 5.0 with a typed
   `OverburdenConfigError` that states the P05 reason.
2. `OverburdenConfig.__post_init__()` applies the same rule to direct construction and
   `dataclasses.replace()`.

This closes the contract without pretending the existing data model is a generic
percentile engine. Values 0.1, 4.999, 50.0, 95.0, and 99.9 are regression-tested through
both entry points. The valid packaged value 5.0 remains accepted.

## 4. Files changed relative to Increment 7.0.2

Exactly **8 existing files changed**:

1. `07_Density_QC_and_Overburden_Stress_Framework.ipynb`
2. `README.md`
3. `p2mem/__init__.py`
4. `p2mem/density_qc.py`
5. `p2mem/overburden_models.py`
6. `pyproject.toml`
7. `tests/test_density_qc.py`
8. `tests/test_overburden_policy.py`

Exactly **3 files were added**:

1. `INCREMENT_07_0_3_MANIFEST.md`
2. `INCREMENT_07_0_3_COMPLETION_RECORD.md`
3. `INCREMENT_07_0_3_SHA256SUMS.txt`

No file was removed. `tests/test_overburden_policy.py` changes only its literal notebook
release-title lookup from 7.0.2 to 7.0.3; its scientific and schema assertions are
unchanged. Every other direct-baseline file is byte-identical.

## 5. Tests and notebook

- Direct baseline suite: **1,306 passed**.
- Final combined suite: **1,316 collected / 1,316 passed**.
- Locked pre-Increment-7 subset: **944 passed**; all 14 locked test files remain
  byte-identical to the locked Increment 6.1.7 versions.
- Increment 7 subset: **372 passed**.
- New cases: **10**, covering five invalid percentile values through each of the two
  public entry points.
- Notebook: **86 cells**, 86 unique IDs, zero saved outputs,
  `nbformat.validate()` passes, and **17/17 `%%writefile` bodies** are byte-identical to
  their packaged targets.
- Completion gate: **39 declared checks**. Its existing public-constructor check now also
  probes and rejects `scenario_high_percentile=50.0`.

The private LAS, deviation, checkshot, and formation-top source files are intentionally
not packaged and were unavailable in this environment. A full real-data notebook or
Google Colab execution is therefore not claimed. The changed modules and gate condition
are covered directly by the complete test suite, notebook-source parity, and clean-room
probes.

## 6. Scientific-output non-regression

All **13/13 files** under `outputs/07_density_overburden/` are byte-identical to the
verified Increment 7.0.2 baseline, including nine CSV/JSON artifacts and four figures.
All measured findings, scenario values, statuses, uncertainties, and limitations are
therefore unchanged. In particular:

- no approved well supports an absolute overburden curve;
- measured increments remain 19.9325 MPa (Boreas 1), 30.6159 MPa (Poseidon 2),
  28.3422 MPa (Poseidon North 1), and 8.2718 MPa (Proteus 1ST2);
- Boreas 1's unresolved 15.64 m gap still truncates the column and excludes 2,511 deeper
  eligible samples;
- the 10 m bridge threshold remains a screening heuristic;
- shallow-column values remain conditional or illustrative scenarios, not calibrated
  results or physical bounds.

## 7. Clean-room and packaging checks

The final ZIP was extracted into a new empty directory and checked for safe relative
paths, duplicate names, symlinks, checksum consistency, package version, full and
partitioned test runs, notebook validity, unique IDs, saved-output absence,
`%%writefile` parity, the P05 gate probe, exact baseline delta, locked-test identity,
scientific-output identity, absolute build-path leakage, private-input exclusion, and
absence of any Increment 8 implementation. The checksum ledger covers every packaged
file except itself.

## 8. Stop condition

Increment 7.0.3 stops here. No pore-pressure/NCT, effective-stress, elastic-property,
rock-strength, horizontal-stress, mud-window, or wellbore-stability implementation was
started. **Increment 8 has not been started.**
