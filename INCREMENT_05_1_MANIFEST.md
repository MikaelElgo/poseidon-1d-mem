# Increment 5.1 Manifest — Corrective Patch to Increment 5

**Package version:** `p2mem` 0.5.1
**Baseline:** `Poseidon_1D_MEM_Increment_05.zip`
**Baseline ZIP SHA-256:** `dc95d4d1af1b079bd20dac04f4aa94de84459152588b2227656f84c4d0aa8c10` (independently verified against the stated baseline hash `dc95d4d1af1b079bd20dac04f4aa94de84459152588b2227656f84c4d0aa8c` before any change was made)

This is a corrective patch to Increment 5 **only**, applied after an independent technical/software-QA audit identified four defects. **Increment 6 has NOT been started.** No gamma-ray normalization, shale-volume calculation, named lithology classification, density modelling, NCT fitting, pore-pressure prediction, elastic properties, rock strength, horizontal stresses, or wellbore-stability analysis is implemented anywhere in this patch. Every previously verified real Poseidon 2 / Boreas 1 formation-top result from Increment 5 is numerically unchanged — see Section 3.

---

## 1. The four audit findings, and what was actually corrected

### 1.1 Finding 1 — zero-common-marker logic defect (corrected)

**Defect confirmed as described.** `reconcile_formation_top_sources()`'s docstring for `TopSourceReconciliationError` already documented "zero canonical markers in common between the two sources" as one of three fatal conditions, but the actual emptiness check tested `canonical_order` — a **union** of the HRS canonical names and any readable-only canonical names — rather than their intersection. `canonical_order` is empty only when **both** sources are completely empty, never when the two sources are simply disjoint. Concretely, HRS markers `{A, B}` and readable markers `{X, Y}` produced zero `ERROR` issues and four one-sided `NOT_COMPARABLE` reconciliation entries — an apparently valid, but scientifically meaningless, reconciliation of two entirely unrelated marker sets.

**Fix.** `p2mem/io/tops.py::reconcile_formation_top_sources` now explicitly computes `common_markers = set(hrs_by_canon) & set(readable_by_canon)` (the canonical-name intersection, evaluated **after** normalization/alias resolution — the same `_canon()` resolution already used to build `hrs_by_canon`/`readable_by_canon`) and raises the `NO_COMMON_MARKERS` `ERROR` whenever `canonical_order` is empty (both sources empty — the pre-existing behavior, preserved) **or** both sources are non-empty and `common_markers` is empty (the corrected condition). The pre-existing union-based construction of `canonical_order` itself — used to build the actual `TopReconciliationEntry` list when at least one marker is genuinely shared — is unchanged, so a legitimate one-sided marker (HRS-only or readable-only, alongside at least one shared marker) remains the pre-existing, non-fatal `NOT_COMPARABLE` case. `load_formation_top_well()` already converts any `ERROR`-severity reconciliation issue into a `TopSourceReconciliationError` (unchanged code path), so it now correctly raises for the disjoint-sources condition. No fuzzy matching, silent renaming, dropping, sorting, or inferred correlation was introduced.

### 1.2 Finding 2 — readable-file absolute-path leakage (corrected)

**Defect confirmed as described.** Every one of the four `except` blocks in `load_formation_top_surveys()` (`TopFileNotFoundError`, `TopParsingError`, `TopContractError`, `TopSourceReconciliationError`) unconditionally recorded `hrs_path` — never `readable_path` — as `TopIngestionFailure.source_path`, regardless of which file or stage of `load_formation_top_well()` actually raised. `p2mem.io.tops_inventory._sanitize_message(message, source_path)` stripped only that one (potentially wrong) path via literal string replacement, so a failure genuinely originating from the "selected readable" file (a missing file, malformed content, or a contract mismatch) could leak that file's own absolute path, unsanitized, into `build_top_issues_rows()`, `build_top_availability_rows()`, and `build_formation_top_manifest()`.

