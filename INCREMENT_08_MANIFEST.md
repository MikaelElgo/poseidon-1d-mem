# Increment 8 Manifest — Pore-Pressure Data-Gap, Hydrostatic-Reference, and Effective-Stress Screening Framework

## 1. Identity and scope

- **Project:** Poseidon 2 — 1D Mechanical Earth Model
- **Package version:** `p2mem 0.8.0`
- **Direct baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.4.zip`
- **Verified baseline SHA-256:** `f5c9a9b50dd0edff6e5b31a42d5bba4ab23b993f5ef11c6217122b13f29d89ae`
- **Assurance:** Tier C — Screening-Level / Uncalibrated Educational
- **Increment 9:** not started

Increment 8 is deliberately narrower than a pore-pressure prediction. It:

1. inventories approved RFT/MDT/DST/FIT/LOT/XLOT/DFIT availability;
2. computes configured low/base/high hydrostatic gauge-pressure references from MSL at the locked Increment 7 profile nodes;
3. carries forward the locked sonic-NCT candidate-thickness sensitivity as readiness evidence;
4. derives vertical effective-stress sensitivity by pairing the Increment 7 low/base/high vertical-stress scenarios with configured fluid-density and Biot-alpha scenarios; and
5. stops when the evidence gate for an NCT or overpressure transform is not met.

No NCT is selected or fitted. No Eaton, Bowers, equivalent-depth, drilling-exponent, or other overpressure transform is implemented or run. No overpressure is inferred. No pressure or stress calibration point is invented, transferred between wells, or substituted. No upstream curve is edited, drift-corrected, filled, clipped, or extrapolated.

## 2. Locked foundation verification

Before any change, the baseline ZIP was re-hashed and matched the SHA-256 above exactly. All 236 archive entries were checked for absolute paths, `..` traversal and symlinks; none was found. All 235 non-self ledger entries in `INCREMENT_07_0_4_SHA256SUMS.txt` matched.

The complete baseline suite was re-run from the clean extraction: **1,368 passed, 0 failed**. In the Increment 8 build the same 18 locked test files remain byte-identical and pass **1,368/1,368** in isolation. Against the baseline ledger, the only changed pre-existing files are the three permitted version/narrative files:

- `pyproject.toml`
- `p2mem/__init__.py`
- `README.md`

Every other Increment 1–7.0.4 file remains byte-identical.

## 3. Source artifacts actually consumed

The real workflow requires no private raw input. It consumes these packaged, locked upstream artifacts and records their hashes in `pore_pressure_manifest.json`:

| Source artifact | SHA-256 |
|---|---|
| `outputs/04_checkshot_time_depth/sonic_checkshot_drift_summary.csv` | `17c84fcf9c9c320d9de665023d5d19ab6c5112bdf0d408378a289c9250886874` |
| `outputs/06_petrophysics_eligibility/method_eligibility_summary.csv` | `7fa715459de2eaa2007cdffe1af30a9c3eb424c78650f618ba34738d9a5c64b9` |
| `outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json` | `00e05aaa35454aef62bb7541adfbccca5a348ff8ccb2ecbc26b9a8093877a58e` |
| `outputs/06_petrophysics_eligibility/thickness_sensitivity_summary.csv` | `0c953df792a474960760e4bc491a05e2ffa448a8909589accadc14c78f2aec3e` |
| `outputs/07_density_overburden/overburden_eligibility_summary.csv` | `8bd03850d1ea8a58b620810f65af18c1d4115b3cd385c542949d7ba22e45cf12` |
| `outputs/07_density_overburden/shallow_column_scenarios.csv` | `356a5e83bca131ed1046c83d0c27d5624bafe8b2510cdff8a500871514aca7a8` |
| `outputs/07_density_overburden/vertical_stress_profile.csv` | `bfe2bd37d31793285f06db34fda6e3e715dd8f085a6685620bca08167941ad52` |

Each CSV reader fails closed on a missing file, missing/duplicate required header, or wrong row width. The upstream petrophysics manifest must explicitly keep all three calibration-availability flags false. Method-eligibility and thickness-sensitivity candidate-well sets must agree. The strict-no-gap NCT readiness input must contain exactly the nine unique endpoint-scenario × proxy-threshold cases per candidate well. The overburden inventory must contain exactly one recognized record per well and remain consistent with shallow-scenario availability.

## 4. Equations and configured assumptions

### 4.1 Hydrostatic reference

For a node at positive-downward TVDSS below MSL:

`P_h_ref = rho_f * g * TVDSS`

The gauge-pressure datum is MSL. `rho_f` is configured at 1020, 1025 and 1030 kg/m³; `g = 9.80665 m/s²`. These are assumptions. The output is a reference curve, not a measured formation pressure and not proof of hydrostatic conditions.

### 4.2 Vertical effective stress

`sigma'_v = sigma_v - alpha * P_h_ref`

