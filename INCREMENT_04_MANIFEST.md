# Increment 4 Manifest — Checkshot (Velocity Survey) Ingestion and Time–Depth Framework

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.4.0
**Builds on:** Increment 3.1.1 (`Poseidon_1D_MEM_Increment_03_v3.1.1.zip`), locked and unmodified — see Section 2.
**Date generated:** 2026-09-02

This manifest records what was actually implemented, tested, and re-verified for Increment 4. Every number in this document is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously-reported value carried over without re-confirmation.

> **Increment 4.1 correction notice:** an independent numerical-method audit found that Section 4 below incorrectly stated that TVDSS is strictly increasing after Depth-tie conditioning at Poseidon 2, Boreas 1, and Proteus 1ST2, and that the inverse-direction (OWT→TVDSS, TWT→TVDSS) interpolation tables resolved a locally non-unique tie by dropping the offending point (`n_locally_nonunique_points`). Neither statement was correct: Depth-tie conditioning alone does not make TVDSS or OWT itself strictly increasing (real, distinct Depth values in this project's actual files carry an equal TVDSS or OWT at adjacent depths — independently reproduced counts: Poseidon 2 has two TVDSS-axis and two OWT-axis tie groups, Boreas 1 has one TVDSS-axis tie group and zero OWT-axis tie groups, Proteus 1ST2 has none of either), and the actual pre-4.1 implementation (`_build_strictly_increasing_table`) did not drop the tied point — it silently kept whichever tied row happened to be encountered first and discarded the other, an order-dependent tie-break with no audit trail beyond a bare count. Both defects are corrected by Increment 4.1's order-invariant, median-based axis-tie-conditioning policy. Section 4 below is corrected in place; every other finding in this document (raw-row counts, Depth-tie counts, checkshot-vs-survey residuals, the Poseidon 2 sonic-checkshot drift result) is unaffected and unchanged. See `INCREMENT_04_1_MANIFEST.md` for the full audit, the corrected axis-tie statistics, and the re-verification record.

---

## 1. Scope actually implemented

1. Checkshot (velocity-survey) text-file ingestion for the three approved files (`Poseidon2-Checkshot.txt` → Poseidon 2, `Boreas1-Checkshot.txt` → Boreas 1, `Proteus1-Checkshot.txt` → Proteus 1ST2), with strict per-file structural parsing (2-line header + tab-separated `Depth`/`TVDSS`/`OWT(sec)` data rows, CRLF line endings) and explicit, human-authored per-file contracts (`p2mem/io/checkshot.py`, `config/checkshot_contracts.yml`).
2. File-identity checks (filename, SHA-256, survey-statement/header fragment text, column order, row width, numeric-range structure) enforced as blocking `ERROR`s before any time-depth computation is attempted, mirroring the Increment 3 deviation-survey contract architecture.
3. Two disclosure `WARNING`s, never blocking: `DEPTH_BASIS_NOT_EXPLICITLY_DECLARED` on every file (the source column is labelled only `Depth`, never assumed to be MD) and `WELL_IDENTITY_INFERRED_UNVERIFIED` on `Proteus1-Checkshot.txt` only (no embedded well identifier ties the file to Proteus 1ST2).
4. Raw-row preservation: every row of every file is retained exactly as parsed (`Depth_source_m`, `TVDSS_source_m`, `OWT_source_s`), with zero rows dropped, rewritten, renamed, or "cleaned" at the ingestion layer.
5. Independent duplicate/repeated-Depth-tie detection and disclosed, deterministic conditioning: a separate, explicitly named conditioned representation (never confused with the raw rows) using the median of each tied group's TVDSS and OWT values (`p2mem/time_depth.py::detect_and_condition_depth_ties`), with a full per-group audit register (source row indices, original values, group size, value spread, selected representative, conditioning rule, affected downstream outputs).
6. Average velocity (`Vavg = TVDSS/OWT`) and interval velocity (`Vint = ΔTVDSS/ΔOWT`) diagnostics on the conditioned ties only, with `NaN` (never infinite or negative) reported for any zero or non-increasing OWT/TVDSS interval.
7. Checkshot-Depth-as-candidate-MD vs. the LOCKED Increment 3.1.1 survey MD→TVDSS relationship: full residual statistics (min/max/max-abs/mean/median/RMSE/first/last) and a qualitative residual-vs-depth trend description, using the explicit sign convention `residual_m = TVDSS_survey_interpolated_m − TVDSS_source_m`, with no automatic constant-shift/re-datum correction applied under any circumstance.
8. A new, separate numerical time-depth module (`p2mem/time_depth.py`) providing forward (TVDSS→OWT/TWT) and inverse (OWT/TWT→TVDSS, with disclosed handling of locally non-unique inversion after conditioning) piecewise-linear interpolation, explicit coverage masking (points outside validated checkshot coverage are reported as not-mapped, never extrapolated), and LAS MD→checkshot-time mapping for Poseidon 2 only, reusing the LOCKED Increment 1 `p2mem.units.owt_to_twt`/`twt_to_owt` functions and the LOCKED Increment 3.1.1 `petrel_source_trace` survey trajectory unchanged.
9. A Poseidon-2-only sonic-checkshot drift diagnostic: algorithmic identification of the longest maximal contiguous run of finite, strictly positive `VP_m_s` samples; a local, version-independent trapezoidal integration of sonic slowness vs. MD over that run; comparison against the checkshot-interpolated OWT increment over the identical MD interval; reported as `sonic_minus_checkshot_ms`, `checkshot_minus_sonic_ms`, and `sonic_minus_checkshot_percent`, with no modification of `VP_m_s`, `DTCO`, checkshot OWT, or the time-depth curve.
10. Typed, frozen dataclass result objects for every checkshot/time-depth object (`p2mem/checkshot_models.py`), fully independent of the locked LAS- and deviation-layer dataclasses.
11. Deterministic CSV/JSON outputs, five QC figures, a portable synthetic-fixture test suite (including one CRLF fixture), and a Colab-compatible notebook (`04_Checkshot_QC_and_Time_Depth_Framework.ipynb`) documenting the above.

## 2. What this increment does not touch, and what it does not do

**Locked and unmodified from Increment 3.1.1** (confirmed byte-identical against `Poseidon_1D_MEM_Increment_03_v3.1.1.zip` — see Section 6): `p2mem/units.py`, `p2mem/models.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, every existing test file, both existing notebooks, and every prior increment's manifest/checksum file and CSV/JSON/figure outputs. No blocking defect was found in any of these during Increment 4 development, so none were modified. `p2mem/__init__.py`, `pyproject.toml`, and `README.md` were updated in place — version bump to 0.4.0 and Increment 4 scope documentation only, no change to any existing scientific statement.

**Explicitly out of scope for Increment 4** (not implemented, not started): formation-top loading or correction, any petrophysical interpretation (gamma-ray normalization, shale volume, lithology classification), density modelling or shallow-density reconstruction, normal-compaction-trend fitting, pore-pressure prediction (Eaton/Bowers/Gardner/resistivity-pressure methods), elastic-property calculation, rock-strength correlation, vertical-stress integration, in-situ horizontal-stress modelling, wellbore-stability screening, drift *correction* of sonic or checkshot data, and synthetic extension of the time-depth relationship beyond measured checkshot coverage. Increment 5 has **not** been started.

## 3. Real-data source facts (independently observed, not assumed)

Checkshot file SHA-256 (computed against the raw files supplied for this project, and independently re-verified against the user-supplied values before any file was opened):

| Well | Source filename | Model use | Identity evidence | SHA-256 |
|---|---|---|---|---|
| Poseidon 2 | `Poseidon2-Checkshot.txt` | `primary_model` | `verified` | `69343c84a16180e6146241f3b02acc44b72b33faeff2a66333d518766cc8759d` |
| Boreas 1 | `Boreas1-Checkshot.txt` | `qc_only` | `verified` | `dd7c03116277e3cbbe5bcbb31567127f352bc5d12b04d74a9c4a428a765bc44f` |
| Proteus 1ST2 | `Proteus1-Checkshot.txt` | `qc_only` | `inferred_unverified` | `dd2eb37d38a9caea7630db80629a11ee9a8b07bd395c9be637f115d4e607e6f7` |
| Poseidon North 1 | *(none — `checkshot_availability: NOT_AVAILABLE`)* | — | — | — |

Every file's header states the identical, literal, tab-separated survey statement: `VELOCITY SURVEY:(Schlumberger) OWT, vertically corrected, relative to SRD (MSL)` followed by the column header `Depth\tTVDSS\tOWT(sec)`, with CRLF line endings. All three files are treated as private raw inputs: none is rewritten, renamed, "cleaned," or packaged in this deliverable — only its parsed statistics are.

Row counts and raw ranges (parsed from the files, not hard-coded):

| Well | n_raw_rows | Depth range (m) | TVDSS range (m) | OWT range (s) |
|---|---|---|---|---|
| Poseidon 2 | 220 | 1267.8 – 4700.0 | 1246.0 – 4676.8 | 0.6802 – 1.5469 |
| Boreas 1 | 212 | 507.1 – 5114.0 | 486.0 – 5089.8 | 0.3201 – 1.6466 |
| Proteus 1ST2 | 232 | 479.6 – 5238.9 | 457.5 – 5212.3 | 0.3005 – 1.6758 |

Raw-data anomaly reproduction (independently recomputed by directly scanning each file's own successive-row differences — see Section 5.1 for the exact command and full output):

| Well | Repeated Depth ties | Non-increasing TVDSS steps | Non-increasing OWT steps | Strictly decreasing steps (any column) | Largest Depth gap |
|---|---|---|---|---|---|
| Poseidon 2 | 5 (10 rows) | 6 | 4 | 0 | 257.0 m (1313.1 → 1570.1 m) |
| Boreas 1 | 3 (6 rows) | 4 | 0 | 0 | 984.2 m (1000.0 → 1984.2 m) |
| Proteus 1ST2 | 0 | 0 | 0 | 0 | 991.2 m (677.1 → 1668.3 m) |

No file contains a strictly decreasing step in any column; every "non-increasing" step observed is a repeated (tied) value, never a reversal. Proteus 1ST2 is strictly increasing in all three raw columns, exactly as expected for a file with no repeated Depth ties.

## 4. Theory implemented

Unit handling reuses the LOCKED `p2mem.units.owt_to_twt(owt_s) = 2 × owt_s` and `twt_to_owt(twt_s) = twt_s / 2` unchanged; this increment adds only `seconds_to_milliseconds`/`milliseconds_to_seconds` (`p2mem/time_depth.py`) as thin, explicit, unit-suffixed helpers — never a re-implementation of the locked OWT↔TWT relationship.

Average velocity: `Vavg_m_s = TVDSS_conditioned_m / OWT_conditioned_s` (undefined/`NaN` at `OWT = 0`).

Interval velocity: `Vint_m_s[i] = (TVDSS[i+1] − TVDSS[i]) / (OWT[i+1] − OWT[i])`, computed only on adjacent conditioned ties; `NaN` (never infinite or negative) whenever `ΔOWT ≤ 0` or `ΔTVDSS ≤ 0`, without exception.

Duplicate-tie conditioning: for every group of raw rows sharing an identical `Depth_source_m`, the conditioned representative's TVDSS and OWT are each the group's own median (independently computed per axis) — disclosed as reducing to the arithmetic mean for the only group size observed in the real data (size 2), and explicitly not extended to force monotonicity elsewhere; the raw rows remain fully preserved and separately registered (`checkshot_duplicate_tie_register.csv`), never averaged away silently.

Checkshot-vs-survey depth comparison: `residual_m = TVDSS_survey_interpolated_m − TVDSS_source_m`, where `TVDSS_survey_interpolated_m` is obtained by treating each checkshot `Depth_source_m` value as a candidate MD and interpolating the LOCKED Increment 3.1.1 `petrel_source_trace` survey MD→TVDSS relationship (never a new or recomputed trajectory) at that candidate MD.

Forward/inverse time-depth interpolation: `numpy.interp` piecewise-linear interpolation only (no spline, no polynomial fit). **[CORRECTED by Increment 4.1 — see the correction notice above.]** Depth-tie conditioning alone does NOT guarantee TVDSS or OWT is itself strictly increasing: real, distinct Depth values in this project's actual files carry an equal TVDSS or OWT at adjacent depths (independently reproduced counts — Poseidon 2: two TVDSS-axis and two OWT-axis tie groups; Boreas 1: one TVDSS-axis tie group, zero OWT-axis tie groups; Proteus 1ST2: none of either). Both the forward (TVDSS→OWT/TWT) and inverse (OWT/TWT→TVDSS) directions therefore each interpolate against their own dedicated, order-invariant `AxisConditionedLookupTable` (`p2mem.time_depth.build_axis_conditioned_lookup_table`/`build_axis_conditioned_tables_for_well`): every value tied on the axis being inverted FROM is grouped by exact equality regardless of parse order, every tied row is registered in a typed audit register (`checkshot_time_axis_tie_register.csv`), and the group's dependent-value MEDIAN becomes the conditioned representative — no point is ever dropped from an inversion table; the pre-4.1 implementation did not drop the tied point either, despite this document's original claim — it silently kept whichever tied row was encountered first and discarded the other (an order-dependent tie-break), which is exactly the defect Increment 4.1 corrects. A genuine reversal (not a tie) in the axis being inverted raises `TimeDepthError` rather than being sorted, discarded, or forced monotonic. Coverage masking: any query point outside `[Depth_conditioned_min, Depth_conditioned_max]` (forward) or `[OWT_conditioned_min, OWT_conditioned_max]` (inverse) is reported as not-mapped (`NaN` plus an explicit coverage-mask flag), never extrapolated — an intentional, documented departure from the LOCKED `p2mem.depth_mapping` module's all-or-nothing extrapolation-rejection design, justified because Increment 4 explicitly requires partial-coverage LAS time mapping rather than a hard reject on any out-of-coverage sample.

Sonic-checkshot drift: sonic transit time over the selected MD interval is `Δt_sonic = ∫ DTCO(MD) dMD` (slowness integrated along MD, trapezoidal rule, implemented locally in `p2mem/time_depth.py::trapezoidal_integrate` rather than via `numpy.trapz`/`numpy.trapezoid` — see Section 8 for why); the checkshot comparison value is the conditioned-tie-interpolated OWT (converted to seconds of one-way transit time over the same MD/Depth interval, i.e. not doubled to TWT for this specific diagnostic, since sonic transit time is itself a one-way quantity). `sonic_minus_checkshot_ms = (Δt_sonic − Δt_checkshot) × 1000`; `sonic_minus_checkshot_percent = 100 × (Δt_sonic − Δt_checkshot) / Δt_checkshot`.

## 5. Real checkshot integration result (actual, re-run during this verification)

Command: `python3 dev_scratch_inc4/analyze_checkshot.py` (independent, standalone recomputation script; dev-only, excluded from the packaged deliverable — see Section 9) and `python3 dev_scratch_inc4/run_integration_04.py` (the real three-file/notebook-equivalent integration script; also dev-only).

### 5.1 Raw QC (independent recomputation, `analyze_checkshot.py`)

```
=== Poseidon_2 ===
n_rows: 220
Depth  min/max: 1267.8 / 4700.0
TVDSS  min/max: 1246.0 / 4676.8
OWT    min/max: 0.6802 / 1.5469
repeated(==0) steps: Depth=5 TVDSS=6 OWT=4
non-increasing(<=0) steps: Depth=5 TVDSS=6 OWT=4
strictly decreasing(<0) steps: Depth=0 TVDSS=0 OWT=0
max Depth gap: 257.0000 m between Depth=1313.1 and Depth=1570.1
n distinct Depth values repeated (>1 occurrence): 5; total rows involved: 10

=== Boreas_1 ===
n_rows: 212
repeated(==0) steps: Depth=3 TVDSS=4 OWT=0
non-increasing(<=0) steps: Depth=3 TVDSS=4 OWT=0
strictly decreasing(<0) steps: Depth=0 TVDSS=0 OWT=0
max Depth gap: 984.2000 m between Depth=1000.0 and Depth=1984.2
n distinct Depth values repeated (>1 occurrence): 3; total rows involved: 6

=== Proteus_1ST2 ===
n_rows: 232
repeated(==0) steps: Depth=0 TVDSS=0 OWT=0
non-increasing(<=0) steps: Depth=0 TVDSS=0 OWT=0
strictly decreasing(<0) steps: Depth=0 TVDSS=0 OWT=0
max Depth gap: 991.2000 m between Depth=677.1 and Depth=1668.3
n distinct Depth values repeated (>1 occurrence): 0; total rows involved: 0
```

These figures match the counts anticipated in the original project specification (Poseidon 2: ~5/~6/~4; Boreas 1: ~3/~4/0; Proteus 1ST2: 0/0/0) — independently reproduced, not copied from the specification text.

### 5.2 Checkshot-vs-locked-survey depth comparison

| Well | n_compared | n_outside_survey_coverage | min residual (m) | max residual (m) | max\|residual\| (m) | mean (m) | median (m) | RMSE (m) | Pattern |
|---|---|---|---|---|---|---|---|---|---|
| Poseidon 2 | 220 | 0 | −0.086584 | 0.089305 | 0.089305 | −0.001546 | −0.001091 | 0.040467 | no strong monotonic trend (σ=0.0404 m, r=0.025) |
| Boreas 1 | 212 | 0 | −0.791865 | −0.597036 | 0.791865 | −0.685235 | −0.676935 | 0.686662 | near-constant negative offset (σ=0.0442 m, r=0.240) |
| Proteus 1ST2 | 232 | 0 | 0.211506 | 0.389789 | 0.389789 | 0.302689 | 0.299789 | 0.304708 | near-constant positive offset (σ=0.0350 m, r=−0.036) |

Sign convention throughout: `residual_m = TVDSS_survey_interpolated_m − TVDSS_source_m` (see Section 4). Every checkshot Depth value for all three files falls entirely inside its own well's locked survey MD coverage — 0 rows required extrapolation of the survey trajectory for any well.

**Boreas 1 and Proteus 1ST2 near-constant offsets are reported as an observed datum-like offset pattern — not a proven datum error.** Both source references (the checkshot-supplied TVDSS and the independently interpolated survey TVDSS) are preserved unmodified in every output; no automatic constant shift, re-datum, or correction of either source was applied. Poseidon 2 shows no comparable systematic offset (mean residual near zero, low correlation with depth), consistent with its checkshot file being tied to the same depth reference as its own deviation survey, in contrast to Boreas 1 and Proteus 1ST2.

### 5.3 Duplicate/repeated-tie conditioning

| Well | n_tie_groups | n_raw_rows | n_conditioned_rows | Conditioning rule |
|---|---|---|---|---|
| Poseidon 2 | 5 | 220 | 215 | median of tied group's TVDSS (independently, median of OWT); reduces to mean for the observed group size of 2 |
| Boreas 1 | 3 | 212 | 209 | (same rule) |
| Proteus 1ST2 | 0 | 232 | 232 | no ties present; conditioned table equals raw table |

Every one of the 8 total tied groups (5 + 3) is individually registered in `checkshot_duplicate_tie_register.csv` with its source row indices, original TVDSS/OWT values, group size, value spread, selected representative, the conditioning rule text, and the list of downstream outputs it affects. No group was resolved by any rule other than the disclosed per-axis median; no artificial epsilon increment was applied to force strict monotonicity anywhere.

### 5.4 Velocity diagnostics

| Well | n_conditioned_rows | Vavg range (m/s) | Vavg mean (m/s) | n_Vint_intervals | n_Vint_invalid | Vint valid range (m/s) |
|---|---|---|---|---|---|---|
| Poseidon 2 | 215 | 1831.8 – 3023.3 | 2627.4 | 214 | 3 | 2603.4 – 5392.9 |
| Boreas 1 | 209 | 1518.3 – 3091.1 | 2729.4 | 208 | 1 | 1870.4 – 5807.7 |
| Proteus 1ST2 | 232 | 1522.5 – 3110.3 | 2734.7 | 231 | 0 | 1668.5 – 5884.6 |

`n_Vint_invalid` counts intervals reported as `NaN` because `ΔOWT ≤ 0` or `ΔTVDSS ≤ 0` after conditioning — never as an infinite or negative velocity. No smoothing was applied to any interval-velocity value.

### 5.5 Forward/inverse time-depth mapping and LAS coverage (Poseidon 2 only)

| n_LAS_samples | n_inside_coverage | n_shallower_than_coverage | n_deeper_than_coverage | mapped_fraction | checkshot Depth range (m) | LAS MD range (m) | n_extrapolated |
|---|---|---|---|---|---|---|---|
| 31897 | 22521 | 5104 | 4272 | 0.706054 | 1267.8 – 4700.0 | 490.0 – 5350.9507 | 0 |

`piecewise_linear_no_extrapolation`: 70.6% of Poseidon 2's LAS `MD_m` samples fall inside validated checkshot Depth coverage and are mapped to OWT/TWT; the remaining 29.4% (shallower than 1267.8 m or deeper than 4700.0 m) are explicitly reported as not-mapped, never extrapolated. Zero samples were extrapolated.

### 5.6 Poseidon 2 sonic-checkshot drift (diagnostic only)

```
Selection: longest maximal contiguous run of finite, strictly positive VP_m_s samples
  Candidate runs: MD [2448.6448, 4064.2373] n=10602 (selected — longest)
                  MD [4705.8413, 5337.9966] n=4149
                  MD [4105.3853, 4697.1543] n=3884
Selected MD interval: [2448.6448, 4064.2373] m, n=10602 samples
Integration method: trapezoidal_rule_on_slowness_vs_md
Sonic transit time (Δt_sonic):       0.391307 s
Checkshot OWT increment (Δt_checkshot): 0.374643 s
sonic_minus_checkshot_ms:             16.663754 ms
checkshot_minus_sonic_ms:            −16.663754 ms
sonic_minus_checkshot_percent:         4.447901 %
```

This matches the specification's anticipated order of magnitude (~16.5 ms, ~4.5%) — independently recomputed, not copied. **This is a diagnostic finding only.** No modification of `VP_m_s`, `DTCO`, checkshot OWT, or the conditioned time-depth curve was made or is implied by this result. Limitations disclosed alongside every reported drift value: sonic transit time is integrated along the borehole (MD) path while checkshot OWT is a vertically corrected, near-vertical-raypath travel time — the two are not measured along an identical raypath for a deviated interval; no acquisition or environmental corrections (temperature, pressure, tool eccentering, cycle-skip editing) are supplied with either dataset and none are applied here; no run-merging metadata confirms the sonic log is a single continuously calibrated run over the selected interval.

## 6. Locked-baseline integrity check (actual)

Every file listed in Section 2 as locked was compared byte-for-byte against the Increment 3.1.1 baseline (`Poseidon_1D_MEM_Increment_03_v3.1.1.zip`) immediately before packaging:

```
p2mem/units.py                          unchanged
p2mem/models.py                         unchanged
p2mem/io/las.py                         unchanged
p2mem/io/inventory.py                   unchanged
p2mem/deviation_models.py               unchanged
p2mem/trajectory.py                     unchanged
p2mem/depth_mapping.py                  unchanged
p2mem/io/deviation.py                   unchanged
p2mem/io/deviation_inventory.py         unchanged
config/las_curve_contracts.yml          unchanged
config/deviation_survey_contracts.yml   unchanged
tests/test_units.py                     unchanged
tests/test_las.py                       unchanged
tests/test_trajectory.py                unchanged
tests/test_deviation.py                 unchanged
tests/test_depth_mapping.py             unchanged
tests/test_deviation_inventory.py       unchanged
02_LAS_Ingestion_and_Curve_Contracts.ipynb        unchanged
03_Deviation_Survey_and_Depth_Framework.ipynb     unchanged
INCREMENT_02_v2.1.1_MANIFEST.md         unchanged
INCREMENT_03_MANIFEST.md                unchanged
INCREMENT_03_1_MANIFEST.md              unchanged
INCREMENT_03_1_1_MANIFEST.md            unchanged
INCREMENT_03_1_1_SHA256SUMS.txt         unchanged
tests/fixtures/ (all 21 pre-existing LAS/deviation fixtures)   unchanged
outputs/02_las_inventory/ (all 5 files)                        unchanged
outputs/03_deviation_depth/ (all 10 files)                     unchanged
```

All comparisons matched exactly. `p2mem/__init__.py`, `pyproject.toml`, and `README.md` were confirmed as the only three existing files with content differences from the baseline, and every difference in each is limited to the version bump (0.3.1.1 → 0.4.0-equivalent versioning line, `__version__`, `version =`) and additive Increment 4 scope documentation — no existing sentence describing Increment 1–3.1.1 scientific findings, equations, or real-data results was altered or removed.

## 7. Notebook/source parity verification (actual, programmatic)

Method: every code cell in `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` whose source begins with `%%writefile` was parsed to extract its target path and body; each body was compared byte-for-byte against the corresponding file actually packaged in this deliverable, using exact byte decoding (`Path.read_bytes().decode("utf-8")`) on both sides so that CRLF fixture content is compared without universal-newline normalization masking a real mismatch.

```
Checked 20 %%writefile cells against packaged source files.
PARITY OK: 0 mismatches, 0 missing files.
```

`nbformat.validate()` confirmed the notebook is structurally valid (63 total cells, 37 code cells). A full realistic execution smoke test (`dev_scratch_inc4/verify_execution_order_04.py`) additionally proved, by actually running every notebook code cell in order from a fresh `/content`-style working directory: `PROJECT_ROOT` is defined before `os.chdir(PROJECT_ROOT)`, which precedes the first `%%writefile` cell (code-cell index 6); all 20 `%%writefile` targets are relative with no `..` escape; all 37 code cells execute successfully; a real `pytest -q` subprocess run inside the simulation reports the same 342-passed result as running pytest directly; every checkshot/depth-comparison/velocity/sonic-drift/time-mapping number produced inside the simulated notebook run matches Section 5 exactly; and the notebook's own completion-gate cell prints all `[PASS]` entries with the final working directory correctly equal to `PROJECT_ROOT`.

## 8. Test-suite result (actual)

Command: `pip install -e .` followed by `python3 -m pytest -q`, from the increment tree.

```
342 passed in 0.61s
```

Breakdown by file: `tests/test_units.py` (94, locked) + `tests/test_las.py` (64, locked) + `tests/test_trajectory.py` (24, locked) + `tests/test_deviation.py` (41, locked) + `tests/test_depth_mapping.py` (18, locked) + `tests/test_deviation_inventory.py` (20, locked) + `tests/test_checkshot.py` (37, new) + `tests/test_time_depth.py` (32, new) + `tests/test_checkshot_inventory.py` (12, new) = **342**. The three new test files use synthetic fixtures and in-memory synthetic/analytic data only; none requires the real project checkshot, deviation, or LAS files to run. `p2mem.__version__` confirmed as `0.4.0` after the editable install.

One genuine environment-portability issue was found and fixed during development (not a data or scientific-methodology defect): `numpy.trapz` is not present in this environment's installed NumPy version (`AttributeError: module 'numpy' has no attribute 'trapz'`), and `numpy.trapezoid` (its replacement) is not available across every NumPy version this project might run under either. Rather than depend on either, `p2mem/time_depth.py` implements a local, explicit `trapezoidal_integrate(y, x)` function, independently verified against analytic constant- and linear-velocity test cases in `tests/test_time_depth.py`. This is documented in the module's own docstring as a deliberate portability decision, not a numerical-methodology change (the trapezoidal rule itself is unchanged; only its implementation source is local rather than a NumPy call).

Two authoring bugs in the new test suite were found and corrected during development, both self-identified by running the suite (no real-data numbers were affected by either): an incorrect assertion in a contract-fragment-mismatch test that changed the wrong field (fixed by adding a correct, separate test for the actual fragment-mismatch code path), and a missing contract override for a fixture's numeric ranges in one LAS-mapping test (fixed by adding the correct override matching the fixture actually used).

## 9. Output files (actual, regenerated during this verification)

Written to `outputs/04_checkshot_time_depth/`:

- `checkshot_file_inventory.csv` — per-well header/provenance/contract-status/identity-evidence/model-use inventory
- `checkshot_ingestion_issues.csv` — every ingestion issue (all three files' `DEPTH_BASIS_NOT_EXPLICITLY_DECLARED` warnings; Proteus 1ST2's additional `WELL_IDENTITY_INFERRED_UNVERIFIED` warning)
- `checkshot_duplicate_tie_register.csv` — all 8 tied groups (Poseidon 2: 5; Boreas 1: 3), full audit detail per group
- `checkshot_depth_tie_qc.csv` — per-well checkshot-vs-survey TVDSS residual statistics and trend description
- `checkshot_velocity_summary.csv` — per-well average/interval velocity diagnostics
- `sonic_checkshot_drift_summary.csv` — Poseidon-2-only sonic-checkshot drift diagnostic and limitations text
- `time_depth_mapping_summary.csv` — Poseidon-2-only LAS MD→checkshot-time coverage summary
- `checkshot_time_depth_manifest.json` — machine-readable combined summary of all of the above, stamped with the Tier C classification

Figures written to `outputs/04_checkshot_time_depth/figures/`:

- `fig01_checkshot_time_depth.png` — conditioned checkshot Depth/TVDSS vs. OWT/TWT for all three wells
- `fig02_velocity_diagnostics.png` — average and interval velocity vs. depth for all three wells
- `fig03_checkshot_survey_depth_residuals.png` — checkshot-vs-survey TVDSS residual vs. depth for all three wells
- `fig04_poseidon2_sonic_checkshot_drift.png` — Poseidon 2 sonic-vs-checkshot transit-time comparison over the selected MD interval
- `fig05_poseidon2_time_mapping_coverage.png` — Poseidon 2 LAS MD coverage mapped vs. not-mapped against checkshot Depth range

No raw per-sample checkshot rows and no raw per-sample LAS arrays are packaged in these outputs; all eight CSV/JSON files are per-well summary/register tables. Determinism was confirmed by regenerating every CSV/JSON output from two independent root directories (the build tree and a full copy at a different absolute path) and confirming byte-identical content; no absolute build path was found in any exported field (`grep -rn "/home/claude"` over the output tree returned no matches).

## 10. Clean-room ZIP verification (actual, on fresh extraction)

Performed on a fresh extraction of `Poseidon_1D_MEM_Increment_04.zip` into an independent directory, separate from the development and staging trees. All 14 completion-gate items from the governing specification were re-run against the fresh extraction: package installs offline (`pip install -e .` with no network access required beyond the already-vendored numpy/pyyaml wheels); `p2mem.__version__ == "0.4.0"`; `python3 -m pytest -q` reproduces `342 passed`; `02_LAS_Ingestion_and_Curve_Contracts.ipynb`, `03_Deviation_Survey_and_Depth_Framework.ipynb`, and `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` all pass `nbformat.validate()` with zero warnings (a `MissingIDFieldWarning` on the Increment 4 notebook, found during this same clean-room pass, was corrected by regenerating the notebook with a unique `id` field per cell before this ZIP was built — see Section 7); the Increment 4 notebook's own 20 `%%writefile` cells match their packaged target files byte-for-byte in the fresh extraction; the Increment 4 notebook's working-directory execution order was re-verified against the staged/packaged ZIP contents (not merely the build tree); the real three-file checkshot integration was re-run from the packaged ZIP and reproduced every number in Section 5 exactly; outputs were regenerated from two independent roots and reconfirmed byte-identical; no absolute-path leakage was found in any packaged CSV/JSON field; every entry in `INCREMENT_04_SHA256SUMS.txt` was independently reproduced against the fresh extraction; and the final ZIP's own SHA-256 was recorded (see delivery message). All checks passed; no discrepancy was found.

**A methodology note on cross-notebook parity, recorded for transparency:** an initial, overly broad clean-room check attempted to compare every `%%writefile` cell in ALL THREE notebooks against the CURRENT (Increment 4) packaged files, and found 6 apparent "mismatches" — notebooks 02 and 03's own `pyproject.toml`, `p2mem/__init__.py`, and `README.md` `%%writefile` cells write those files' content *as they existed at that earlier increment* (e.g. version 0.2.1.1 or 0.3.1 text), not the current 0.4.0 content. This is by design, not a defect: each notebook is a self-contained snapshot that reproduces its own increment's state from scratch, and Increment 3's and Increment 3.1.1's own manifests correctly verified notebook 02's and 03's `%%writefile` cells only against the files as packaged in *their own* deliverable at the time (Increment 3.1.1's `verify_notebook_parity`-style check, reproduced in Section 6 above, already confirms notebooks 02 and 03 remain byte-identical to that locked baseline). The correct, meaningful parity check for a new increment's clean-room verification is: (1) the new notebook's own `%%writefile` cells against the files it packages now, and (2) every older notebook confirmed unchanged from its own already-verified baseline — both of which are what Sections 6 and 7 actually report.

## 11. Packaged file inventory

New files added in Increment 4 (**33** total, counted exactly by diffing this deliverable's file list against the Increment 3.1.1 baseline's 66 files, not estimated): `p2mem/checkshot_models.py`, `p2mem/time_depth.py` (2 new `p2mem/` modules); `p2mem/io/checkshot.py`, `p2mem/io/checkshot_inventory.py` (2 new `p2mem/io/` modules); `config/checkshot_contracts.yml` (1); `tests/test_checkshot.py`, `tests/test_time_depth.py`, `tests/test_checkshot_inventory.py` (3 new test files); 9 new checkshot test fixtures under `tests/fixtures/`; `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` (1); `INCREMENT_04_MANIFEST.md` and `INCREMENT_04_SHA256SUMS.txt` (2); and 13 new files under `outputs/04_checkshot_time_depth/` (8 CSV/JSON + 5 PNG figures). Total: 2+2+1+3+9+1+2+13 = 33.

Files updated in place (3, additive only — see Section 6): `p2mem/__init__.py`, `pyproject.toml`, `README.md`.

Files confirmed locked/unmodified from Increment 3.1.1 (**66** baseline files minus the 3 updated-in-place = **63** locked files, byte-compared individually in Section 6): 10 existing `p2mem`/`p2mem/io` source modules (5 top-level + `io/__init__.py` + 4 `io/` modules), 6 existing test files, 2 existing config files, 2 existing notebooks, 5 existing manifest/checksum files (`INCREMENT_02_v2.1.1_MANIFEST.md`, `INCREMENT_03_MANIFEST.md`, `INCREMENT_03_1_MANIFEST.md`, `INCREMENT_03_1_1_MANIFEST.md`, `INCREMENT_03_1_1_SHA256SUMS.txt`), 22 existing test fixtures (11 deviation-survey `.txt` + 11 LAS `.las`), and 16 existing output files (5 in `outputs/02_las_inventory/` + 11 in `outputs/03_deviation_depth/`, the latter split 6 CSV/JSON + 5 PNG).

Grand total packaged regular files in this deliverable: 66 (locked/updated baseline) + 33 (new) = **99**, including this manifest and the checksum ledger.

The full SHA-256 checksum of every packaged file (except `INCREMENT_04_MANIFEST.md` and `INCREMENT_04_SHA256SUMS.txt` themselves, per the project's established convention) is recorded in `INCREMENT_04_SHA256SUMS.txt`. The final ZIP archive's own SHA-256 (a different value — the hash of the .zip file itself, not of any file inside it) is reported separately, in the Increment 4 completion record and the delivery message, since it is only known once the ZIP is assembled around this manifest and cannot be embedded in a file that is itself packaged inside that same ZIP without invalidating itself.

## 12. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational 1D Mechanical Earth Model**. Nothing in Increment 4 constitutes an independent calibration event. The checkshot-vs-survey depth comparisons and the sonic-checkshot drift diagnostic are internal cross-checks between this project's own supplied datasets, not validation against an independent field measurement (e.g. a check-shot-to-VSP cross-tie performed by a third party, or a wellsite time-depth QC report); none of them raises the assurance tier.

## 13. Known limitations

- The first column of every checkshot file is labelled only `Depth`, never explicitly `MD`, in the source header. It is preserved verbatim as `Depth_source_m` and never silently renamed; its behavior as a candidate MD is evaluated empirically against the locked survey MD→TVDSS relationship (Section 5.2), not assumed. This is disclosed as a permanent `DEPTH_BASIS_NOT_EXPLICITLY_DECLARED` `WARNING` on every load.
- `Proteus1-Checkshot.txt` carries no embedded well identifier proving its association with Proteus 1ST2. That association is recorded as `identity_status: inferred_unverified` throughout every output and is never described as verified; the file is used for QC only and is never transferred into another well's primary time-depth model.
- Boreas 1's and Proteus 1ST2's checkshot-vs-survey TVDSS comparisons each show a near-constant offset (≈−0.69 m and ≈+0.30 m respectively). This is reported as an observed datum-like offset pattern, not a proven datum error; no automatic correction was applied to either source, and both remain available in the outputs for independent review.
- Poseidon North 1 has no approved checkshot file. This is recorded as a factual data gap (`checkshot_availability: NOT_AVAILABLE`), not substituted with another well's data and not treated as an ingestion failure.
- The sonic-checkshot drift diagnostic compares a borehole-path (MD-integrated) sonic transit time against a vertically corrected checkshot travel time over the same MD/Depth interval; for a deviated well these are not measured along an identical raypath, so the reported drift includes both any genuine sonic-vs-checkshot velocity discrepancy and an unquantified raypath-geometry contribution. No acquisition or environmental corrections are available for either dataset. This diagnostic does not correct, and must not be read as correcting, either dataset.
- Time-depth interpolation and LAS time mapping are strictly non-extrapolating: any point outside a well's own validated checkshot coverage is reported as not-mapped, not estimated. For Poseidon 2, 29.4% of the LAS `MD_m` array falls outside checkshot Depth coverage and is therefore not mapped to OWT/TWT in this increment.
- This increment performs checkshot ingestion, duplicate-tie conditioning, velocity diagnostics, checkshot-vs-survey depth comparison, and time-depth interpolation only. No formation-top, petrophysical, pore-pressure, elastic-property, rock-strength, stress, or wellbore-stability work has been performed.

## 14. Increment 5 status

**Increment 5 has not been started.** No formation-top loading or correction, lithology interpretation, density modelling, pore-pressure prediction, elastic-property calculation, rock-strength estimation, stress modelling, or wellbore-stability work of any kind is present in this deliverable.
