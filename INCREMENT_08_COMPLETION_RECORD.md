# Increment 8 Completion Record — Pore-Pressure Data-Gap, Hydrostatic-Reference, and Effective-Stress Screening Framework

**Package:** `p2mem 0.8.0`  
**Baseline:** Increment 7.0.4, SHA-256 `f5c9a9b50dd0edff6e5b31a42d5bba4ab23b993f5ef11c6217122b13f29d89ae`, independently matched before change  
**Assurance:** Tier C — Screening-Level / Uncalibrated Educational  
**Increment 9:** not started

## Delivered scope

Increment 8 publishes an auditable calibration-data gap inventory, low/base/high hydrostatic gauge-pressure references, sonic-NCT readiness sensitivity, and vertical effective-stress scenarios. It uses only packaged, checksum-locked Increment 4/6/7 summary/profile artifacts; no private raw input is required or redistributed.

The evidence gate is intentionally binding: all four wells have zero approved RFT/MDT/DST/FIT/LOT/XLOT/DFIT records, and no independent normal-compaction interval exists. Therefore **no NCT was selected or fitted, no overpressure transform ran, and no overpressure was inferred**. This is a scientifically substantive withheld result, not an incomplete execution.

## Verified results

- **Tests:** 1,594 passed (1,368 locked + 226 Increment 8), zero failures/errors/skips.
- **Notebook:** 34 cells, 13/13 `%%writefile` parity, zero saved outputs, all 22 code cells executed from a clean Increment 7.0.4 extraction, completion gate 22/22 `[PASS]`.
- **Outputs:** seven deterministic CSV/JSON artifacts and four figures; all seven data artifacts are byte-identical across three independent roots.
- **Baseline identity:** exactly three pre-existing files changed (`pyproject.toml`, `p2mem/__init__.py`, `README.md`); every other Increment 1–7.0.4 file is byte-identical.
- **Privacy:** no raw LAS, deviation, checkshot or formation-top file is packaged; zero absolute-path leakage in Increment 8 CSV/JSON.

### NCT readiness

- Boreas 1: no admissible configuration because the locked input-QC exclusion remains binding.
- Poseidon 2: 140.0029–1110.2406 m strict-no-gap candidate thickness, factor 7.9301.
- Poseidon North 1: 341.5350–1198.1552 m, factor 3.5081.
- Proteus 1ST2: 350.1931–861.8934 m, factor 2.4612.

These are candidate-data sensitivity ranges, not fitted normal trends.

### Hydrostatic and effective-stress screening

Hydrostatic reference pressure is `rho_f*g*TVDSS` from an MSL gauge datum at configured fluid densities 1020/1025/1030 kg/m³. It covers all 351 locked profile nodes (1,053 scenario rows) with zero extrapolation and is not a measured formation pressure.

Only Boreas 1 and Poseidon 2 have Increment 7 shallow-column vertical-stress scenarios. At 1025 kg/m³ and `alpha=1.0`, terminal low/base/high effective vertical stress is:

- Boreas 1: **12.0060 / 35.3860 / 58.7661 MPa** at TVDSS 4767.0090 m.
- Poseidon 2: **18.4633 / 43.1311 / 67.7989 MPa** at TVDSS 5272.7447 m.

These values pair assumed/configured inputs and are sensitivity scenarios, not calibrated truth. Poseidon North 1 and Proteus 1ST2 remain hydrostatic-reference-only because no absolute vertical-stress scenario is available for either.

## Corrections made before release

Two defects were found during the same build and corrected before packaging:

1. the local notebook execution initially could not import the freshly written package because changing the working directory does not alter an already-running interpreter's `sys.path`; the setup cell now inserts the resolved project root explicitly, and the notebook was re-executed end to end;
2. the first profile-offset implementation would have double-counted a non-zero conditioned gap in a future dataset. The final implementation removes both the measured-only and bridged terminal components before adding Increment 7's cumulative profile; a synthetic non-zero-bridge regression test pins the identity. The published real values are unchanged because both scenario-supported wells have zero bridged contribution.

3. hosted runtimes can contain an unrelated site-package named `tests`, which can shadow a namespace-style project test directory. The package now includes an explicit `tests/__init__.py` that selects the project-local test package while preserving the locked tests' historical top-level fixture imports. This is a packaging/runtime fix only; scientific calculations and outputs are unchanged.

## Stop condition

No dynamic/static elastic-property, rock-strength, horizontal-stress, stress-calibration, mud-window or wellbore-stability work was started. See `INCREMENT_08_MANIFEST.md` for full contracts, artifacts, limitations and clean-room evidence.
