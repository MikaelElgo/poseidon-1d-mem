# Increment 8.0.1 Manifest — Final Corrective Release of the Pore-Pressure Data-Gap, Hydrostatic-Reference, and Effective-Stress Screening Framework

## 1. Identity and scope

- **Project:** Poseidon 2 — 1D Mechanical Earth Model
- **Package version:** `p2mem 0.8.1`
- **Config schema:** `8.0.1`
- **Direct scientific baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.4.zip`
- **Verified baseline SHA-256:** `f5c9a9b50dd0edff6e5b31a42d5bba4ab23b993f5ef11c6217122b13f29d89ae`
- **Corrected predecessor:** `Poseidon_1D_MEM_Increment_08.zip`, SHA-256 `68190661c521ec36c4f7e4c73030ab5a86b22ce3dd8abe6c7588d60634fa8b76`
- **Assurance:** Tier C — Screening-Level / Uncalibrated Educational
- **Increment 9:** not started

Increment 8.0.1 is a corrective release of Increment 8. It does not add a pore-pressure prediction method. It preserves the same scientific scope: approved-input data-gap inventory, configured hydrostatic references, NCT-candidate readiness sensitivity, and vertical effective-stress scenarios where Increment 7 supplies a shallow-column total-stress scenario.

No NCT is selected or fitted. No Eaton, Bowers, equivalent-depth, drilling-exponent, or other overpressure transform is implemented or run. No overpressure is inferred. No field measurement is invented or transferred between wells. No source curve is corrected, filled, clipped, or extrapolated.

The original `INCREMENT_08_MANIFEST.md`, `INCREMENT_08_COMPLETION_RECORD.md`, and `INCREMENT_08_SHA256SUMS.txt` remain packaged as historical records. They do **not** verify this corrective tree. This manifest and `INCREMENT_08_0_1_SHA256SUMS.txt` supersede them for the current release.

## 2. Corrective findings and dispositions

### 2.1 Upstream “locked” inputs were not cryptographically closed

Increment 8 recorded the seven source hashes but accepted any syntactically valid 64-character lowercase digest. A semantically plausible modified upstream artifact could therefore pass the workflow while being described as locked.

Increment 8.0.1 embeds the exact approved hash registry and requires equality for all seven artifacts before any output can be published:

| Source artifact | Required SHA-256 |
|---|---|
| `vertical_stress_profile.csv` | `bfe2bd37d31793285f06db34fda6e3e715dd8f085a6685620bca08167941ad52` |
| `shallow_column_scenarios.csv` | `356a5e83bca131ed1046c83d0c27d5624bafe8b2510cdff8a500871514aca7a8` |
| `overburden_eligibility_summary.csv` | `8bd03850d1ea8a58b620810f65af18c1d4115b3cd385c542949d7ba22e45cf12` |
| `method_eligibility_summary.csv` | `7fa715459de2eaa2007cdffe1af30a9c3eb424c78650f618ba34738d9a5c64b9` |
| `thickness_sensitivity_summary.csv` | `0c953df792a474960760e4bc491a05e2ffa448a8909589accadc14c78f2aec3e` |
| `petrophysics_eligibility_manifest.json` | `00e05aaa35454aef62bb7541adfbccca5a348ff8ccb2ecbc26b9a8093877a58e` |
| `sonic_checkshot_drift_summary.csv` | `17c84fcf9c9c320d9de665023d5d19ab6c5112bdf0d408378a289c9250886874` |

Each artifact is perturbed independently in regression tests; every altered copy is rejected with no output directory created.

### 2.2 Configuration was broader than the release policy

The previous constructor checked ranges and ordering, while the exported manifest required one exact release configuration. The constructor now closes the same values it claims:

- gravity `9.80665 m/s²`;
- fluid densities `1020.0 / 1025.0 / 1030.0 kg/m³`;
- Biot-alpha sensitivities `0.8 / 1.0`;
- profile reference `alpha = 1.0`, `rho_f = 1025.0 kg/m³`;
- config schema `8.0.1`.

Duplicate YAML keys at any nesting depth are rejected instead of silently overwriting an earlier value. Unknown or missing keys were already rejected and remain so.

### 2.3 Cross-artifact identities were incomplete

The workflow now additionally requires:

- each Increment 7 shallow-scenario total to equal water-column + unresolved-shallow + measured + bridged stress;
- the complete five-row shallow-scenario inventory for each scenario-supported well and no shallow rows for unsupported wells;
- each vertical-stress cumulative profile to start at zero and be non-decreasing;
- strict canonical CSV integer/numeric tokens;
- sonic/checkshot milliseconds, reversed milliseconds, and percent to reproduce independently from the two transit times;
- exact per-well node counts and contiguous node indices for all three hydrostatic scenarios;
- exact effective-stress scenario cross-products and profile node/scenario coverage;
- identical hydrostatic nodes across fluid scenarios;
- effective-profile pressure to equal the base hydrostatic profile;
- terminal profile total stress to equal its corresponding terminal scenario;
- NCT-readiness JSON records to equal the CSV records; and
- the exact 11-row issue inventory.

These are release invariants, not additional geological assumptions.

### 2.4 CSV/JSON and figures were not one publication transaction

The previous workflow atomically published the seven data artifacts and rendered the four figures afterward. A plotting failure could therefore replace a complete prior output with data files but no figures.

Increment 8.0.1 stages and verifies the entire eleven-file bundle before one directory swap. Injected plotting and final-swap failures leave the preceding official bundle byte-identical and remove candidates/backups. The standalone figure writer is also transactional.

### 2.5 Colab test import and stale-folder handling were too fragile

The predecessor’s `tests/__init__.py` workaround modified import behavior for the entire locked test tree. It is removed. Increment 8 tests now follow the locked project convention and import `synthetic_inc8` directly from the local test directory, so an unrelated external package named `tests` cannot intercept the import.

The notebook’s Colab bootstrap now accepts only a ledger-verified Increment 8.0.1 tree by default. Otherwise it safely extracts the exact versioned ZIP into a new versioned folder. An incomplete existing folder is preserved, not overwritten. ZIP members are checked for absolute/traversal paths, duplicates, symlinks, backslashes, NULs, and bounded uncompressed size before extraction.

Verification is closed over the complete extracted file set: every regular file except the ledger must have exactly one ledger entry, and missing, extra, non-canonical, or symlinked paths invalidate the tree. This prevents a valid listed payload from concealing an additional unlisted importable file.

### 2.6 Plotting dependency and inventory language were inaccurate

Because `run_pore_pressure_workflow(..., render_png=True)` is the default, Matplotlib is now an explicit runtime dependency rather than an undeclared environmental assumption.

The zero-count table is now labelled as an **approved packaged input** inventory. It establishes that this project was supplied no approved RFT/MDT/DST/FIT/LOT/XLOT/DFIT files; it does not claim that unprovided field data cannot exist.

## 3. Scientific method and unchanged results

### 3.1 Hydrostatic reference

For positive-downward TVDSS from a mean-sea-level gauge datum:

`P_h,ref = rho_f * g * TVDSS`

This is one configured constant-density gradient from MSL. It is not a measured formation pressure, proof of hydrostatic conditions, or a separately modelled seawater-plus-formation-fluid column.

### 3.2 Vertical effective stress

`sigma'_v = sigma_v - alpha * P_h,ref`

