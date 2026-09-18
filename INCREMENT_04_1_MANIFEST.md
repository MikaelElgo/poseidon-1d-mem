# Increment 4.1 Manifest — Corrective Patch: Order-Invariant Axis-Tie Conditioning for Checkshot Time-Depth Inversion

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.4.1
**Corrective patch of:** Increment 4 (`Poseidon_1D_MEM_Increment_04.zip`, `p2mem` 0.4.0)
**Date generated:** 2026-09-02

This manifest records what was actually implemented, tested, and re-verified for Increment 4.1. Every number in this document is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously-reported value carried over without re-confirmation. Increment 4.1 is a **narrowly scoped corrective patch only**: it does not begin Increment 5, and it implements no formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, or wellbore-stability analysis.

> **Increment 4.1.1 correction notice:** an independent numerical-validation audit found that Section 1.1's claim — "a GENUINE reversal (not a tie — a later group's value less than an earlier group's) raises `TimeDepthError`" — is not true in every case. `build_axis_conditioned_lookup_table` grouped ALL occurrences of an identical axis value together GLOBALLY (by exact-value equality across the whole array, not only adjacent occurrences) BEFORE checking the grouped sequence for a reversal. A reversal that returns to an already-seen value — e.g. the independent-axis sequence `[100.0, 200.0, 100.0]` — is silently absorbed by this global grouping (the trailing `100.0` merges into the first group, producing an apparently-valid, strictly-increasing `[100.0, 200.0]`) and was therefore NOT raising `TimeDepthError`, contradicting the stated guarantee. This is corrected in Increment 4.1.1 by evaluating the ORIGINAL, ungrouped independent-axis sequence's successive differences for negativity BEFORE any grouping is attempted; only once the original sequence is confirmed non-decreasing are exact ADJACENT ties grouped and median-conditioned, exactly as before. This is provably equivalent to this section's described behavior for every legitimate adjacent tie (including every real axis-tie case in Section 3 below, all of which are adjacent) and strictly stronger against a reversal that returns to an already-seen, non-adjacent value. No real Poseidon 2/Boreas 1/Proteus 1ST2 result changes: zero genuine reversals of either kind were found in any of the three approved checkshot files' real data, in this increment or Increment 4.1. Three further blocking defects (incomplete full-MD validation in `compute_sonic_checkshot_drift`; an untyped crash on zero survey-coverage overlap in `compare_checkshot_to_survey`; missing batch isolation for numerical failures in `load_checkshot_surveys`) and one input-safety gap (`seconds_to_milliseconds`/`milliseconds_to_seconds`) were also found and corrected. See `INCREMENT_04_1_1_MANIFEST.md` for the full audit, the corrected statements, and the re-verification record.

---

## 1. The blocking finding and what was actually corrected

### 1.1 Finding 1 — order-dependent axis-tie handling (corrected)

Increment 4's `p2mem.time_depth._build_strictly_increasing_table` (the internal helper feeding `tvdss_to_owt`/`owt_to_tvdss`/`tvdss_to_twt`/`twt_to_tvdss`) resolved a repeated (tied) value on the axis being inverted by keeping whichever tied row happened to be encountered FIRST while walking the Depth-conditioned table in Depth order, and silently discarding the other. This is an ORDER-DEPENDENT tie-break: the resolved inverse value depended on an incidental property (which physical row's Depth happened to be smaller) rather than on a principled, symmetric rule, and the discarded row's information vanished with no audit trail beyond a bare count (`n_locally_nonunique_points`).

Three real, independently reproduced examples of this defect (all confirmed against the actual approved checkshot files, using the code and data in this deliverable):

| Well | Interpolation direction | Tied axis value | Pre-4.1 result (order-dependent, WRONG) | Post-4.1 result (order-invariant median, CORRECT) |
|---|---|---|---|---|
| Poseidon 2 | `owt_to_tvdss` | OWT = 1.0319 s | TVDSS = 2591.3 m (first-parsed row only) | TVDSS = 2591.35 m (median of 2591.3 / 2591.4) |
| Poseidon 2 | `tvdss_to_owt` | TVDSS = 4495.6 m | OWT = 1.5015 s (first-parsed row only) | OWT = 1.50175 s (median of 1.5015 / 1.5020) |
| Boreas 1 | `tvdss_to_owt` | TVDSS = 3988.8 m | OWT = 1.3531 s (first-parsed row only) | OWT = 1.35385 s (median of 1.3531 / 1.3546) |