**Fix.**
- `p2mem/top_models.py::TopIngestionFailure` gained three new fields, all with backward-compatible defaults: `failure_origin: str = "unknown"` (one of the new `VALID_TOP_FAILURE_ORIGINS = ("hrs", "readable", "reconciliation", "mapping", "unknown")`), `hrs_path: Optional[str] = None`, `readable_path: Optional[str] = None`. `source_path` is retained unchanged for backward compatibility and is now always set to the path judged most representative of the failure (the HRS path for an "hrs"-origin failure, the readable path for a "readable"-origin failure).
- `p2mem/io/tops.py::load_formation_top_well()` now tags each exception with the stage that actually raised it — via a small `_tag(exc, origin)` helper that sets `exc.failure_origin` and `exc.hrs_path`/`exc.readable_path` before the exception propagates — around each of the four stages: HRS parse/read ("hrs"), HRS contract resolution ("hrs"), readable parse/read ("readable"), readable contract resolution ("readable"), and source reconciliation ("reconciliation"). ("mapping" is reserved in the vocabulary for completeness; no fatal exception currently originates from the mapping stage, since `build_formation_top_markers()` reports out-of-coverage/unresolved markers as disclosed, non-fatal statuses rather than raising.)
- `load_formation_top_surveys()`'s exception handlers now read `getattr(exc, "failure_origin", "unknown")` and construct `TopIngestionFailure` with both `hrs_path` and `readable_path` always populated, and `source_path` set from the correctly identified origin.
- `p2mem/io/tops_inventory.py::_sanitize_message` is now variadic (`_sanitize_message(message, *source_paths)`), sanitizing every path given via literal substring replacement only (never a regex) — never only the single path recorded in `source_path`. A new `_failure_context_basename()` helper picks the correct basename from `failure_origin` (the HRS basename for "hrs", the readable basename for "readable"; both basenames joined with `+` for "reconciliation"/"mapping", since neither file individually failed; falls back to `source_path`'s basename for a `TopIngestionFailure` built without this classification, preserving old behavior for any pre-existing caller). `build_top_issues_rows`, `build_top_availability_rows`, `build_formation_top_manifest`, and `build_top_file_inventory_rows`'s failure-row branch all now sanitize `hrs_path`, `readable_path`, and `source_path` together, and report the corrected context/basename.

Backward compatibility: every existing call site and every pre-existing test that constructs a `TopIngestionFailure` with only the original five positional/keyword fields continues to work unchanged (the three new fields default to `"unknown"`/`None`/`None`), and `_sanitize_message`'s pre-existing two-argument call form still works (the second positional argument is captured by `*source_paths`).

### 1.3 Finding 3 — incomplete caller-supplied numerical validation (corrected)

**Defect confirmed as described**, exactly as enumerated in the audit: HRS MDRT containing `NaN` was accepted (silently reaching `MDRT_MISMATCH` classification downstream); readable MDRT containing `Inf` was accepted; readable TVDSS containing `NaN` was accepted; a shorter `NOTE_source` tuple than `TOP_NAME_source`/`MDRT_source_m`/`TVDSS_source_m` produced an untyped `IndexError` deep inside the reconciliation loop (since `NOTE_source` length was never included in the readable length-consistency check); `mdrt_agreement_tolerance_m=np.nan`, a negative tolerance, and a boolean tolerance were all accepted and used directly in a numeric comparison; a string tolerance reached an incidental Python `TypeError` only because string-versus-float comparison happens to raise, not because of any deliberate validation.

**Fix.** `p2mem/io/tops.py::reconcile_formation_top_sources()`'s validation preamble now performs, in order, before any reconciliation or numerical comparison:

1. **Type and dimensionality** — each of `hrs_raw.MDRT_source_m`, `readable_raw.MDRT_source_m`, `readable_raw.TVDSS_source_m` must be a NumPy `ndarray` (`TopParsingError` otherwise) and 1-dimensional (`TopParsingError` otherwise).
2. **Dtype class** — the pre-existing `_reject_ambiguous_dtype` check (boolean/string-bytes/complex/object → `TypeError`) is applied to all three arrays, now gated to run before length/value checks.
3. **Length consistency** — HRS name-vs-MDRT length (pre-existing), and the readable-side check now includes **all four** of `TOP_NAME_source`, `MDRT_source_m`, `TVDSS_source_m`, **and `NOTE_source`** (previously only the first three) — a mismatch of any of the four raises `TopParsingError` before the reconciliation loop is ever entered, eliminating the untyped `IndexError`.
4. **Name/note element types** — a new `_validate_name_tuple()` helper rejects (with `TopParsingError`) any non-`str` element in `Top_Name_source`, `TOP_NAME_source`, or `NOTE_source`.
5. **Finiteness and non-negativity** — HRS MDRT and readable MDRT must be entirely finite and non-negative (`TopParsingError` otherwise, mirroring the file-parser's pre-existing per-row check, now enforced for the in-memory API too); readable TVDSS must be entirely finite (`TopParsingError` otherwise — TVDSS is a signed quantity so no non-negativity constraint applies).
6. **Tolerance validation** — a new `_validate_mdrt_agreement_tolerance()` helper rejects boolean, string/bytes, and complex values with `TypeError` (a type-class defect, mirroring `_reject_ambiguous_dtype`'s split); rejects non-finite (`NaN`/`Inf`) and negative values with `TopParsingError` (a value defect); accepts valid Python `int`/`float` and NumPy integer/floating scalars, including a 0-d or size-1 NumPy array, returning a plain Python `float`.

All six checks use deliberate, documented exception types (`TopParsingError` for a structural/value defect, `TypeError` for a type-class defect — matching this module's pre-existing split) — never an incidental `IndexError`, NumPy broadcasting error, or bare comparison `TypeError`.

### 1.4 Finding 4 — verification-language correction (corrected in this document only)

**Defect confirmed as described.** `INCREMENT_05_MANIFEST.md` Section 6, item 7 states: *"No absolute path (`/home/`, `/root/`, `/content/`, or any container-specific path) found anywhere in the packaged source, tests, config, notebook, or regenerated outputs."* This is overbroad and literally inaccurate: `tests/test_checkshot_inventory.py`, `tests/test_deviation_inventory.py`, and this patch's own `tests/test_tops_inventory.py` all intentionally contain fake absolute-path strings (e.g. `/home/user/secret_build_dir/...`, `/home/private_build/...`) as deliberate test inputs used to verify the sanitizer — this is the same finding pattern already documented for prior increments (`INCREMENT_03_1_MANIFEST.md`, `INCREMENT_04_1_1_MANIFEST.md`, `INCREMENT_04_1_2_MANIFEST.md`). `INCREMENT_05_MANIFEST.md`'s own Section 6, item 1 states the narrower, accurate claim ("No absolute path ... appears in any output CSV or JSON") correctly; only item 7's broader claim was wrong.

**Correction (this document, not the locked Increment 5 manifest).** The accurate, narrowly scoped claim is: **no environment-dependent build path appears in any exported CSV/JSON output** (see Section 3.5/3.6 below for the actual verification). Intentional synthetic absolute-path strings exist in test files and in historical increment documentation as deliberate test inputs and audit narrative — they are never leaked runtime paths, and their presence does not indicate a defect. **`INCREMENT_05_MANIFEST.md` itself is a locked historical record and is NOT rewritten** — this manifest supersedes it only for the purpose of stating the corrected, precise claim going forward.

---

## 2. What was NOT touched

- The locked Increment 4.1.2 checkshot/time-depth layer, Increment 3.1.1 deviation-survey/depth-mapping layer (including `petrel_source_trace` and `p2mem.depth_mapping.map_las_md_to_tvd_tvdss`, both reused unmodified), and Increment 2.1.1 LAS-ingestion layer.
- `config/formation_top_contracts.yml` — re-read and confirmed unaffected by any of the four findings; not modified.
- Marker-name canonicalization (`normalize_marker_name`, `_canon`, the alias-contract mechanism) — Finding 1's fix only changes the emptiness/intersection **check**, not how canonical names are resolved.
- `_check_source` (duplicate-name/order-reversal QC) and the per-marker reconciliation/MDRT-agreement/mapping logic beyond the new validation preamble.
- `build_formation_top_markers`, `load_deviation_surveys`, and every other Increment 1–5 module not named in Section 4 below.
- Any raw LAS, deviation, checkshot, or formation-top source file — none is packaged, none is modified.
- The established real Poseidon 2 / Boreas 1 scientific results and tolerances — see Section 3.

---

## 3. Real-data non-regression — independently re-verified against the real approved files

Re-run via `dev_scratch_inc5/run_integration_05.py` (dev-only, not packaged) against the same four real, private approved formation-top files and the same locked Increment 3.1.1 deviation surveys used in Increment 5, with the corrected code.

| Requirement | Increment 5 (baseline) | Increment 5.1 (this patch) | Match |
|---|---|---|---|
| Poseidon 2 canonical markers | 9, all reconciled and mapped | 9, all reconciled and mapped | ✅ |
| Boreas 1 canonical markers | 10, all reconciled and mapped | 10, all reconciled and mapped | ✅ |
| Extrapolated markers (either well) | 0 | 0 | ✅ |
| MDRT-unresolved markers (either well) | 0 | 0 | ✅ |
| Poseidon 2 supplied TVDSS = MDRT − 21.8 m | 9/9 source rows, exact | 9/9 source rows, exact | ✅ |
| Poseidon 2 Plover Fm (Top Reservoir) residual | +1.6795599517 m | **+1.6795599516581206 m** | ✅ |
| Poseidon 2 TD residual | +2.4895507400 m | **+2.489550739999686 m** | ✅ |
| Boreas 1 maximum absolute residual | 0.0416015600 m | **0.04160155999943527 m** | ✅ |
| Poseidon North 1 formation-top availability | `NOT_AVAILABLE` | `NOT_AVAILABLE` | ✅ |
| Proteus 1ST2 formation-top availability | `NOT_AVAILABLE` | `NOT_AVAILABLE` | ✅ |

All figures above were freshly, independently recomputed from the real files by the corrected code — never copied from Increment 5's own documentation and asserted unchanged without recomputation.

### 3.5 Byte identity of successful real-data outputs

All 6 CSV outputs and the JSON manifest, regenerated by the corrected code, were compared with `cmp` against the Increment 5 baseline's own delivered outputs: `top_availability.csv`, `top_file_inventory.csv`, `top_hrs_vs_readable_reconciliation.csv`, `top_ingestion_issues.csv`, `top_marker_register.csv`, `top_survey_corrected_markers.csv`, `formation_top_manifest.json` — **all seven byte-identical**. All 3 QC figures (`fig01_poseidon2_tvdss_residual_by_marker.png`, `fig02_boreas1_tvdss_residual_by_marker.png`, `fig03_poseidon2_boreas1_marker_depth_panel.png`) — **all three byte-identical**. No output changed, because none of the three code findings touch any successful, non-failure, fully-reconciled real-data code path — they change only the disjoint-sources rejection path (never exercised by the real files, which share every canonical marker), the failure/path-sanitization path (never exercised, since the real files ingest successfully), and the in-memory validation preamble (the real, file-parsed arrays already satisfy every new check).

### 3.6 Absolute-path scan of regenerated outputs

`grep -rl "/home/\|/root/\|/content/"` across the regenerated `outputs/05_formation_tops/` tree (all 6 CSVs, the JSON manifest, and the figures directory) returned **zero matches** — confirming the precise Section 1.4 claim.

---

## 4. Changed-file list (exhaustive, exactly as diffed against a clean-room extraction of the Increment 5 baseline ZIP)

| File | Change |
|---|---|
| `p2mem/top_models.py` | `TopIngestionFailure` gained `failure_origin`, `hrs_path`, `readable_path` (all backward-compatible defaults); added `VALID_TOP_FAILURE_ORIGINS` |
| `p2mem/io/tops.py` | Finding 1 (intersection-based `NO_COMMON_MARKERS` check), Finding 3 (validation preamble: dimensionality, dtype, length incl. `NOTE_source`, name/note element types, finiteness/non-negativity, tolerance validation via new `_validate_name_tuple`/`_validate_mdrt_agreement_tolerance` helpers), Finding 2 (`load_formation_top_well` origin-tagging via `_tag()`, `load_formation_top_surveys` origin-aware `TopIngestionFailure` construction) |
| `p2mem/io/tops_inventory.py` | Finding 2 (`_sanitize_message` made variadic, new `_failure_context_basename()` helper, all builder functions updated to sanitize both `hrs_path`/`readable_path`) |
| `pyproject.toml` | version `0.5.0` → `0.5.1` |
| `p2mem/__init__.py` | version bump; new Increment 5.1 changelog paragraph |
| `README.md` | Increment 5.1 status/changelog updates (header, "New in the Increment 5.1 corrective patch" bullet, "Increment 5.1 update" bullet under Scientific limitations) |
| `tests/test_tops.py` | 31 new regression tests (Findings 1–3, plus readable-format-equivalent malformed/nonfinite/negative-MDRT coverage) |
| `tests/test_tops_inventory.py` | 6 new regression tests (Finding 2 builder-level sanitization) |
| `tests/fixtures/top_hrs_disjoint_markers.txt` | **new** — two markers (`Marker X`, `Marker Y`) sharing nothing with `top_readable_valid.txt`'s markers, for Finding 1 coverage |
| `tests/fixtures/top_readable_malformed_numeric.txt` | **new** — readable-format equivalent of `top_hrs_malformed_numeric.txt` |
| `tests/fixtures/top_readable_nonfinite.txt` | **new** — readable-format equivalent of `top_hrs_nonfinite.txt` |
| `tests/fixtures/top_readable_negative_depth.txt` | **new** — readable-format equivalent of `top_hrs_negative_depth.txt` |
| `05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb` | regenerated: `%%writefile` cells updated to the corrected sources above, 4 new fixture `%%writefile` cells added, introductory/status markdown updated for the 5.1 patch and the new 476-test target |
| `dev_scratch_inc5/build_notebook_05.py` | **dev-only, not packaged** — updated to emit the above notebook changes |
| `INCREMENT_05_1_MANIFEST.md` | **new** (this document) |
| `INCREMENT_05_1_SHA256SUMS.txt` | **new** |

No other file differs from the Increment 5 baseline ZIP — independently confirmed by a recursive diff of a clean-room extraction of `Poseidon_1D_MEM_Increment_05.zip` against this build tree (excluding `dev_scratch_inc4_1/`, `dev_scratch_inc5/`, `outputs/`, `__pycache__/`, and `.pytest_cache/`, none of which are packaged or is source). `config/formation_top_contracts.yml` and all locked Increment 1–4.1.2 files/tests are confirmed byte-identical to the baseline.

---

## 5. Test suite — actual results

- Increment 5 baseline (freshly re-verified before any change): `pytest -q` → **439 passed**.
- After this patch: `pytest -q` → **476 passed** (439 pre-existing + 37 new: 31 in `tests/test_tops.py`, 6 in `tests/test_tops_inventory.py`).
- Every one of the 12 mandatory regression-test categories is covered:

  1. Disjoint non-empty sources → `NO_COMMON_MARKERS`: `test_disjoint_nonempty_sources_produce_no_common_markers_error`.
  2. High-level loading raises `TopSourceReconciliationError`: `test_load_formation_top_well_raises_reconciliation_error_for_disjoint_sources`.
  3. Common subset + one-sided markers remains auditable/nonfatal: `test_common_subset_plus_one_sided_markers_remains_auditable_nonfatal`.
  4. Missing/malformed/contract-failing readable paths cannot leak: `test_batch_missing_readable_file_reports_readable_origin_and_both_paths`, `test_batch_malformed_readable_file_reports_readable_origin`, `test_batch_readable_contract_failure_reports_readable_origin`, plus `test_issues_rows_sanitize_readable_origin_failure_path`, `test_availability_rows_sanitize_readable_origin_failure_path`, `test_manifest_sanitizes_readable_origin_failure_path`, `test_file_inventory_rows_sanitize_readable_origin_failure_context`.
  5. HRS failure-path sanitization remains correct: `test_batch_hrs_failure_still_reports_hrs_origin_and_sanitizes_correctly`, `test_hrs_origin_failure_still_sanitizes_and_identifies_hrs_context`.
  6. NaN/Inf arrays rejected: `test_reconcile_rejects_nan_in_hrs_mdrt`, `test_reconcile_rejects_inf_in_readable_mdrt`, `test_reconcile_rejects_nan_in_readable_tvdss`.
  7. Negative MDRT rejected: `test_reconcile_rejects_negative_hrs_mdrt`.
  8. Non-1D arrays rejected: `test_reconcile_rejects_non_1d_array`.
  9. NOTE/name/numeric-array length mismatches rejected with typed errors: `test_reconcile_rejects_shorter_note_source_with_typed_error_not_indexerror` (and the pre-existing `test_reconcile_rejects_mismatched_array_lengths`, re-verified still passing).
  10. Invalid tolerance types/values rejected: `test_reconcile_rejects_invalid_tolerance_values` (parametrized: NaN, Inf, -Inf, -0.01), `test_reconcile_rejects_invalid_tolerance_types` (parametrized: bool True/False, str, bytes, complex).
  11. Valid scalar/array inputs unaffected: `test_reconcile_accepts_valid_tolerance_scalars_and_arrays` (parametrized: Python float/int, `np.float64`, `np.int32`, 0-d array, size-1 array).
  12. All existing Increment 1–5 tests still pass: confirmed by the 439/476 counts above — every one of the 439 pre-existing tests passes unchanged.

  Additional, explicitly requested readable-parser coverage: `test_readable_malformed_or_nonfinite_or_negative_depth_rejected` (parametrized over the three new readable fixtures — this format-equivalent coverage was confirmed absent before this patch; only HRS-format fixtures existed for these three conditions).
  Additional reconciliation-origin coverage (beyond the mandatory list, since Finding 2's vocabulary includes "reconciliation"): `test_reconciliation_origin_failure_context_combines_both_basenames`.

---

## 6. Clean-room verification (actual, performed against the final `Poseidon_1D_MEM_Increment_05_v5.1.zip`)

1. **Extraction** — `Poseidon_1D_MEM_Increment_05_v5.1.zip` extracted into a new, empty directory.
2. **Checksums** — every entry in `INCREMENT_05_1_SHA256SUMS.txt` (excluding the ledger's own self-reference) verified against the extracted files: **all match**.
3. **Offline editable install** — `pip install -e . --no-build-isolation --no-index --no-deps -q` from the clean-room extraction: succeeds, `p2mem.__version__ == "0.5.1"`.
4. **Full combined test suite** — `pytest -q` from the clean-room extraction: **476 passed**, zero failures, zero errors, zero skips.
5. **Notebook structure/source parity** — all 65 cells carry unique IDs, every code cell has `execution_count: null` and `outputs: []`; every one of the 26 `%%writefile` cell bodies compared byte-for-byte against the corresponding packaged source file in the clean-room extraction: **zero mismatches**.
6. **Notebook execution semantics** — `dev_scratch_inc5/verify_execution_order_05.py`-equivalent execution (all 42 code cells, in order, from a fresh `/content`-style working directory, real files copied in at the exact contract-required paths) run against the clean-room extraction: **all 42 cells executed successfully**, the notebook's own internal `pytest -v` subprocess reported **476 passed**, the completion gate printed all 9 `[PASS]` lines, and the final working directory equalled `PROJECT_ROOT`.
7. **Real-data integration** — `run_integration_05.py`-equivalent rerun from the clean-room extraction against the real approved files: **SUCCESS**, reproducing every value in Section 3's table.
8. **Output/figure regeneration** — all 6 CSVs, the JSON manifest, and all 3 PNG figures regenerated into the clean-room extraction's own `outputs/05_formation_tops/` tree.
9. **Byte identity vs. Increment 5** — every regenerated output from step 8 compared with `cmp` against the Increment 5 baseline's own delivered outputs: **all 7 CSV/JSON files and all 3 figures byte-identical** (Section 3.5).
10. **Absolute-path scan** — `grep -rl "/home/\|/root/\|/content/"` across the clean-room extraction's regenerated `outputs/05_formation_tops/` tree: **zero matches** (Section 3.6).
11. **No raw private files packaged** — the clean-room extraction contains no formation-top file (`*HRS_tops*`, `*selected_well_tops*`), no deviation-survey file (`*_dev.txt`), no LAS file (`*.las`), and no checkshot file; `dev_scratch_inc4_1/` and `dev_scratch_inc5/` (the dev-only directories holding the real private files) are absent from the ZIP entirely.
12. **Locked-file byte comparison** — every file in the clean-room extraction other than the 15 files listed in Section 4 compared byte-for-byte against a clean-room extraction of the Increment 5 baseline ZIP: **zero differences** (recursive `diff -rq`, both trees with their respective dev-only/output/cache directories excluded from the comparison since neither ZIP packages them).

---

## 7. Checksum ledger and packaging

`INCREMENT_05_1_SHA256SUMS.txt` lists the SHA-256 of every file inside `Poseidon_1D_MEM_Increment_05_v5.1.zip`, computed from the final packaged tree, following the established self-exclusion-only ledger policy (the ledger file lists every packaged file except itself). `dev_scratch_inc4_1/`, `dev_scratch_inc5/` (including the real, private formation-top and deviation-survey files, and the three dev-only scripts `build_notebook_05.py`/`run_integration_05.py`/`verify_execution_order_05.py`), `.pytest_cache/`, `__pycache__/`, `p2mem.egg-info/`, and `outputs/` are excluded from the ZIP — identical exclusion policy to Increment 5.

---

## 8. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational**. This patch is a defect correction to the ingestion/reconciliation/validation/export layer; it does not add, remove, or reclassify any scientific method, and it does not touch any calibration status.

---

## 9. Known limitations (unchanged from Increment 5; Increment 5.1-specific limitations noted)

- All Increment 5 limitations stated in `INCREMENT_05_MANIFEST.md` remain in force (both formation-top file representations for both wells remain `well_identity_evidence_status: inferred_unverified`; Poseidon North 1 and Proteus 1ST2 have no approved formation-top file; the Poseidon 2 vertical-well-assumption defect and Boreas 1 survey-consistent finding are unchanged and disclosed exactly as before).
- Increment 5.1-specific: the `"mapping"` value of `TopIngestionFailure.failure_origin` / `VALID_TOP_FAILURE_ORIGINS` is reserved for architectural completeness (per the audit's own four-way vocabulary requirement) but is not currently reachable — no fatal exception originates from the survey-mapping stage in the current control flow, since `build_formation_top_markers()` reports out-of-coverage/unresolved markers as disclosed, non-fatal statuses. This is documented, not silently assumed.

---

## 10. Stop condition

Increment 5.1 is complete. This patch corrects exactly the four independently audited findings above, adds the mandatory regression tests, re-verifies every real-data non-regression requirement to the requested precision, and reproduces byte-identical successful outputs/figures. **Increment 6 (or any petrophysics/pore-pressure/mechanical-properties/stress/wellbore-stability work) has NOT been started.** Per the governing instruction, this increment stops here to await independent audit.