The total vertical stress is an Increment 7 low/base/high shallow-column scenario. Biot alpha is configured, not measured. Negative scenario values would be retained and flagged, never clipped.

The profile offset removes both the measured-only and bridged terminal components before adding Increment 7’s cumulative profile node by node. This avoids double-counting a conditioned interval.

### 3.3 NCT readiness

The strict-no-gap qualifying-thickness ranges remain:

| Well | Configurations | Range (m TVD) | Factor | Disposition |
|---|---:|---:|---:|---|
| Boreas 1 | 0 | not applicable | not applicable | input-QC exclusion |
| Poseidon 2 | 9 | 140.0029–1110.2406 | 7.9301 | fit withheld |
| Poseidon North 1 | 9 | 341.5350–1198.1552 | 3.5081 | fit withheld |
| Proteus 1ST2 | 9 | 350.1931–861.8934 | 2.4612 | fit withheld |

These ranges describe candidate-data extent, not a fitted normal-compaction trend.

### 3.4 Effective-stress terminal scenarios

At `rho_f = 1025 kg/m³` and `alpha = 1.0`:

| Well | TVDSS (m) | Hydrostatic reference (MPa) | Low / base / high effective stress (MPa) |
|---|---:|---:|---:|
| Boreas 1 | 4767.0090 | 47.9171 | 12.0060 / 35.3860 / 58.7661 |
| Poseidon 2 | 5272.7447 | 53.0007 | 18.4633 / 43.1311 / 67.7989 |

Poseidon North 1 and Proteus 1ST2 remain hydrostatic-reference-only because Increment 7 supplies no shallow-column total-stress scenario for either well.

Five result CSVs—NCT readiness, hydrostatic profile, effective-stress scenarios, effective-stress profile, and issues—are byte-identical to the corrected predecessor. `pressure_data_inventory.csv` changes only its two controlled provenance/status phrases to say “approved input.” `pore_pressure_manifest.json` changes for package identity, stronger limitations, and the same exact source hashes. No numeric result changed.

## 4. Outputs

`outputs/08_pore_pressure_effective_stress/` contains exactly:

- 4-row `pressure_data_inventory.csv`;
- 4-row `nct_readiness_summary.csv`;
- 1,053-row `hydrostatic_reference_profile.csv`;
- 36-row `effective_stress_scenarios.csv`;
- 606-row `effective_stress_profile.csv`;
- 11-row `pore_pressure_issues.csv`;
- `pore_pressure_manifest.json`; and
- four PNG QC figures under `figures/`.