All three are reproduced exactly, and independently re-verified as no longer resolving to the pre-4.1 value, in `dev_scratch_inc4_1/run_integration_04.py`'s regression-proof block and in the packaged notebook's Step 11b (see Section 4 below for the actual, current run output).

**The fix.** `_build_strictly_increasing_table` is REMOVED. It is replaced by:

- `p2mem.checkshot_models.AxisTimeDepthTieRegisterEntry` — a new, typed audit-register entry for one tied group on the axis being inverted (TVDSS, for `tvdss_to_owt`; OWT, for `owt_to_tvdss`). Distinct from, and never confused with, the pre-existing `DuplicateTieRegisterEntry` (Depth-axis raw-row ties).
- `p2mem.checkshot_models.AxisConditionedLookupTable` — a new, typed lookup table (`axis_values`, `dependent_values`, plus tie-group/collapse/identical-pair/genuinely-non-unique counts and the conditioning method string). Never described as raw, uniquely measured, or unconditioned.
- `p2mem.time_depth.build_axis_conditioned_lookup_table(...)` — groups every value tied on the axis being inverted by EXACT equality, regardless of which tied row was parsed first (order-invariant by construction — see Section 4.2's synthetic order-invariance proof and Section 1.1's real-data proof above); registers the group's COMPLETE original rows in an `AxisTimeDepthTieRegisterEntry` (never discarded unrecorded); and uses the group's dependent-value MEDIAN as the single conditioned representative. A group whose tied rows ALSO share an identical dependent value (`tie_kind="identical_pair"`) still collapses to one row without changing the value, but is still counted and registered — never silently merged away. After grouping, the per-group axis values must themselves be strictly increasing; a GENUINE reversal (not a tie — a later group's value less than an earlier group's) raises `TimeDepthError` rather than being sorted, discarded, or forced monotonic. **[Increment 4.1.1 correction — see the notice at the top of this document: this statement, as originally written, was INCORRECT for a reversal that returns to an already-seen value, e.g. `[100.0, 200.0, 100.0]` — global exact-value grouping silently absorbed that case. Increment 4.1.1 now evaluates the original, ungrouped sequence for a negative step BEFORE grouping, closing this gap. No real checkshot data was affected — see below.]** No genuine reversal was found in any of the three approved checkshot files' real data — see Section 3.
- `p2mem.time_depth.build_axis_conditioned_tables_for_well(...)` — builds both directions (`tvdss_to_owt`, `owt_to_tvdss`) for one well in a single call; this is the function `p2mem.io.checkshot.load_checkshot_file` now calls once per well, attaching the result to two new fields on `CheckshotWellResult`: `axis_tie_entries` (a flat tuple) and `axis_tables` (a dict keyed by direction). Every downstream consumer (interpolation, the CSV/JSON exporters, the notebook) therefore shares one canonical, order-invariant computation.
- `tvdss_to_owt`, `owt_to_tvdss`, `tvdss_to_twt`, `twt_to_tvdss` now take a pre-built `AxisConditionedLookupTable` (not a bare `ConditionedCheckshotData`) and return a 2-tuple `(values, mask)` — the old 3-tuple with `n_dropped` no longer exists, because no point is ever dropped from an inversion table anymore; each function also guards against being called with a table built for the wrong direction, raising `TimeDepthError`.
- `p2mem.io.checkshot_inventory.build_checkshot_time_axis_tie_register_rows(results)` — a new row-builder producing one row per `AxisTimeDepthTieRegisterEntry`, written to the new `checkshot_time_axis_tie_register.csv` output (Section 5). A new `_axis_tie_conditioning_summary` helper embeds each well's per-direction tie-group/collapsed-point/identical-pair/genuinely-non-unique counts and the conditioning-policy text into `checkshot_time_depth_manifest.json` under a new `axis_tie_conditioning` key per well.

### 1.2 Finding 2 — incorrect documentation (corrected)

`INCREMENT_04_MANIFEST.md` Section 4 stated that "forward directions (TVDSS→OWT, TVDSS→TWT) [are] always well-posed since TVDSS is strictly increasing after conditioning at Poseidon 2, Boreas 1, and (trivially) Proteus 1ST2." This was INCORRECT. Depth-tie conditioning alone does not guarantee TVDSS or OWT is itself strictly increasing — real, distinct Depth values in the actual approved files carry an equal TVDSS or OWT at adjacent depths. The independently reproduced, correct counts (see Section 3 for the full per-well/per-direction breakdown) are:

