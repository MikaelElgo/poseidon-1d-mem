# Increment 4.1.1 Manifest — Numerical-Validation Corrective Patch to Increment 4.1

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.4.1.1
**Corrective patch of:** Increment 4.1 (`Poseidon_1D_MEM_Increment_04_v4.1.zip`, `p2mem` 0.4.1, final ZIP SHA-256 `357f659b931449755490416aaa9f2613b2db78696aa114bec5f444ee1aef0214`)
**Date generated:** 2026-09-02

This manifest records what was actually implemented, tested, and re-verified for Increment 4.1.1. Every number in this document is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously-reported value carried over without re-confirmation. Increment 4.1.1 is a **narrowly scoped numerical-validation corrective patch only**: it does not begin Increment 5, and it implements no formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, or wellbore-stability analysis. All verified Increment 4.1 real-data results, median axis-tie representatives, outputs, figures, raw-data policies, and locked earlier-increment files are preserved exactly, except where directly affected by the corrections below (Section 3 confirms this exactly, not by assertion).

> **Increment 4.1.2 correction notice:** a real Google Colab fresh-runtime execution of `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` (as packaged in this Increment 4.1.1 deliverable) exposed two defects that Section 6 below did **not** catch, and that Section 6's language overstated the sufficiency of: (1) the real Colab run reported `1 failed, 384 passed`, not the `385 passed` this section and Section 4 report — Colab's runtime reconstructed the `%%writefile tests/fixtures/checkshot_valid.txt` cell's intentionally-CRLF fixture with LF line endings instead of CRLF, so `tests/test_checkshot.py::test_valid_file_parses_header_and_rows` failed with `assert 'LF' == 'CRLF'`; and (2) the notebook's Step 9 test-running cell was a bare `!pytest -v` shell-escape line with no exit-code check at all, so the completion gate (Section 6's "printed all ten `[PASS]` entries") was structurally incapable of ever reflecting a failing test suite — it would have printed the identical ten `[PASS]` entries whether the real test suite passed or, as it actually did in Colab, failed. Section 6's claim that "a full realistic clean-room execution smoke test... ran every one of the notebook's 41 code cells" and "the in-simulation `pytest -q` subprocess reported the same `385 passed` as running pytest directly" was an ACCURATE description of what that Linux-based, Python-`exec()`-driven simulation itself observed — but is now known to have been an **insufficient proxy for real Google Colab runtime behavior** for this one CRLF-sensitive fixture, and the simulation's own `!pytest` handling (a special-cased branch that itself checked the return code) masked the fact that the notebook's REAL Step 9 cell never checked it. Neither defect is a numerical, contract, or scientific-output defect — nothing in Sections 1–5 above is affected, and no `p2mem` source file changed. Both are corrected in Increment 4.1.2 (packaging/notebook-only; `p2mem` version unchanged at `0.4.1.1`): the CRLF fixture is now written via an explicit-bytes `Path.write_bytes()` cell (immune to any text-mode/line-ending normalization), and Step 9 now runs pytest via `subprocess.run([sys.executable, "-m", "pytest", "-v"])` with an explicit `returncode` check feeding a new, blocking completion-gate condition. See `INCREMENT_04_1_2_MANIFEST.md` for the full defect analysis and re-verification record.

---

## 1. The four blocking defects and one input-safety gap, and what was actually corrected

### 1.1 Blocking Defect 1 — hidden reversal via global exact-value grouping (corrected)

`build_axis_conditioned_lookup_table` grouped every occurrence of an identical axis value together GLOBALLY (`_group_by_exact_value`, exact-equality across the WHOLE array, not only adjacent occurrences) and only THEN checked the resulting, deduplicated array for a reversal. A reversal that returns to an already-seen value is silently absorbed by this global grouping. Concrete example: `independent_values = [100.0, 200.0, 100.0]` — the trailing `100.0` merges into the first group (both occurrences of `100.0`, indices 0 and 2, are the same group under exact-value equality regardless of position), producing a grouped array `[100.0, 200.0]` that is strictly increasing and therefore accepted, silently hiding the genuine `200 -> 100` reversal between the original indices 1 and 2. This contradicted the documented guarantee (both this project's stated policy and Increment 4.1's own Section 1.1 language) that every genuine reversal raises `TimeDepthError` and is never sorted, grouped away, discarded, or force-monotonized.

**The fix.** `build_axis_conditioned_lookup_table` now:

1. Validates `depth_conditioned_m` finite and strictly increasing on entry (new — Increment 4.1 validated `independent_values`/`dependent_values` finiteness and equal length, but not `depth_conditioned_m` itself).
2. Evaluates `np.diff(independent_values)` — the successive differences of the ORIGINAL, ungrouped axis sequence — BEFORE any grouping is attempted.
3. Raises `TimeDepthError` immediately if any difference is negative (a genuine reversal), naming the original interval index/indices.
4. Only once the original sequence is confirmed non-decreasing does it group exact ADJACENT-by-construction ties (see the proof below) and median-condition them, exactly as Increment 4.1 did.
5. Never sorts the data.

**Proof that this is both necessary and sufficient, and changes nothing for any legitimate tie.** Once step 3 passes (no negative difference exists anywhere in the original sequence — a non-decreasing sequence with ties allowed), any two occurrences of the same value are NECESSARILY adjacent: a non-adjacent repeat of a value would require the sequence to descend back down to that value after a strictly larger value was seen somewhere in between, which is exactly a negative difference — already excluded by step 3. Therefore every group `_group_by_exact_value` forms after this check passes is a contiguous run, identical in composition to what would be formed by a purely adjacent-tie grouping. This means the fix is a pure ADDITION of a missing precondition check; it does not alter which points are grouped, how they are grouped, or which representative value is selected, for any input that was already valid under Increment 4.1's stated contract.

Four required regression vectors, all independently traced by hand and confirmed by the packaged test suite (Section 4):

| Input | Expected | Reasoning |
|---|---|---|
| `[100.0, 200.0, 100.0]` | `TimeDepthError` | diffs `[100, -100]` — negative diff at index 1, a genuine reversal that returns to a seen value |
| `[100.0, 200.0, 150.0, 150.0, 300.0]` | `TimeDepthError` | diffs `[100, -50, 0, 150]` — negative diff at index 1, even though a legitimate adjacent tie (150.0, 150.0) appears immediately afterward |
| `[100.0, 100.0, 200.0]` | valid, order-invariant | diffs `[0, 100]` — no negative diff; the leading adjacent tie groups and median-conditions normally |
| `[100.0, 200.0, 200.0, 300.0]` | valid, order-invariant | diffs `[100, 0, 100]` — no negative diff; the interior adjacent tie groups and median-conditions normally |

### 1.2 Blocking Defect 2 — incomplete MD validation in sonic-checkshot drift (corrected)

`compute_sonic_checkshot_drift` validated strict MD monotonicity only INSIDE the sub-run selected by `find_longest_finite_positive_run` (the longest contiguous run of finite, strictly-positive `VP_m_s`), not across the complete canonical `md_m` array. A decreasing or duplicate MD value OUTSIDE the selected run — e.g. at a station whose `VP_m_s` happens to be `NaN`, and is therefore excluded from run-selection entirely — could pass silently, because the function's own precondition (the canonical MD index itself must be valid) was checked only on a subset of the array, not the array the function actually receives and is responsible for.

**The fix.** `compute_sonic_checkshot_drift` now requires the COMPLETE `md_m` array to be one-dimensional, finite, and strictly increasing (via the shared `_require_strictly_increasing` helper) BEFORE `find_longest_finite_positive_run` is even called — raising `TimeDepthError` for any violation anywhere in the log, not only inside the eventually-selected interval. `find_longest_finite_positive_run` itself also now validates that `md_m` and `values` are each one-dimensional and share one shape, so it does not silently misbehave on a malformed shape when called directly (it is part of the module's public API, not only an internal helper).

**Preserves the real Poseidon 2 sonic result exactly.** The real Poseidon 2 canonical `MD_m` array (31,897 samples, loaded via `p2mem.io.las.load_wells` against the real LAS file and `config/las_curve_contracts.yml`) was independently re-verified, in this deliverable, fully finite and strictly increasing across its ENTIRE length (not only the previously-verified 10,602-sample selected sonic run): minimum step `0.15229999999974098`, zero non-positive differences anywhere. This stricter check therefore changes nothing for the real data — see Section 3.4 for the bit-for-bit reproduction.

### 1.3 Blocking Defect 3 — untyped crash on zero survey-coverage overlap (corrected)

`compare_checkshot_to_survey` masked checkshot rows to those falling inside the locked survey's own MD coverage, then computed residual statistics (`min`/`max`/`mean`/`median`/RMSE) directly on the masked array. If EVERY checkshot `Depth_source_m` row fell outside that coverage, the mask selected zero rows and these NumPy reductions raised an untyped `ValueError: zero-size array to reduction operation minimum which has no identity` instead of this module's own typed `TimeDepthError` — an uninformative crash rather than a documented failure mode.

**The fix.** `compare_checkshot_to_survey` now explicitly checks `not np.any(inside)` before reaching any reduction, and raises `TimeDepthError` containing: the well key; the checkshot's own `Depth_source_m` range; the survey's MD coverage; an explicit statement that no comparison was performed; and an explicit statement that no extrapolation was attempted. No real checkshot file in this project exhibits this condition (Section 3.5 confirms all three wells' comparisons are unaffected).

### 1.4 Blocking Defect 4 — missing batch isolation for numerical failures (corrected)

`p2mem.io.checkshot.load_checkshot_surveys` caught `CheckshotFileNotFoundError`, `CheckshotParsingError`, and `CheckshotContractError` per well, but did not catch `TimeDepthError` — the exception type raised by Depth-tie conditioning, axis-tie conditioning, checkshot-vs-survey comparison, or any other numerical-validation step inside `load_checkshot_file`. A numerical defect in one well's data could therefore propagate out of the batch loader and stop every other well from loading, contradicting this project's documented batch-isolation guarantee (every other expected failure mode is isolated per well).

**The fix.** `load_checkshot_surveys` now catches `TimeDepthError` per well — a fifth, explicit, typed `except` clause alongside the three existing ones, never a blanket `except Exception` — and records a typed `CheckshotIngestionFailure(error_type="numerical_conditioning_failure", ...)`, exactly like every other expected per-well failure. `TimeDepthError` messages are built from `well_key` and numeric values only (never a file path — confirmed in Section 6's absolute-path search), so this isolation introduces no new path-leakage risk.

### 1.5 Unit-helper input-safety gap (corrected)

`seconds_to_milliseconds`/`milliseconds_to_seconds` (added in Increment 4) coerced their input directly with `np.asarray(x, dtype=np.float64)`, unlike the input-safety policy `p2mem.units` established in Increment 1 (which rejects boolean, string/bytes, and complex dtypes with `TypeError` before any numeric coercion, via a private `_reject_ambiguous_dtype` check). A boolean would be silently reinterpreted as `1.0`/`0.0`; a numeric-looking string (or string array) such as `"3.5"` would be silently parsed as a float; a complex value would be silently truncated to its real part.

**The fix.** A new, LOCAL function `_reject_ambiguous_dtype(raw, context)` is added to `p2mem/time_depth.py`, checking `raw.dtype.kind` for `"b"` (boolean), `"U"`/`"S"` (string/bytes), and `"c"` (complex) — and rejecting anything not in `("i", "u", "f")` as unsupported — with the identical checks and wording as `p2mem.units`'s private version. This is a deliberate LOCAL COPY, not a reimplementation of different behavior and not an import of a private/underscore-prefixed name across a module boundary (this project's established convention), because `p2mem/units.py` is LOCKED and is not modified by this patch. Both `seconds_to_milliseconds` and `milliseconds_to_seconds` now call this guard on `np.asarray(x)` (before dtype coercion to `float64`) and raise `TypeError` for boolean, string, or complex input, while continuing to accept valid Python numeric scalars, NumPy integer/floating arrays, and NaN exactly as before.

---

## 2. What was NOT touched

- No change to any raw checkshot, deviation, or LAS data, or to any locked module (`p2mem/units.py`, `p2mem/models.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `p2mem/checkshot_models.py`, `p2mem/io/checkshot_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, `config/checkshot_contracts.yml`).
- No change to notebooks `02_LAS_Ingestion_and_Curve_Contracts.ipynb` or `03_Deviation_Survey_and_Depth_Framework.ipynb` (byte-identical to the Increment 4.1 baseline — see Section 6).
- No change to the median axis-tie representative values, the axis-tie register content, the Depth-tie conditioning path, the velocity diagnostics, or the checkshot-vs-survey depth-comparison residuals for any of the three approved real checkshot files — all reproduce exactly (Section 3).
- No change to any of the nine Increment 4.1 CSV/JSON outputs or five QC figures — all nine/five reproduce **byte-identically** to the Increment 4.1 baseline (Section 5), because none of the five corrections above changes any success-path computation for input that was already valid; they only add missing failure-path validation and a missing typed-exception catch.
- No new scope: formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, and wellbore-stability screening remain entirely unimplemented and out of scope. Increment 5 has NOT been started.

## 3. Real-data findings — exact reproduction of every previously verified Increment 4.1 result

All values below were re-run against the real checkshot/deviation/LAS files in this deliverable, using the code actually in this deliverable, not carried over from Increment 4.1's own manifest.

### 3.1 Axis-tie register and per-well conditioning summary — unchanged

Identical to Increment 4.1's Section 3.1/3.2: 5 real axis-tie register rows (2 `identical_pair`, 3 `genuinely_non_unique`); Poseidon 2 has 2 TVDSS-axis and 2 OWT-axis tie groups; Boreas 1 has 1 TVDSS-axis and 0 OWT-axis tie groups; Proteus 1ST2 has 0 of either. Zero genuine reversals of either kind (grouped or hidden) were found in any well's real data — the Blocking Defect 1 fix changes nothing here, because the fix only strengthens rejection of an input pattern that does not occur in any of the three approved files.

### 3.2 Forward/inverse round-trip and order-dependence regression — unchanged

```
Poseidon 2  OWT=1.0319 s   -> TVDSS = 2591.3500000000004 m  (median of 2591.3/2591.4; NOT 2591.3)
Poseidon 2  TVDSS=4495.6 m -> OWT   = 1.50175 s  (median of 1.5015/1.5020; NOT 1.5015)
Boreas 1    TVDSS=3988.8 m -> OWT   = 1.35385 s  (median of 1.3531/1.3546; NOT 1.3531)
```

Independently re-verified against the actual code and data in this deliverable, exactly matching the required preservation values: Poseidon 2 OWT 1.0319 s maps to median TVDSS 2591.35 m; Poseidon 2 TVDSS 4495.6 m maps to median OWT 1.50175 s; Boreas 1 TVDSS 3988.8 m maps to median OWT 1.35385 s.

### 3.3 Poseidon 2 canonical MD array — independently re-verified fully valid across its ENTIRE length

```
n = 31897
all finite: True
min diff: 0.15229999999974098
any non-positive diff: False
```

This directly confirms the Blocking Defect 2 fix's stricter full-array validation accepts the real data unchanged.

### 3.4 Sonic-checkshot drift — bit-for-bit reproduction (full precision)

```
sonic_transit_time_s            = 0.39130683112659115
checkshot_owt_increment_s       = 0.374643076821192
sonic_minus_checkshot_ms        = 16.663754305399124
sonic_minus_checkshot_percent   = 4.447901305634517
```

Exactly matches the full-precision values required to be preserved. Selected MD interval `[2448.6448, 4064.2373]` m, n=10,602 samples — unchanged.

### 3.5 LAS-to-checkshot-time mapping — bit-for-bit reproduction

```
n_las_samples      = 31897
n_inside_coverage  = 22521
mapped_fraction    = 0.7060538608646582
n_extrapolated     = 0
```

Exactly matches the required preservation value (`mapped_fraction=0.7060538608646582`, zero extrapolated).

### 3.6 Checkshot-vs-survey depth comparison and Depth-axis ties — unchanged

Poseidon 2: n=220, max\|residual\|=0.089305 m, mean=−0.001546 m. Boreas 1: n=212, max\|residual\|=0.791865 m, mean=−0.685235 m. Proteus 1ST2: n=232, max\|residual\|=0.389789 m, mean=0.302689 m. Depth-axis duplicate-tie groups: Poseidon 2=5, Boreas 1=3, Proteus 1ST2=0. All identical to Increment 4.1's Section 3.5.

## 4. Test suite — actual results

Command: `pip install -e . --no-build-isolation --no-index --no-deps` (offline) followed by `python3 -m pytest -q`, from the increment tree.

```
385 passed in 0.65s
```

This is **16 more tests than Increment 4.1's reported 369** (read directly from the actual `pytest` output above). Breakdown by file, collected directly with `pytest --collect-only -q` against the code actually in this deliverable:

`tests/test_units.py` (94) + `tests/test_las.py` (64) + `tests/test_trajectory.py` (27) + `tests/test_deviation.py` (52) + `tests/test_depth_mapping.py` (18) + `tests/test_deviation_inventory.py` (6) + `tests/test_checkshot.py` (40) + `tests/test_time_depth.py` (67) + `tests/test_checkshot_inventory.py` (17) = **385**.

`tests/test_time_depth.py` grew from 52 to 67 (+15) and `tests/test_checkshot.py` grew from 39 to 40 (+1); every other file is unchanged from Increment 4.1's counts. Required regression coverage, confirmed present:

1. `test_hidden_reversal_returning_to_seen_value_raises` — `[100.0, 200.0, 100.0]` raises `TimeDepthError` (Blocking Defect 1, vector 1).
2. `test_hidden_reversal_with_adjacent_tie_before_it_raises` — `[100.0, 200.0, 150.0, 150.0, 300.0]` raises `TimeDepthError` (Blocking Defect 1, vector 2).
3. `test_valid_leading_adjacent_tie_remains_valid_and_order_invariant` — `[100.0, 100.0, 200.0]` remains valid and order-invariant (Blocking Defect 1, vector 3).
4. `test_valid_trailing_adjacent_tie_remains_valid_and_order_invariant` — `[100.0, 200.0, 200.0, 300.0]` remains valid and order-invariant (Blocking Defect 1, vector 4).
5. `test_axis_conditioned_table_rejects_non_finite_or_non_increasing_depth_conditioned` — the new `depth_conditioned_m` validation.
6. `test_sonic_checkshot_drift_rejects_decreasing_md_outside_selected_run` / `test_sonic_checkshot_drift_rejects_duplicate_md_outside_selected_run` — full-MD monotonicity violated OUTSIDE the selected run, with the offending station's `VP_m_s = NaN` (Blocking Defect 2).
7. `test_find_longest_finite_positive_run_rejects_non_1d_input` / `_rejects_mismatched_shapes` — direct-call shape validation for `find_longest_finite_positive_run`.
8. `test_compare_checkshot_to_survey_raises_typed_error_when_zero_rows_in_coverage` — every checkshot depth outside survey MD coverage raises `TimeDepthError` (not an untyped `ValueError`), with the message containing the well key, checkshot depth range, and survey MD coverage (Blocking Defect 3).
9. `test_batch_isolates_numerical_conditioning_failure_from_successful_wells` (in `tests/test_checkshot.py`) — a synthetic batch of one valid file (`checkshot_valid.txt`) and one file exhibiting the Blocking Defect 1 hidden-reversal pattern (new fixture `tests/fixtures/checkshot_hidden_reversal.txt`) confirms the failing well appears in `failures` with `error_type="numerical_conditioning_failure"`, the valid well still appears in `results`, and the failure message contains no absolute path (Blocking Defect 4).
10. `test_seconds_to_milliseconds_rejects_boolean_input` / `_rejects_string_input` / `_rejects_complex_input`, `test_milliseconds_to_seconds_rejects_boolean_string_complex_input`, `test_seconds_milliseconds_still_accept_valid_scalars_arrays_and_nan` — the unit-helper dtype-rejection audit (Section 1.5), demonstrating `TypeError` for boolean/string/complex input while preserving valid Python numeric scalars, NumPy numeric arrays, and NaN behavior.

All new tests use synthetic fixtures, hand-built typed objects, or small in-memory NumPy arrays only, per this project's established portability convention — none requires the real project checkshot, deviation, or LAS files.

## 5. Output files — all nine CSV/JSON outputs and five QC figures reproduce byte-identically

Every one of Increment 4.1's nine CSV/JSON outputs under `outputs/04_checkshot_time_depth/` (`checkshot_depth_tie_qc.csv`, `checkshot_duplicate_tie_register.csv`, `checkshot_file_inventory.csv`, `checkshot_ingestion_issues.csv`, `checkshot_time_axis_tie_register.csv`, `checkshot_time_depth_manifest.json`, `checkshot_velocity_summary.csv`, `sonic_checkshot_drift_summary.csv`, `time_depth_mapping_summary.csv`) and all five QC figures (`fig01_checkshot_time_depth.png` through `fig05_poseidon2_time_mapping_coverage.png`) reproduce **byte-identically** to the Increment 4.1 baseline — `diff -rq` between the two `outputs/04_checkshot_time_depth/` trees reports zero differences. This is the expected result: none of the five Increment 4.1.1 corrections changes any computation on the success path for input that was already valid; they only add missing failure-path validation (never reached by the real data, per Section 3) and a missing typed-exception catch in the batch loader.

Determinism was reconfirmed by regenerating every CSV/JSON output and figure from two independent root directories (the build tree and a full, independent copy at a different absolute path) and confirming byte-identical content in both; `grep -rn "/home/claude\|/root/\|/tmp/"` over the entire regenerated output tree, and over every packaged `.py`/`.md`/`.csv`/`.json`/`.ipynb`/`.yml`/`.toml`/`.txt` file, returned matches only inside documentation describing this very check and inside pre-existing, self-referential test-assertion strings (e.g. `tests/test_checkshot_inventory.py`'s `/home/user/secret_build_dir/...` fixtures, unchanged from Increment 4/4.1) — no actual leaked build path was found in either root.

## 6. Locked-baseline and notebook-parity verification (actual)

- `p2mem/units.py`, `p2mem/checkshot_models.py`, `p2mem/io/checkshot_inventory.py`, `p2mem/models.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, `config/checkshot_contracts.yml`, and every existing test/fixture file outside the two changed test files: confirmed byte-identical to the Increment 4.1 baseline (`diff -rq` against a fresh clean-room extraction of the actual delivered `Poseidon_1D_MEM_Increment_04_v4.1.zip` reported zero differences for all of these).
- `02_LAS_Ingestion_and_Curve_Contracts.ipynb` and `03_Deviation_Survey_and_Depth_Framework.ipynb`: confirmed byte-identical to the Increment 4.1 baseline — neither notebook was opened or modified by this patch.
- `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` was rebuilt from the corrected source files (`dev_scratch_inc4_1/build_notebook_04.py`, not packaged), adding a new Step 11c synthetic defect-regression demonstration and a tenth completion-gate condition: every `%%writefile` cell's embedded content was checked byte-for-byte against the corresponding packaged file, using exact byte decoding (no universal-newline normalization) — **22 `%%writefile` cells checked, 0 mismatches** (21 from Increment 4.1, plus the new `tests/fixtures/checkshot_hidden_reversal.txt` fixture). `nbformat.validate()` passed with 69 total cells, all carrying unique string `id` fields. A full realistic clean-room execution smoke test (`dev_scratch_inc4_1/verify_execution_order_04.py`) ran every one of the notebook's 41 code cells in order from a fresh `/content`-style working directory populated with the locked Increment 3.1.1 foundation plus the real checkshot/deviation/LAS input files: `PROJECT_ROOT` is defined before `os.chdir(PROJECT_ROOT)`, which precedes the first `%%writefile` cell; all 22 `%%writefile` targets are relative with no `..` escape; all 41 code cells executed successfully; the in-simulation `pytest -q` subprocess reported the same `385 passed` as running pytest directly; every real-data number produced inside the simulated run matched Section 3 exactly; the new Step 11c cell's five synthetic defect demonstrations all printed `[PASS]`; all 9 deterministic outputs and 5 QC figures were confirmed present; and the notebook's own completion-gate cell printed all ten `[PASS]` entries (the eight from Increment 4, the Increment 4.1 axis-tie regression check, and the new Increment 4.1.1 numerical-validation check), with the final working directory correctly equal to `PROJECT_ROOT`.

## 7. Changed-file list (exhaustive, exactly as diffed against a clean-room extraction of the delivered Increment 4.1 ZIP)

**Source code (2 files):**
- `p2mem/time_depth.py` — all four blocking-defect fixes (Section 1.1–1.4), the new local `_reject_ambiguous_dtype` helper wired into `seconds_to_milliseconds`/`milliseconds_to_seconds` (Section 1.5), and corrected docstrings (module-level and per-function).
- `p2mem/io/checkshot.py` — `load_checkshot_surveys` now catches `TimeDepthError` per well (Section 1.4); `load_checkshot_file`'s docstring clarified on the scope of "genuine axis reversal."

**Tests and fixtures (3 files):**
- `tests/test_time_depth.py` — added all Blocking Defect 1/2 regression tests, the `find_longest_finite_positive_run` shape-validation tests, the Blocking Defect 3 typed-error test, and the unit-helper dtype-rejection audit tests (Section 4).
- `tests/test_checkshot.py` — added the Blocking Defect 4 batch-isolation regression test.
- `tests/fixtures/checkshot_hidden_reversal.txt` (NEW) — a synthetic checkshot file whose TVDSS column (`95.0, 190.0, 285.0, 190.0`) reproduces the Blocking Defect 1 hidden-reversal pattern end-to-end through `load_checkshot_file`/`load_checkshot_surveys`, used by the new batch-isolation test.

**Documentation (2 files):**
- `README.md` — version/summary updated to reflect `0.4.1.1`; a new "Increment 4.1.1 update" bullet added following the Increment 3.1/4.1 precedent.
- `INCREMENT_04_1_MANIFEST.md` — corrected in place (correction notice added at the top; Section 1.1's specific incorrect statement corrected in place) per the Increment 3.1/4.1 precedent of amending a prior manifest's specific error without rewriting or concealing the rest of the document. Every other finding in that document is unaffected and unchanged.

**Packaging (1 file):**
- `INCREMENT_04_1_1_SHA256SUMS.txt` (NEW) — see Section 8.

**Manifest (1 file):**
- `INCREMENT_04_1_1_MANIFEST.md` (NEW, this file).

**Notebook (1 file):**
- `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` — rebuilt (Section 6); notebooks 02 and 03 untouched.

**Version-control-only (2 files):**
- `pyproject.toml` — version bumped to `0.4.1.1`.
- `p2mem/__init__.py` — version bumped to `0.4.1.1`; new changelog entry documenting Increment 4.1.1's five corrections.

Total: **12 changed or new packaged files** (2 + 3 + 2 + 1 + 1 + 1 + 2 above), confirmed exhaustively by `diff -rq` between a clean-room extraction of the actual delivered `Poseidon_1D_MEM_Increment_04_v4.1.zip` and this deliverable's build tree (excluding build artifacts and the dev-only, unpackaged `dev_scratch_inc4_1/` scratch directory, which is not part of either ZIP) — no other packaged file differs. No output file changed (Section 5) because none of the five corrections alters any success-path computation.

## 8. Checksum ledger and packaging

`INCREMENT_04_1_1_MANIFEST.md` (this file) was finalized FIRST, before any checksum was computed. `INCREMENT_04_1_1_SHA256SUMS.txt` then records the SHA-256 of every OTHER regular file packaged in `Poseidon_1D_MEM_Increment_04_v4.1.1.zip`, computed from the final packaged bytes — **including this manifest's own checksum**, following the same policy established in Increment 4.1: the ledger excludes ONLY itself. A checksum file cannot contain the SHA-256 of its own final on-disk bytes (writing that checksum into the file changes the file's bytes, which changes its checksum), but this manifest was completely finalized before the ledger was generated and its bytes do not change afterward — only a file's own checksum is self-referential, and a checksum of a different, already-finished file is not self-referential and is included normally.

The final ZIP archive's own SHA-256 (a different, external value — the hash of the `.zip` file itself, not of any file inside it) is reported separately, in the Increment 4.1.1 completion record and the delivery message, since it is only known once the ZIP is assembled around this manifest and the checksum ledger, and cannot be embedded in either without invalidating it. No private raw checkshot, deviation, or LAS input file is packaged in this or any prior deliverable ZIP.

## 9. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational 1D Mechanical Earth Model**. This patch corrects numerical-validation and software-QA defects in the existing time-depth interpolation and checkshot-ingestion layers; it performs no new calibration and raises no independent evidence toward a higher assurance tier. The axis-tie-conditioning median representative remains a disclosed, order-invariant, SCREENING-LEVEL choice — it is not evidence that the original TVDSS↔OWT relationship was single-valued at any tied axis value; both original rows remain fully preserved in `checkshot_time_axis_tie_register.csv`.

## 10. Known limitations (Increment 4.1.1-specific)

- The Blocking Defect 1 fix closes a specific, well-characterized gap (a reversal returning to an already-seen, non-adjacent value); it does not constitute a from-scratch formal-methods proof of `build_axis_conditioned_lookup_table`'s correctness for every conceivable input — the proof in Section 1.1 is a hand-verified argument, not a machine-checked one, though it is exhaustively tested against the four required vectors plus the pre-existing Increment 4.1 order-invariance tests.
- None of the five corrections in this patch was triggered by, or found in, any of the three approved real checkshot files or the real Poseidon 2 LAS log — every defect was identified by an independent numerical-validation audit reasoning about the code's stated contract against inputs that do not occur in this project's real data. This is disclosed, not hidden: Section 3 explicitly confirms zero real-data impact for every fix.
- All limitations disclosed in `INCREMENT_04_MANIFEST.md` and `INCREMENT_04_1_MANIFEST.md` (Boreas 1 / Proteus 1ST2 depth-datum offset patterns, Proteus 1ST2 identity inference, the sonic-vs-checkshot raypath difference, the axis-tie median-representative screening-level choice, and every downstream-phase scope exclusion) remain fully in force and are unaffected by this patch.

## 11. Stop condition

Increment 4.1.1 is complete as of this manifest. Per the governing instruction for this patch: **Increment 5 has NOT been started**, and no formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, or wellbore-stability analysis has been implemented. This corrective patch is the entirety of the scope delivered here.