The seven CSV/JSON artifacts are byte-deterministic across independent roots. PNG byte identity across different Matplotlib versions is not claimed.

## 5. Tests and notebook

- **Combined suite:** 1,632 collected / 1,632 passed.
- **Locked Increment 1–7.0.4 subset:** 1,368 / 1,368 passed from 18 byte-identical test files.
- **Increment 8 tests:** 264 / 264 passed.
- **Notebook:** 33 cells (21 code, 12 markdown), 33 unique IDs, zero saved outputs, valid nbformat, 12/12 `%%writefile` byte parity.
- **Fresh-baseline execution:** all 21 code cells executed in order from a clean Increment 7.0.4 extraction; the gate printed 25/25 `[PASS]`.
- **Packaged-notebook execution:** all 21 code cells executed from the final ZIP extraction; all 1,632 tests and all 264 Increment 8 tests passed inside the notebook, and the gate printed 25/25 `[PASS]`.
- **Colab-bootstrap branch simulation:** the actual notebook bootstrap performed a first safe extraction, reused an unchanged verified tree, preserved a deliberately contaminated tree and selected a new clean target, and rejected traversal, unlisted-file, and unlisted-symlink cases. This exercised the Colab code path with a simulated mounted Drive; it is not a claim of a hosted Colab runtime execution.
- **Adversarial import check:** all 264 Increment 8 tests pass with an external `tests` package placed first on `PYTHONPATH`.
- **Independent numerical audit:** standard-library-only recomputation reproduced every hydrostatic identity, effective-stress identity, NCT range/factor, and nodewise total-stress reconstruction.

## 6. Package delta relative to the locked scientific baseline

Relative to the corrected Increment 8 predecessor, this patch has **19 changed, 3 added, and 1 removed** file. The removed file is `tests/__init__.py`; its broad package/import side effect is replaced by the narrow local-fixture import. The three added files are this manifest, its completion record, and its checksum ledger.

Exactly three pre-existing Increment 7.0.4 files differ:

- `README.md`;
- `p2mem/__init__.py`;
- `pyproject.toml`.

Exactly 27 files are added and none removed:

1. `08_Pore_Pressure_and_Effective_Stress_Framework.ipynb`
2. `INCREMENT_08_COMPLETION_RECORD.md`
3. `INCREMENT_08_MANIFEST.md`
4. `INCREMENT_08_SHA256SUMS.txt`
5. `INCREMENT_08_0_1_COMPLETION_RECORD.md`
6. `INCREMENT_08_0_1_MANIFEST.md`
7. `INCREMENT_08_0_1_SHA256SUMS.txt`
8. `config/pore_pressure.yml`
9. `p2mem/pore_pressure_models.py`
10. `p2mem/pore_pressure.py`
11. `p2mem/io/pore_pressure_inventory.py`
12. `p2mem/io/pore_pressure_workflow.py`
13. `tests/synthetic_inc8.py`
14. `tests/test_pore_pressure.py`
15. `tests/test_pore_pressure_inventory.py`
16. `tests/test_pore_pressure_workflow.py`
17. `outputs/08_pore_pressure_effective_stress/pressure_data_inventory.csv`
18. `outputs/08_pore_pressure_effective_stress/nct_readiness_summary.csv`
19. `outputs/08_pore_pressure_effective_stress/hydrostatic_reference_profile.csv`
20. `outputs/08_pore_pressure_effective_stress/effective_stress_scenarios.csv`
21. `outputs/08_pore_pressure_effective_stress/effective_stress_profile.csv`
22. `outputs/08_pore_pressure_effective_stress/pore_pressure_issues.csv`
23. `outputs/08_pore_pressure_effective_stress/pore_pressure_manifest.json`
24. `outputs/08_pore_pressure_effective_stress/figures/fig01_hydrostatic_reference_profile.png`
25. `outputs/08_pore_pressure_effective_stress/figures/fig02_nct_readiness_and_sensitivity.png`
26. `outputs/08_pore_pressure_effective_stress/figures/fig03_terminal_effective_stress_scenarios.png`
27. `outputs/08_pore_pressure_effective_stress/figures/fig04_pressure_calibration_data_gap.png`

## 7. Limitations and stop condition

This release lacks direct formation-pressure measurements, leak-off/fracture-integrity constraints, an independently established normally compacted reference interval, measured formation-fluid density, a separately modelled water/formation-fluid pressure column, laboratory Biot coefficients, and calibrated absolute vertical stress. Increment 7’s total-stress inputs are themselves assumption-dominated screening scenarios.

Nothing here is suitable for drilling, mud-weight, casing, fracture-gradient, or other operational decisions. Increment 9 has not been started; no elastic-property, rock-strength, horizontal-stress, mud-window, or wellbore-stability module is included.