| Well | TVDSS-axis tie groups (post-Depth-conditioning) | OWT-axis tie groups (post-Depth-conditioning) |
|---|---|---|
| Poseidon 2 | 2 | 2 |
| Boreas 1 | 1 | 0 |
| Proteus 1ST2 | 0 | 0 |

`INCREMENT_04_MANIFEST.md` has been corrected in place with a correction notice at the top of the document and an in-line correction of the Section 4 paragraph itself (following the Increment 3.1 precedent of correcting a prior manifest's specific error in place, rather than rewriting the whole document) — see that file directly. `README.md`, this project's own docstrings (`p2mem/time_depth.py`, `p2mem/checkshot_models.py`, `p2mem/io/checkshot.py`, `p2mem/__init__.py`), and the packaged notebook's markdown explanations have all been updated to state this correctly and consistently, distinguishing three representations at every point they are discussed: (1) raw checkshot data (`CheckshotStationData`, never modified), (2) the Depth-tie-conditioned table (`ConditionedCheckshotData`, strictly increasing in Depth by construction, but NOT guaranteed strictly increasing in TVDSS or OWT), and (3) the axis-tie-conditioned lookup table (`AxisConditionedLookupTable`, strictly increasing in the axis being inverted, by the Increment 4.1 conditioning policy above).

### 1.3 Numerical-validation hardening (not a defect fix to any real-data result — see Section 3.4)

- `trapezoidal_integrate(y, x)` now validates: `x`/`y` one-dimensional, finite, equal length, at least 2 samples, and `x` strictly increasing — raising `TimeDepthError` otherwise rather than silently integrating garbage (a decreasing or duplicate `x` could previously produce a physically invalid negative "integral"). Regression tests: `test_trapezoidal_integrate_rejects_non_1d_input`, `_rejects_mismatched_lengths`, `_rejects_fewer_than_two_samples`, `_rejects_non_finite_values`, `_rejects_non_increasing_x_never_sorts`.
- `compute_sonic_checkshot_drift(...)` now validates `md_m` (finite, one-dimensional) and `vp_m_s` (one-dimensional, matching shape), and — the specific regression this task named — requires the MD values WITHIN the selected sonic run to be strictly increasing, raising `TimeDepthError` for a decreasing or duplicate MD run rather than silently integrating it into a physically invalid negative transit time (the pre-4.1 implementation performed none of this validation). It also now rejects a non-positive checkshot OWT increment over the comparison interval. Regression tests: `test_sonic_checkshot_drift_rejects_decreasing_md_never_negative_transit_time`, `_rejects_duplicate_md`, `_rejects_non_finite_md`, `_rejects_incompatible_md_vp_shapes`, `_rejects_non_positive_checkshot_owt_increment`.
- `detect_and_condition_depth_ties` and `compare_checkshot_to_survey` gained equivalent finite/1D/equal-length guard clauses; `_interp_with_coverage` (the shared interpolation helper) gained a second, independent line of defense against a future caller violating its strictly-increasing-x contract.
- **This hardening does not change the real, already-verified Poseidon 2 sonic-drift result.** The real Poseidon 2 sonic MD run (10,602 samples, MD [2448.6448, 4064.2373] m) was independently confirmed genuinely strictly increasing (minimum step 0.1523 m, no duplicates) before this hardening was added, and the drift result reported in Section 3.5 below is bit-for-bit identical to Increment 4's: `sonic_transit_time_s = 0.391307`, `checkshot_owt_increment_s = 0.374643`, `sonic_minus_checkshot_ms = 16.663754`, `sonic_minus_checkshot_percent = 4.447901`.

## 2. What was NOT touched

- No change to any raw checkshot, deviation, or LAS data, or to any locked module (`p2mem/units.py`, `p2mem/models.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`).
- No change to notebooks `02_LAS_Ingestion_and_Curve_Contracts.ipynb` or `03_Deviation_Survey_and_Depth_Framework.ipynb` (byte-identical to the Increment 4 baseline — see Section 6).
- No change to Depth-tie conditioning (`detect_and_condition_depth_ties`, `DuplicateTieRegisterEntry`, `checkshot_duplicate_tie_register.csv`) beyond the added finiteness guard clause — the Depth-axis tie counts, groups, and representative values are unchanged from Increment 4 (Poseidon 2: 5 groups; Boreas 1: 3 groups; Proteus 1ST2: 0).
- No change to the checkshot-vs-survey depth-comparison residuals, the velocity diagnostics, the LAS-to-checkshot-time mapping summary, or any of the seven Increment 4 output files not listed as changed in Section 5 — all seven reproduce byte-identically (verified in Section 5).
- No new scope: formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, and wellbore-stability screening remain entirely unimplemented and out of scope. Increment 5 has NOT been started.

## 3. Real-data findings (independently reproduced, this deliverable)

### 3.1 Axis-tie register (`checkshot_time_axis_tie_register.csv`) — actual content

5 rows total (2 `identical_pair`, 3 `genuinely_non_unique`):

| well_key | interpolation_direction | axis | tie_axis_value | group_size | dependent_value_spread | selected_representative | tie_kind |
|---|---|---|---|---|---|---|---|
| Boreas_1 | tvdss_to_owt | TVDSS_conditioned_m | 3988.8 | 2 | 0.0015 | 1.35385 | genuinely_non_unique |
| Poseidon_2 | tvdss_to_owt | TVDSS_conditioned_m | 2606.5 | 2 | 0.0 | 1.0351 | identical_pair |
| Poseidon_2 | tvdss_to_owt | TVDSS_conditioned_m | 4495.6 | 2 | 0.0005 | 1.50175 | genuinely_non_unique |
| Poseidon_2 | owt_to_tvdss | OWT_conditioned_s | 1.0319 | 2 | 0.1 | 2591.35 | genuinely_non_unique |
| Poseidon_2 | owt_to_tvdss | OWT_conditioned_s | 1.0351 | 2 | 0.0 | 2606.5 | identical_pair |

Note that Poseidon 2's TVDSS=2606.5/OWT=1.0351 tie is simultaneously an axis tie on BOTH directions with IDENTICAL values on both axes — an `identical_pair` case satisfied organically by real data, not a synthetic-only example.

### 3.2 Per-well axis-tie-conditioning summary (from `checkshot_time_depth_manifest.json`)

| Well | TVDSS-axis tie groups | TVDSS-axis collapsed points | TVDSS-axis identical pairs | TVDSS-axis genuinely-non-unique | OWT-axis tie groups | OWT-axis collapsed points | OWT-axis identical pairs | OWT-axis genuinely-non-unique |
|---|---|---|---|---|---|---|---|---|
| Poseidon 2 | 2 | 2 | 1 | 1 | 2 | 2 | 1 | 1 |
| Boreas 1 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| Proteus 1ST2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Zero genuine reversals were found in any well's axis-conditioned table (every non-strictly-increasing case at this stage is an exact tie, never a decreasing step) — the `TimeDepthError`-raising reversal path is exercised only by the synthetic unit tests in Section 3.3, not by real data.

### 3.3 Forward/inverse round-trip demonstration (real data, actual output)

```
Boreas_1: tvdss_to_owt table n_in=209 n_out=208 n_tie_groups=1 (identical=0, non_unique=1);
          owt_to_tvdss table n_in=209 n_out=209 n_tie_groups=0 (identical=0, non_unique=0)
  round-trip sample: TVDSS=[486.0, 3535.3, 5089.8] -> OWT=[0.3201, 1.2411, 1.6466]
    -> TWT=[0.6402, 2.4822, 3.2932] -> TVDSS_back=[486.0, 3535.3, 5089.8] (inside coverage: True/True)
Poseidon_2: tvdss_to_owt table n_in=215 n_out=213 n_tie_groups=2 (identical=1, non_unique=1);
          owt_to_tvdss table n_in=215 n_out=213 n_tie_groups=2 (identical=1, non_unique=1)
  round-trip sample: TVDSS=[1246.0, 3075.1, 4676.8] -> OWT=[0.6802, 1.1381, 1.5469]
    -> TWT=[1.3604, 2.2762, 3.0938] -> TVDSS_back=[1246.0, 3075.1, 4676.8] (inside coverage: True/True)
Proteus_1ST2: tvdss_to_owt table n_in=232 n_out=232 n_tie_groups=0 (identical=0, non_unique=0);
          owt_to_tvdss table n_in=232 n_out=232 n_tie_groups=0 (identical=0, non_unique=0)
  round-trip sample: TVDSS=[457.5, 3464.0, 5212.3] -> OWT=[0.3005, 1.2174, 1.6758]
    -> TWT=[0.601, 2.4348, 3.3516] -> TVDSS_back=[457.5, 3464.0, 5212.3] (inside coverage: True/True)

Order-dependence regression checks (must be group MEDIAN, never the first-parsed row):
  Poseidon 2  OWT=1.0319 s   -> TVDSS = 2591.3500000000004 m  (median of 2591.3/2591.4; NOT 2591.3)
  Poseidon 2  TVDSS=4495.6 m -> OWT   = 1.50175 s  (median of 1.5015/1.5020; NOT 1.5015)
  Boreas 1    TVDSS=3988.8 m -> OWT   = 1.35385 s  (median of 1.3531/1.3546; NOT 1.3531)
  All three PASS: order-dependent first-tied-row resolution no longer occurs.
```

(Reproduced from `dev_scratch_inc4_1/run_integration_04.py`, dev-only, not packaged — exercised identically inside the packaged notebook's Step 11b, executed as part of the clean-room notebook run in Section 6.)

### 3.4 Sonic-checkshot drift (unaffected by this patch — bit-for-bit reproduction)

```
Selected MD interval: [2448.6448, 4064.2373] m, n=10602 samples
Sonic transit time (Δt_sonic):          0.391307 s
Checkshot OWT increment (Δt_checkshot): 0.374643 s
sonic_minus_checkshot_ms:               16.663754 ms
sonic_minus_checkshot_percent:           4.447901 %
```

Bit-for-bit identical to Increment 4's Section 5.6. This confirms the Section 1.3 numerical-validation hardening did not alter the arithmetic path for already-valid real data.

### 3.5 Checkshot-vs-survey depth comparison and Depth-axis ties (unaffected — bit-for-bit reproduction)

Poseidon 2: n=220, max\|residual\|=0.089305 m, mean=−0.001546 m. Boreas 1: n=212, max\|residual\|=0.791865 m, mean=−0.685235 m. Proteus 1ST2: n=232, max\|residual\|=0.389789 m, mean=0.302689 m. Depth-axis duplicate-tie groups: Poseidon 2=5, Boreas 1=3, Proteus 1ST2=0. All identical to Increment 4's Section 5.2/5.3 — see Section 5 below for the byte-identity confirmation of the underlying CSV outputs.

## 4. Test suite — actual results

Command: `pip install -e . --no-build-isolation --no-index --no-deps` (offline; no network access used beyond the already-vendored numpy/pyyaml wheels) followed by `python3 -m pytest -q`, from the increment tree.

```
369 passed in 0.99s
```

This is **27 more tests than Increment 4's reported 342** (this count is read directly from the actual `pytest` output above, not assumed in advance). Breakdown by file, collected directly with `pytest --collect-only` against the code actually in this deliverable:

`tests/test_units.py` (94) + `tests/test_las.py` (64) + `tests/test_trajectory.py` (27) + `tests/test_deviation.py` (52) + `tests/test_depth_mapping.py` (18) + `tests/test_deviation_inventory.py` (6) + `tests/test_checkshot.py` (39) + `tests/test_time_depth.py` (52) + `tests/test_checkshot_inventory.py` (17) = **369**.

The Increment 4.1 test additions are concentrated in the three checkshot-layer files: `tests/test_time_depth.py` grew from 32 to 52 (+20 — the new `build_axis_conditioned_lookup_table` order-invariance/identical-pair/reversal/validation tests, the rewritten table-based `tvdss_to_owt`/`owt_to_tvdss`/`tvdss_to_twt`/`twt_to_tvdss` tests, the `trapezoidal_integrate` validation tests, and the `compute_sonic_checkshot_drift` validation/regression tests); `tests/test_checkshot.py` grew from 37 to 39 (+2 — end-to-end wiring tests for `load_checkshot_file`'s new `axis_tie_entries`/`axis_tables` fields, including a new synthetic fixture `tests/fixtures/checkshot_axis_tie.txt` exercising a genuine axis tie with no Depth tie); `tests/test_checkshot_inventory.py` grew from 12 to 17 (+5 — `build_checkshot_time_axis_tie_register_rows` content/sort/determinism/no-absolute-path tests and the manifest's new per-well `axis_tie_conditioning` summary tests). All new tests use synthetic fixtures or hand-built typed objects only, per this project's established portability convention — none requires the real project checkshot, deviation, or LAS files.

Required regression coverage, confirmed present in `tests/test_time_depth.py` (unit tests reproducing the identical defect *shape* found in real data, per that file's synthetic-only-data convention; the exact real-data numbers are independently re-verified in Section 3.3/3.4 above and the packaged notebook, not in the unit-test suite):

1. `test_owt_axis_tie_resolves_to_median_and_is_order_invariant` — OWT tie with different TVDSS dependent values, proves order-invariance via a swapped-assignment construction.
2. `test_tvdss_axis_tie_resolves_to_median_and_is_order_invariant` — TVDSS tie with different OWT, same proof.
3. `test_identical_axis_and_dependent_pair_collapses_without_changing_value` / `test_exact_duplicate_axis_and_dependent_rows_are_still_counted` — identical duplicate axis/dependent pairs, including a 3-row group.
4. `test_genuine_reversal_after_grouping_raises_never_sorted_or_discarded` — a genuine reversal after grouping raises `TimeDepthError`.
5. `test_axis_conditioned_table_rejects_non_finite_independent_values` / `_rejects_non_finite_dependent_values` / `_rejects_mismatched_array_lengths` — non-finite axes and mismatched lengths rejected.
6. `test_tvdss_to_owt_never_extrapolates_outside_table_coverage` — coverage masking / no-extrapolation intact.
7. `tests/test_checkshot_inventory.py::test_axis_tie_register_rows_deterministic_and_json_serializable_no_absolute_paths` — the register builder serializes all provenance fields deterministically with no absolute paths.
8. The three specific real first-point regressions no longer occur — proven against real data in Section 3.3 and the packaged notebook's Step 11b (not in the synthetic unit-test suite, consistent with `tests/test_time_depth.py`'s own stated scope).

## 5. Output files (actual, regenerated during this verification)

Seven of Increment 4's original eight CSV/JSON outputs under `outputs/04_checkshot_time_depth/` reproduce **byte-identically** to the Increment 4 baseline (`diff -rq` against the Increment 4 build tree found zero differences for `checkshot_depth_tie_qc.csv`, `checkshot_duplicate_tie_register.csv`, `checkshot_file_inventory.csv`, `checkshot_ingestion_issues.csv`, `checkshot_velocity_summary.csv`, `sonic_checkshot_drift_summary.csv`, `time_depth_mapping_summary.csv`), and four of Increment 4's five QC figures reproduce byte-identically (`fig02`–`fig05`). Two files are genuinely new or changed:

- **`checkshot_time_axis_tie_register.csv` (NEW)** — the order-invariant TVDSS/OWT-axis tie audit register (Section 3.1); one row per `AxisTimeDepthTieRegisterEntry`, columns: `well_key`, `interpolation_direction`, `axis`, `dependent_axis`, `tie_axis_value`, `conditioned_row_indices`, `associated_depth_m`, `original_dependent_values`, `group_size`, `dependent_value_spread`, `selected_representative_dependent_value`, `conditioning_rule`, `tie_kind`, `affected_downstream_outputs`.
- **`checkshot_time_depth_manifest.json` (CHANGED)** — top-level `increment` changed from `"4"` to `"4.1"`, a new `corrective_patch_of: "4"` field added, the `scope` text rewritten to describe the corrective-patch nature, and each well's entry gained a new `axis_tie_conditioning` object (Section 3.2). Every other field (well statuses, contract results, checkshot availability, drift/mapping summaries) is unchanged.
- **`fig01_checkshot_time_depth.png` (CHANGED — label fix only, not a data change)** — the x/y axis labels were corrected from the incorrect `_source_` names to the actual plotted arrays' names, `OWT_conditioned_s` and `Depth_conditioned_m` (both explicitly annotated "Depth-tie conditioned"); the title now also says "Depth-tie conditioned" rather than leaving the conditioning basis unstated. The plotted data itself (conditioned OWT vs. Depth for all three wells) is unchanged.

Determinism was reconfirmed exactly as in Increment 4: every CSV/JSON output was regenerated from two independent root directories (the build tree and a full copy at a different absolute path) and confirmed byte-identical; `grep -rn "/home/claude"` over the entire regenerated output tree returned no matches in either root.

## 6. Locked-baseline and notebook-parity verification (actual)

- `p2mem/units.py`, `p2mem/models.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, and every existing test/fixture file outside the checkshot layer: confirmed byte-identical to the Increment 4 baseline (`diff -rq` reported zero differences for all of these).
- `02_LAS_Ingestion_and_Curve_Contracts.ipynb` and `03_Deviation_Survey_and_Depth_Framework.ipynb`: confirmed byte-identical to the Increment 4 baseline — neither notebook was opened or modified by this patch.
- `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` was rebuilt from the corrected source files (`dev_scratch_inc4_1/build_notebook_04.py`, not packaged): every `%%writefile` cell's embedded content was checked byte-for-byte against the corresponding packaged file, using exact byte decoding (no universal-newline normalization) — **21 `%%writefile` cells checked, 0 mismatches**. `nbformat.validate()` passed with 66 total cells, all carrying unique string `id` fields (66 unique ids for 66 cells). A full realistic clean-room execution smoke test (`dev_scratch_inc4_1/verify_execution_order_04.py`) ran every one of the notebook's 39 code cells in order from a fresh `/content`-style working directory populated with the locked Increment 3.1.1 foundation plus the real checkshot/deviation/LAS input files: `PROJECT_ROOT` is defined before `os.chdir(PROJECT_ROOT)`, which precedes the first `%%writefile` cell; all 21 `%%writefile` targets are relative with no `..` escape; all 39 code cells executed successfully; the in-simulation `pytest -q` subprocess reported the same `369 passed` as running pytest directly; every real-data number produced inside the simulated run (checkshot loads, depth comparison, axis-tie counts, the three regression checks, sonic drift, time mapping) matched Sections 3–5 exactly; all 9 deterministic outputs and 5 QC figures were confirmed present; and the notebook's own completion-gate cell printed all `[PASS]` entries, including the new "(4.1) Order-invariant axis-tie regression checks passed" condition, with the final working directory correctly equal to `PROJECT_ROOT`.

## 7. Changed-file list (exhaustive, exactly as diffed against the Increment 4 build tree)

**Source code (5 files):**
- `p2mem/time_depth.py` — the core fix: removed `_build_strictly_increasing_table`; added `build_axis_conditioned_lookup_table`, `build_axis_conditioned_tables_for_well`, `_group_by_exact_value`; rewrote `tvdss_to_owt`/`owt_to_tvdss`/`tvdss_to_twt`/`twt_to_tvdss`; added validation helpers `_as_1d_finite`/`_require_equal_length`/`_require_strictly_increasing`; hardened `trapezoidal_integrate`, `detect_and_condition_depth_ties`, `compare_checkshot_to_survey`, `_interp_with_coverage`, `compute_sonic_checkshot_drift`; corrected the module docstring.
- `p2mem/checkshot_models.py` — added `AxisTimeDepthTieRegisterEntry`, `AxisConditionedLookupTable` dataclasses; extended `CheckshotWellResult` with `axis_tie_entries`/`axis_tables` fields (both defaulted, backward-compatible).
- `p2mem/io/checkshot.py` — wires `build_axis_conditioned_tables_for_well` into `load_checkshot_file`; updated docstring.
- `p2mem/io/checkshot_inventory.py` — added `build_checkshot_time_axis_tie_register_rows`, `_axis_tie_conditioning_summary`; updated `build_checkshot_time_depth_manifest`'s top-level `increment`/`corrective_patch_of`/`scope` fields and each well's entry.
- `p2mem/__init__.py` — version bumped to `0.4.1`; new changelog entry documenting Increment 4.1's two corrected defects and two hardening changes.

**Tests and fixtures (4 files):**
- `tests/test_time_depth.py` — updated for the new 2-tuple `tvdss_to_owt`/`owt_to_tvdss` API; added all required axis-tie-conditioning and numerical-validation regression tests (Section 4).
- `tests/test_checkshot.py` — added end-to-end wiring tests for `load_checkshot_file`'s new fields.
- `tests/test_checkshot_inventory.py` — added tests for the new register builder and manifest summary.
- `tests/fixtures/checkshot_axis_tie.txt` (NEW) — a synthetic fixture with a genuine TVDSS-axis tie and no Depth tie, used to exercise the axis-tie path end-to-end through `load_checkshot_file` independently of the real project files.

**Documentation (3 files):**
- `README.md` — version/summary updated to reflect 0.4.1; the "two-way time" wording error in the sonic-drift finding corrected to "one-way transit time (OWT) increment"; a new "Increment 4.1 update" bullet added following the Increment 3.1 precedent; the forward/inverse interpolation bullet corrected to describe the axis-tie-conditioned lookup table rather than "disclosed handling of locally non-unique inversion."
- `INCREMENT_04_MANIFEST.md` — corrected in place (correction notice added at the top; Section 4's specific false claim corrected in place) per the Increment 3.1 precedent of amending a prior manifest's specific error without rewriting the whole document. Every other finding in that document is unaffected and unchanged.
- `INCREMENT_04_1_MANIFEST.md` (NEW, this file).

**Packaging (1 file):**
- `INCREMENT_04_1_SHA256SUMS.txt` (NEW) — see Section 8.

**Notebook (1 file):**
- `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` — rebuilt (Section 6); notebooks 02 and 03 untouched.

**Outputs (2 files, plus one changed as a byproduct):**
- `outputs/04_checkshot_time_depth/checkshot_time_axis_tie_register.csv` (NEW).
- `outputs/04_checkshot_time_depth/checkshot_time_depth_manifest.json` (CHANGED — Section 5).
- `outputs/04_checkshot_time_depth/figures/fig01_checkshot_time_depth.png` (CHANGED, label fix only — Section 5).

**Version-control-only (1 file):**
- `pyproject.toml` — version bumped to `0.4.1`.

Total: **18 changed or new packaged files** (5 + 4 + 3 + 1 + 1 + 3 + 1 above), confirmed exhaustively by `diff -rq` between the Increment 4 build tree and this deliverable's build tree (excluding build artifacts and the dev-only scratch directory in both trees) — no other packaged file differs.

## 8. Checksum ledger and packaging

`INCREMENT_04_1_MANIFEST.md` (this file) was finalized FIRST, before any checksum was computed. `INCREMENT_04_1_SHA256SUMS.txt` then records the SHA-256 of every OTHER regular file packaged in `Poseidon_1D_MEM_Increment_04_v4.1.zip`, computed from the final packaged bytes — **including this manifest's own checksum**, which is a deliberate change from the Increment 4 / 3.1 / 3.1.1 convention of excluding both the manifest and the checksum file from the ledger. `INCREMENT_04_1_SHA256SUMS.txt` excludes ONLY itself: a checksum file cannot contain the SHA-256 of its own final on-disk bytes, because writing that checksum into the file changes the file's bytes, which changes its checksum — the value would be wrong the instant it was written. This is a structural necessity for the ledger file itself, but it does NOT apply to `INCREMENT_04_1_MANIFEST.md`, which was completely finalized before the ledger was generated and whose bytes do not change afterward — only a file's own checksum is self-referential and therefore impossible to embed; a checksum of a DIFFERENT, already-finished file is not self-referential and is included normally.

The final ZIP archive's own SHA-256 (a different, external value — the hash of the `.zip` file itself, not of any file inside it) is reported separately, in the Increment 4.1 completion record and the delivery message, since it is only known once the ZIP is assembled around this manifest and the checksum ledger, and cannot be embedded in either without invalidating it.

## 9. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational 1D Mechanical Earth Model**. This patch corrects a numerical-methods and documentation defect in the existing time-depth interpolation layer; it performs no new calibration and raises no independent evidence toward a higher assurance tier. The axis-tie-conditioning median representative remains a disclosed, order-invariant, SCREENING-LEVEL choice — it is not evidence that the original TVDSS↔OWT relationship was single-valued at any tied axis value; both original rows remain fully preserved in `checkshot_time_axis_tie_register.csv`.

## 10. Known limitations (Increment 4.1-specific)

- The median representative used to resolve a tied axis value is, by construction, a disclosed choice among the tied group's dependent values — for a group of exactly 2 (every group observed in this project's real data), the median equals the arithmetic mean. This is documented, not hidden, but it remains a screening-level simplification: the underlying acquisition reason for a repeated TVDSS or OWT value at two distinct Depths is not investigated by this patch.
- No independently surveyed VSP or additional checkshot run exists to adjudicate which of a tied group's two original values is "more correct" — this patch registers both and reports a symmetric statistic, it does not adjudicate.
- All limitations disclosed in `INCREMENT_04_MANIFEST.md` (Boreas 1 / Proteus 1ST2 depth-datum offset patterns, Proteus 1ST2 identity inference, the sonic-vs-checkshot raypath difference, and every downstream-phase scope exclusion) remain fully in force and are unaffected by this patch.

## 11. Stop condition

Increment 4.1 is complete as of this manifest. Per the governing instruction for this patch: **Increment 5 has NOT been started**, and no formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, or wellbore-stability analysis has been implemented. This corrective patch is the entirety of the scope delivered here.