The total vertical-stress input is an Increment 7 low/base/high shallow-column scenario. `alpha` is configured at 0.8 and 1.0 because no laboratory Biot-coefficient measurement exists. Negative scenario values, if produced, are retained and flagged—never clipped. The public functions and records reject booleans, textual numerics, complex values, NaN, infinity and out-of-domain inputs with typed errors.

For a profile node, Increment 7's cumulative stress includes strictly measured plus explicitly bridged density. The scenario offset therefore removes both terminal measured-only and bridged components before adding the cumulative profile node by node. This identity is tested with a synthetic non-zero bridged component even though the two published real scenario wells have zero bridged contribution.

## 5. Measured real-data findings

### 5.1 Calibration inventory

Every one of the four wells has zero approved RFT, MDT, DST, FIT, LOT, XLOT and DFIT records. Each well is therefore recorded as `NOT_AVAILABLE`; the absence is factual and never replaced with a cross-well value.

### 5.2 NCT readiness, not an NCT result

| Well | Strict-no-gap configurations | Qualifying thickness range (m TVD) | Factor | Disposition |
|---|---:|---:|---:|---|
| Boreas 1 | 0 | not applicable | not applicable | input-QC exclusion |
| Poseidon 2 | 9 | 140.0029–1110.2406 | 7.9301 | fit withheld |
| Poseidon North 1 | 9 | 341.5350–1198.1552 | 3.5081 | fit withheld |
| Proteus 1ST2 | 9 | 350.1931–861.8934 | 2.4612 | fit withheld |

These ranges quantify sensitivity of candidate data extent. They do not establish a normal-compaction interval. Pressure calibration and independent normal-interval evidence are both absent; every readiness record has `nct_fit_performed = false` and `overpressure_inferred = false`.

### 5.3 Hydrostatic-reference coverage

The locked vertical-stress profile contains 351 decimated nodes. Low/base/high references produce 1,053 rows and cover all four wells with zero extrapolation.

| Well | Locked nodes | TVDSS range (m) | Base reference at deepest node (MPa) |
|---|---:|---:|---:|
| Boreas 1 | 80 | 3978.4436–4767.0090 | 47.9171 |
| Poseidon 2 | 122 | 4063.7425–5272.7447 | 53.0007 |
| Poseidon North 1 | 116 | 3759.4089–4907.9108 | 49.3334 |
| Proteus 1ST2 | 33 | 4897.2011–5217.6181 | 52.4465 |

### 5.4 Effective-stress screening scenarios

Only Boreas 1 and Poseidon 2 have Increment 7 shallow-column vertical-stress scenarios, so only these wells receive effective-stress scenarios. Poseidon North 1 and Proteus 1ST2 remain hydrostatic-reference-only; effective stress is explicitly not computed for them.

At the base fluid density (1025 kg/m³) and `alpha = 1.0`:

| Well | TVDSS (m) | Hydrostatic reference (MPa) | Low / base / high effective stress (MPa) |
|---|---:|---:|---:|
| Boreas 1 | 4767.0090 | 47.9171 | 12.0060 / 35.3860 / 58.7661 |
| Poseidon 2 | 5272.7447 | 53.0007 | 18.4633 / 43.1311 / 67.7989 |

