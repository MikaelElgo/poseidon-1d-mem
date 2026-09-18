# Poseidon 1D MEM

Independent 1D Mechanical Earth Model pipeline — LAS ingestion through wellbore-stability screening, built increment by increment with locked contracts and full test coverage.

**Author:** Mikael Elgo · **Classification:** Tier C — Screening-Level / Uncalibrated (Educational) · **License:** MIT · **Current release:** Increment 12 (v12.0.0)

---

> **This project is screening-level, uncalibrated, and educational in nature. It is NOT validated against independent field measurements (no confirmed RFT/MDT pressure points, LOT/XLOT tests, or core-calibrated log ties are currently incorporated), and it must NOT be used for operational drilling, well-design, or any real-world decision-making. It exists to demonstrate a technically defensible, transparent, modular geomechanics workflow — not to produce field-ready predictions.**

---

## Purpose and technical scope

This repository implements a modular, reproducible 1D Mechanical Earth Model workflow for the Poseidon 2 well, built from well logs, deviation surveys, checkshot data, formation tops, and Vp/Vs data supplied for the project. The intended end-to-end scope (delivered incrementally, one validated phase at a time) covers:

- data quality control and depth alignment across LAS logs, deviation surveys, and checkshot data
- pore-pressure prediction (Eaton-family methods, contingent on a defensible normal compaction trend)
- elastic properties (dynamic Vp/Vs-derived Poisson's ratio, and density-dependent moduli where density coverage permits)
- rock-strength estimation
- vertical-stress (overburden) modelling
- horizontal-stress and wellbore-stability screening (Kirsch elastic wall-stress equations with Mohr–Coulomb/Mogi–Coulomb failure criteria)
- uncertainty treatment via deterministic low/base/high scenarios and one-at-a-time sensitivity (tornado) analysis, rather than unsupported probabilistic distributions

Every empirical or correlation-based relationship used anywhere in this project (Eaton, Bowers, Gardner, Castagna, etc.) is required to have a recorded source, stated units, applicability range, and calibration status in the project's method-and-citation register *before* it is implemented in code. Nothing is fabricated or assumed silently: missing measurements, missing calibration points, and unavailable data are always reported as unavailable rather than filled in.

This is a personal portfolio project intended to demonstrate scientific rigor, reproducibility, and honest handling of data limitations — not a commercial or operational deliverable.

## Current status

Start with **12_Wellbore_Stability_Envelopes.ipynb** or **INCREMENT_12_QUICKSTART.md**.

This cumulative release adds full wall-stress tensors, Mohr–Coulomb/tensile pressure intervals, hypothetical relative-orientation experiments and independent numerical checks. The scientific report documents the sealed-wall alpha=1 convention and all inherited analogue limitations. Field eligibility remains false.

Use `python scripts/run_increment_12.py --mode review` (or `reproduce`) for the version-scoped verification workflow. Earlier release instructions are retained as historical documentation in [`CHANGELOG.md`](CHANGELOG.md).

Development runs one gated increment at a time; each increment's own quickstart, scientific report, and manifest are kept at the repo root (`INCREMENT_12_QUICKSTART.md`, `INCREMENT_12_SCIENTIFIC_REPORT.md`, etc.). The complete increment-by-increment history — everything from Increment 1 through the current release, including every corrective patch and independently audited finding — is preserved in [`CHANGELOG.md`](CHANGELOG.md).

## Installation

Requires Python 3.9 or later.

```bash
# from the project root (the directory containing pyproject.toml)
pip install -e .
```

This installs the `p2mem` package in editable mode along with its runtime dependencies: NumPy (`numpy>=1.24`) and, as of Increment 2, PyYAML (`pyyaml>=6.0`) — used for parsing the human-authored curve contracts in `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml` (Increment 3), `config/checkshot_contracts.yml` (Increment 4), and (new in Increment 5) `config/formation_top_contracts.yml`. No new runtime dependency was added in Increment 3, 4, or 5: the minimum-curvature engine, depth-mapping interpolation, duplicate-tie conditioning, velocity diagnostics, time-depth interpolation, and formation-top reconciliation/mapping all use only NumPy (including a local, version-independent trapezoidal-integration helper in `p2mem/time_depth.py`, added because `numpy.trapz`/`numpy.trapezoid` are not consistently available across supported NumPy versions). Matplotlib and pandas are used only for notebook display and QC-figure generation (`run_integration_03.py`/`run_integration_04.py`/`run_integration_05.py`, the Increment 3/4/5 notebooks) — never imported by the installable `p2mem` package itself. To also install the test dependency:

```bash
pip install -e ".[dev]"
```

## Running the tests

```bash
pytest -v
```

None of the test suites require the private/raw project LAS, deviation, checkshot, or formation-top files, so the full suite runs the same way for anyone who clones this repository. This document does not assert a fixed expected test count — read that from the actual `pytest` output for the code currently on disk. Real integration validation (which DOES require the raw project data files, not included in this repository) is run separately, notebook by notebook. Per-suite descriptions of what each test file validates are kept in [`CHANGELOG.md`](CHANGELOG.md).

## Directory structure

```
Poseidon_1D_MEM/
├── README.md
├── pyproject.toml
├── p2mem/
│   ├── __init__.py
│   ├── models.py
│   ├── units.py
│   ├── deviation_models.py
│   ├── trajectory.py
│   ├── depth_mapping.py
│   ├── checkshot_models.py
│   ├── time_depth.py
│   ├── top_models.py
│   ├── wellframe_models.py
│   ├── wellframe.py
│   ├── petrophysics_models.py
│   ├── petrophysics.py
│   ├── method_eligibility.py
│   ├── overburden_models.py        (Increment 7)
│   ├── density_qc.py               (Increment 7)
│   ├── overburden.py               (Increment 7)
│   ├── pore_pressure_models.py      (Increment 8)
│   ├── pore_pressure.py             (Increment 8)
│   └── io/
│       ├── __init__.py
│       ├── las.py
│       ├── inventory.py
│       ├── deviation.py
│       ├── deviation_inventory.py
│       ├── checkshot.py
│       ├── checkshot_inventory.py
│       ├── tops.py
│       ├── tops_inventory.py
│       ├── output_policy.py
│       ├── petrophysics_inventory.py
│       ├── overburden_policy.py    (Increment 7)
│       ├── overburden_registry.py  (Increment 7)
│       ├── overburden_inventory.py (Increment 7)
│       ├── overburden_workflow.py  (Increment 7)
│       ├── pore_pressure_inventory.py (Increment 8)
│       └── pore_pressure_workflow.py  (Increment 8)
├── tests/
│   ├── test_units.py
│   ├── test_las.py
│   ├── test_trajectory.py
│   ├── test_deviation.py
│   ├── test_depth_mapping.py
│   ├── test_deviation_inventory.py
│   ├── test_checkshot.py
│   ├── test_time_depth.py
│   ├── test_checkshot_inventory.py
│   ├── test_tops.py
│   ├── test_tops_inventory.py
│   ├── test_wellframe.py
│   ├── test_petrophysics.py
│   ├── test_method_eligibility.py
│   ├── synthetic_inc6.py
│   ├── synthetic_inc7.py           (Increment 7; fictional in-memory frames only)
│   ├── helpers_inc7.py             (Increment 7)
│   ├── test_density_qc.py          (Increment 7)
│   ├── test_overburden.py          (Increment 7)
│   ├── test_overburden_policy.py   (Increment 7)
│   ├── test_overburden_inventory.py (Increment 7)
│   ├── synthetic_inc8.py           (Increment 8; fictional only)
│   ├── test_pore_pressure.py       (Increment 8)
│   ├── test_pore_pressure_inventory.py (Increment 8)
│   ├── test_pore_pressure_workflow.py (Increment 8)
│   └── fixtures/         (small synthetic LAS + deviation-survey + checkshot + formation-top files; no project raw data)
├── config/
│   ├── las_curve_contracts.yml
│   ├── deviation_survey_contracts.yml
│   ├── checkshot_contracts.yml
│   ├── formation_top_contracts.yml
│   ├── petrophysics_eligibility.yml
│   ├── overburden_stress.yml       (Increment 7)
│   └── pore_pressure.yml           (Increment 8)
├── data/
│   └── raw/
│       ├── logs/         (the four raw LAS files - NOT included in this repository; immutable inputs)
│       ├── deviation/    (the four raw deviation-survey files, exact filenames contain spaces, e.g. "Poseidon 2_dev.txt" - NOT included in this repository; immutable inputs)
│       ├── checkshot/    (the three raw checkshot files, exact filenames e.g. "Poseidon2-Checkshot.txt" - NOT included in this repository; immutable inputs, never rewritten/renamed/"cleaned")
│       └── tops/         (the four raw formation-top files, e.g. "Poseidon_2_HRS_tops_no_wellname_MDRT.txt" - NOT included in this repository; immutable inputs)
├── notebooks/  (reserved for later increments)
└── outputs/
    ├── 02_las_inventory/            (Increment 2.1.1 real four-well run: CSV/JSON metadata only, no raw log samples)
    ├── 03_deviation_depth/          (Increment 3 real four-well run: CSV/JSON metadata + QC figures, no raw station/log samples)
    ├── 04_checkshot_time_depth/     (Increment 4 real three-file checkshot run: CSV/JSON metadata + QC figures, no raw per-sample checkshot/LAS arrays)
    ├── 05_formation_tops/           (Increment 5 real four-file formation-top run: CSV/JSON metadata + QC figures, no raw per-marker arrays beyond scalar fields)
    ├── 06_petrophysics_eligibility/ (Increment 6 real four-well run: CSV/JSON metadata + QC figures, no raw per-sample arrays)
    ├── 07_density_overburden/       (Increment 7 real four-well run: 9 closed-schema CSV/JSON artifacts + 4 QC figures; the stress profile is a DECIMATED selection of existing samples, never a raw log dump)
    └── 08_pore_pressure_effective_stress/ (Increment 8: 7 CSV/JSON artifacts + 4 figures, derived only from packaged locked outputs)
```

`notebooks/` is created empty by the project-setup notebook cell and is not yet populated in-repo (the increment notebooks themselves are delivered as top-level files, e.g. `02_LAS_Ingestion_and_Curve_Contracts.ipynb`, `03_Deviation_Survey_and_Depth_Framework.ipynb`, `04_Checkshot_QC_and_Time_Depth_Framework.ipynb`, `05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb`, `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`, `07_Density_QC_and_Overburden_Stress_Framework.ipynb`, and are meant to be run from Google Drive per their own directory-setup cells; the Increment 7 notebook additionally runs unchanged from any working directory that is itself the project root).


## Scientific limitations

These limitations are specific to the Poseidon 2 dataset and this project's current increment, and are carried forward here so they are visible outside the conversation in which they were identified:

- **RHOB (bulk density) coverage in Poseidon 2 ends at approximately 5,296.85 m MD.** Sonic and other curves continue deeper, so Vp/Vs and dynamic Poisson's ratio remain computable below that depth, but density-dependent properties (Young's modulus, shear modulus, bulk modulus, acoustic impedance, shear impedance) are unavailable below it unless density is explicitly estimated and flagged as such — never silently substituted.
- **No reliable shale-based normal compaction trend (NCT) exists from Poseidon 2 alone.** A provisional, transferred candidate NCT identified in offset well Poseidon North 1 is a *candidate*, not a validated trend, and must not be presented as calibrated.
- **Independently measured Vp/Vs quality flags:** approximately 3.38% of Poseidon 2 Vp/Vs values fall below 1.5, and approximately 0.53% fall below the physical validity cutoff of √2 (≈1.4142) required for a non-negative dynamic Poisson's ratio.
- **No independent calibration data (RFT/MDT pressure points, LOT/XLOT tests, or core data) has been supplied or incorporated.** Any pore-pressure or stress output in later increments must be presented as a bounded or theoretical estimate, not a validated field prediction.
- **Empirical/correlation equations are not implemented until their governing equation, units, applicability range, and calibration status are recorded in the project's method-and-citation register.** Several candidate methods remain in "pending" status and are intentionally absent from the codebase for that reason, not because they were overlooked.
- Additional open items (offset-well GR/ECGR scale adjudication, missing formation tops for one offset well) are tracked in the project's design-review documentation and gate specific later phases (lithology and pore-pressure), not this increment.

These are the limitations current as of the latest release. The full per-increment log of audits, corrections, and disclosed real-data findings that produced this list is kept in [`CHANGELOG.md`](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

## Author

Mikael Elgo — [mikaelelgo.github.io](https://mikaelelgo.github.io) · [github.com/MikaelElgo](https://github.com/MikaelElgo)

---

## Screening-level statement

**This 1D Mechanical Earth Model is a screening-level, uncalibrated, educational work product.** It has not been validated against independent field measurements and does not carry the assurance level required for drilling engineering, well design, casing/mud-weight selection, or any other operational decision. Any numerical result produced by this codebase should be read as illustrative of a defensible methodology applied to the available data, not as a certified or field-ready prediction.