Across all configured fluid-density, alpha and vertical-stress scenarios, the ranges are 11.7723–68.5365 MPa for Boreas 1 and 18.2047–78.6058 MPa for Poseidon 2. These spreads are sensitivity results, not calibrated uncertainty intervals.

Poseidon 2's locked sonic-checkshot drift diagnostic remains +4.4479%. It is carried as a warning only; no sonic, checkshot, NCT or pressure value is corrected from it.

## 6. Implementation and artifact contracts

Added implementation:

- `config/pore_pressure.yml`
- `p2mem/pore_pressure_models.py`
- `p2mem/pore_pressure.py`
- `p2mem/io/pore_pressure_inventory.py`
- `p2mem/io/pore_pressure_workflow.py`

Added tests:

- `tests/synthetic_inc8.py`
- `tests/test_pore_pressure.py`
- `tests/test_pore_pressure_inventory.py`
- `tests/test_pore_pressure_workflow.py`

The six CSV artifacts have exact ordered schemas, strict field types, closed string vocabularies, unique primary keys, finite numeric values and cross-field numerical identities enforced before serialization. The JSON artifact has an exact top-level schema, exact registered limitation text, closed calculation/gate blocks, source-hash validation and row-count agreement. Export writes a complete candidate set into an isolated sibling directory, re-reads and compares every serialized CSV record and JSON document, then publishes the directory. A mid-publication failure is injected in a regression test and the prior directory is restored byte-exact with no candidate residue.

## 7. Outputs

`outputs/08_pore_pressure_effective_stress/` contains:

- 4-row `pressure_data_inventory.csv`
- 4-row `nct_readiness_summary.csv`
- 1,053-row `hydrostatic_reference_profile.csv`
- 36-row `effective_stress_scenarios.csv`
- 606-row `effective_stress_profile.csv`
- 11-row `pore_pressure_issues.csv`
- `pore_pressure_manifest.json`
- four PNG figures

The seven CSV/JSON artifacts are byte-deterministic across independent roots. Figures are verified present and visually inspected, but PNG byte identity is not claimed across different matplotlib versions.

## 8. Verification

- **Combined suite:** 1,594 collected / 1,594 passed.
- **Locked subset:** 1,368 / 1,368 passed from 18 byte-identical baseline test files.
- **Increment 8 tests:** 226 / 226 passed.
- **Notebook:** `08_Pore_Pressure_and_Effective_Stress_Framework.ipynb`, 34 cells (22 code, 12 markdown), 34 unique IDs, zero saved outputs, valid nbformat, 13/13 `%%writefile` byte parity.
- **Notebook execution semantics:** all 22 code cells executed in order from a fresh Increment 7.0.4 extraction; the actual pytest subprocess reported 1,594 passed and 226 Increment 8 tests passed; the workflow ran, independent-root bytes matched and the gate printed 22/22 `[PASS]`.
- **Determinism:** all seven CSV/JSON outputs matched byte-for-byte between the build tree, the fresh notebook execution root, and an independent workflow root.
- **Privacy:** no private LAS, deviation, checkshot or formation-top source is packaged; no absolute build path occurs in the Increment 8 CSV/JSON outputs.
- **Line endings:** text sources, notebook write bodies, CSV, JSON, manifest and ledger use LF.
- **Runtime dependencies:** unchanged—NumPy and PyYAML only. Matplotlib remains notebook/figure-generation tooling, not an installable runtime dependency.

## 9. Limitations and stop condition

The scientifically correct output of the NCT/overpressure gate is **withheld**, not a numeric pressure prediction. The project lacks direct formation-pressure measurements, leak-off/fracture-integrity constraints, an independently established normally compacted reference interval, measured formation-fluid density, laboratory Biot coefficient, and calibrated absolute vertical stress. The Increment 7 total-stress inputs are themselves shallow-column scenarios dominated by assumptions.

Accordingly, none of the hydrostatic or effective-stress values may be used for drilling, mud-weight, casing, fracture-gradient, or operational decisions. Increment 9 has not been started; no elastic-property, rock-strength, horizontal-stress or wellbore-stability module is included.
