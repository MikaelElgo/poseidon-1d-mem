# Increment 5.1.1 Manifest — Further Corrective Patch to Increment 5.1

**Package version:** `p2mem` 0.5.2
**Baseline:** `Poseidon_1D_MEM_Increment_05_v5.1.zip`
**Baseline ZIP SHA-256 (stated and independently verified, exact 64-character match, no discrepancy):** `72717039617dab60ea6ce5f2664eb978dcc249a116c1700c1e84abad40521758`

This is a further, narrowly scoped corrective patch to Increment 5.1 **only**, applied after an independent technical/software-QA audit identified one remaining reconciliation edge case in the code plus three documentation-accuracy inaccuracies in `INCREMENT_05_1_MANIFEST.md`. **Increment 6 has NOT been started.** No gamma-ray normalization, shale-volume calculation, named lithology classification, density modelling, NCT fitting, pore-pressure prediction, elastic properties, rock strength, horizontal stresses, or wellbore-stability analysis is implemented anywhere in this patch. Every previously verified real Poseidon 2 / Boreas 1 formation-top result from Increment 5 / 5.1 is numerically unchanged — see Section 3. No scientific result, tolerance, depth-mapping method, or formation-top contract was changed.

---

## 1. Finding 1 — one-empty-source zero-common-marker defect (corrected)

**Defect confirmed as described.** Increment 5.1's fix correctly rejected two non-empty but disjoint marker sets, but the actual emitted condition was:

```python
if not canonical_order or (hrs_by_canon and readable_by_canon and not common_markers):
```

`canonical_order` is the **union** of the HRS and readable canonical marker names, so it is empty only when **both** sources are empty — it does not catch the case where exactly one source is empty. The second clause's `hrs_by_canon and readable_by_canon` truthy-guard requires **both** dicts to be non-empty before the intersection-emptiness check (`not common_markers`) is even evaluated — so when exactly one source is empty, that guard is `False` (Python's `and` short-circuits on the empty/falsy operand) and the whole clause is `False`, and neither branch fires. Independently reproduced: HRS empty, readable containing marker A → no `NO_COMMON_MARKERS` `ERROR`, marker A returned as a one-sided `missing_in_hrs` `NOT_COMPARABLE` entry; HRS containing marker A, readable empty → no `ERROR`, marker A returned as `missing_in_readable`; both sources empty → correctly produced `NO_COMMON_MARKERS` (this one case already worked, via the `not canonical_order` branch).

**Fix.** `p2mem/io/tops.py::reconcile_formation_top_sources` now computes the same canonical-name intersection as before, `common_markers = set(hrs_by_canon) & set(readable_by_canon)`, and raises `NO_COMMON_MARKERS` under the single, strictly-correct condition `if not common_markers:` — no truthy-guard, no separate union-emptiness branch. This one condition is provably a superset of the prior two-branch logic: it is empty (fires) in all four required zero-common-marker configurations — (1) both sources empty, (2) HRS empty / readable non-empty, (3) HRS non-empty / readable empty, (4) both non-empty and disjoint — and it is non-empty (does not fire) whenever at least one canonical marker is genuinely shared between the two sources, which is exactly the previously-established, preserved non-fatal case: a marker present in only one source remains a legitimate, auditable one-sided `NOT_COMPARABLE` entry **only** when at least one other canonical marker is genuinely shared. `load_formation_top_well()`'s pre-existing, unmodified conversion of any `ERROR`-severity reconciliation issue into a `TopSourceReconciliationError` now correctly raises for all four zero-common cases, so high-level loading can never build or map a successful well result when `NO_COMMON_MARKERS` is present. No fuzzy matching, silent renaming, dropping, sorting, or inferred correlation was introduced. This is the **only** functional code change in this patch — `p2mem/top_models.py`, `p2mem/io/tops_inventory.py`, marker canonicalization, `_check_source`, the numerical-validation preamble (`_validate_name_tuple`, `_validate_mdrt_agreement_tolerance`), and every other Increment 5.1 code path are untouched.

**Tests added (6, in `tests/test_tops.py`):**

1. `test_no_common_markers_hrs_empty_readable_nonempty` — HRS empty, readable contains marker A → `NO_COMMON_MARKERS` `ERROR` raised.
2. `test_no_common_markers_hrs_nonempty_readable_empty` — HRS contains marker A, readable empty → `NO_COMMON_MARKERS` `ERROR` raised.
3. `test_no_common_markers_both_sources_empty` — both sources empty → `NO_COMMON_MARKERS` `ERROR` raised (retained/re-confirmed).
4. `test_no_common_markers_both_nonempty_disjoint_still_rejected` — both non-empty, disjoint (Increment 5.1's original defect) → `NO_COMMON_MARKERS` `ERROR` still raised, confirming no regression from the simplified condition.
5. `test_load_formation_top_well_raises_reconciliation_error_for_one_empty_source` — high-level `load_formation_top_well()` raises `TopSourceReconciliationError` (never silently builds a successful well result) when exactly one source is empty.
6. `test_common_subset_plus_one_sided_markers_still_nonfatal_after_5_1_1` — with at least one genuinely shared marker, an additional HRS-only or readable-only marker remains a non-fatal, auditable `NOT_COMPARABLE` entry and does **not** raise — confirming the legitimate one-sided case is preserved unchanged by the simplified condition.

---

## 2. Finding 2 — baseline-hash wording correction (documentation only)

**Defect confirmed as described.** The actual Increment 5 baseline ZIP (`Poseidon_1D_MEM_Increment_05.zip`) SHA-256, computed by direct hashing, is the 64-character value `dc95d4d1af1b079bd20dac04f4aa94de84459152588b2227656f84c4d0aa8c10`. A previous governing prompt accidentally supplied a truncated 62-character string, `dc95d4d1af1b079bd20dac04f4aa94de84459152588b2227656f84c4d0aa8c` (missing the trailing two characters, `10`). The Increment 5.1 completion record stated that the actual full hash "matches the stated baseline hash" — this is mathematically impossible, since a 64-character SHA-256 digest cannot be identical to a distinct 62-character string, and the wording obscured that a truncation had occurred in the prompt.

**Correction (stated transparently, this document and the new completion record only).** Direct hashing of the real Increment 5 baseline ZIP produced the 64-character value ending `...aa8c10`. The previous governing prompt's stated hash was a two-character truncation of that same value, not a different or corrupted file. Increment 5.1's actual work was performed and independently verified against the real, full, correctly-hashed baseline ZIP throughout — the truncation existed only in one prompt's stated-hash text, never in the file that was hashed, extracted, or built from. This was a documentation/input typo, not corruption of, or uncertainty in, the baseline ZIP itself, and it had zero effect on any Increment 5.1 result. **`INCREMENT_05_MANIFEST.md` and `INCREMENT_05_1_MANIFEST.md` are locked historical records and are NOT rewritten** — this section states the corrected wording prospectively, for this document and the new Increment 5.1.1 completion record only.

---

## 3. Finding 3 — packaged-outputs wording correction (documentation only)

**Defect confirmed as described.** `INCREMENT_05_1_MANIFEST.md` Section 7 states that `outputs/` is excluded from the ZIP. This is false: direct inspection of the delivered `Poseidon_1D_MEM_Increment_05_v5.1.zip`'s file listing confirms it packages the full `outputs/` tree — 48 entries, including the locked prior-increment outputs (`outputs/02_las_inventory/`, `outputs/03_deviation_depth/` with its figures, `outputs/04_checkshot_time_depth/` with its figures) and the Increment 5 formation-top outputs and figures (`outputs/05_formation_tops/`, including all 6 CSVs, the JSON manifest, and all 3 PNG figures).

**Correction (this document only).** Output files **are** packaged in the delivered ZIP. The successful Increment 5 (and, in this patch, Increment 5.1.1) formation-top outputs remain byte-identical to their originally delivered versions — see Section 3.5 below. What is genuinely excluded from every increment's ZIP is: dev-only, never-packaged scratch directories (`dev_scratch_inc4_1/`, `dev_scratch_inc5/`, holding real private source files and dev-only build/verification scripts), build/test caches (`__pycache__/`, `.pytest_cache/`, `*.egg-info/`), and any private raw LAS/deviation/checkshot/formation-top source file (none of which is ever packaged, in `outputs/` or anywhere else). **`INCREMENT_05_1_MANIFEST.md` is a locked historical record and is NOT rewritten**; the packaged outputs themselves were not removed to make the old, incorrect statement true.

---

## 4. Finding 4 — synthetic LAS fixture wording correction (documentation only)

**Defect confirmed as described.** `INCREMENT_05_1_MANIFEST.md`'s clean-room section (item 11) states that the clean-room extraction contains no LAS file (`*.las`). This wording, read literally against the packaged tree, is inaccurate: the package intentionally includes small, fictional, portable synthetic LAS fixtures under `tests/fixtures/` (e.g. `*.las` files used by `tests/test_las.py` and related LAS-ingestion tests), which are necessary for the test suite to run standalone without any real project file.

**Correction (this document only).** The accurate claim is: **no real or private project LAS file is packaged** — nor is any real/private deviation-survey, checkshot, or formation-top source file packaged, in `outputs/`, `dev_scratch_*` (excluded entirely), or anywhere else. Small, fictional, synthetic LAS, checkshot, deviation, and formation-top **fixture** files remain intentionally packaged under `tests/fixtures/` for portable, standalone test execution, and are never real or private data. A synthetic fixture must never be described as leaked private data, and no test fixture was deleted or altered to satisfy this correction. **`INCREMENT_05_1_MANIFEST.md` is a locked historical record and is NOT rewritten.**

---

## 5. What was NOT touched

- The locked Increment 4.1.2 checkshot/time-depth layer, Increment 3.1.1 deviation-survey/depth-mapping layer (including `petrel_source_trace` and `p2mem.depth_mapping.map_las_md_to_tvd_tvdss`), and Increment 2.1.1 LAS-ingestion layer.
- `config/formation_top_contracts.yml` — re-read and confirmed unaffected; not modified.
- Marker-name canonicalization (`normalize_marker_name`, `_canon`, the alias-contract mechanism) — Finding 1's fix only changes the emptiness/intersection **check**, not how canonical names are resolved.
- `_check_source`, the per-marker reconciliation/MDRT-agreement/mapping logic, and the entire Increment 5.1 numerical-validation preamble (`_validate_name_tuple`, `_validate_mdrt_agreement_tolerance`, dimensionality/dtype/length/finiteness checks).
- `p2mem/top_models.py` (`TopIngestionFailure.failure_origin`/`hrs_path`/`readable_path`, `VALID_TOP_FAILURE_ORIGINS`) and `p2mem/io/tops_inventory.py` (`_sanitize_message`, `_failure_context_basename()`) — unchanged.
- `build_formation_top_markers`, `load_deviation_surveys`, and every other Increment 1–5.1 module not named in Section 7 below.
- Any raw LAS, deviation, checkshot, or formation-top source file — none is packaged, none is modified.
- The established real Poseidon 2 / Boreas 1 scientific results and tolerances — see Section 3 (real-data table below; note this manifest's Section 3 numbering restarts the real-data section as "Section 3" per the established per-increment manifest convention, distinct from Section 3's use above for Finding wording — see the real-data table immediately below).

---

## 6. Real-data non-regression — independently re-verified against the real approved files

Re-run via `dev_scratch_inc5/run_integration_05.py` (dev-only, not packaged) against the same four real, private approved formation-top files and the same locked Increment 3.1.1 deviation surveys used in Increment 5 / 5.1, with the Finding-1-corrected code.

| Requirement | Increment 5.1 (baseline) | Increment 5.1.1 (this patch) | Match |
|---|---|---|---|
| Poseidon 2 canonical markers | 9, all reconciled and mapped | 9, all reconciled and mapped | ✅ |
| Boreas 1 canonical markers | 10, all reconciled and mapped | 10, all reconciled and mapped | ✅ |
| Extrapolated markers (either well) | 0 | 0 | ✅ |
| MDRT-unresolved markers (either well) | 0 | 0 | ✅ |
| Poseidon 2 supplied TVDSS = MDRT − 21.8 m | 9/9 source rows, exact | 9/9 source rows, exact | ✅ |
| Poseidon 2 Plover Fm (Top Reservoir) residual | +1.6795599516581206 m | **+1.6795599516581206 m** | ✅ |
| Poseidon 2 TD residual | +2.489550739999686 m | **+2.489550739999686 m** | ✅ |
| Boreas 1 maximum absolute residual | 0.04160155999943527 m | **0.04160155999943527 m** | ✅ |
| Poseidon North 1 formation-top availability | `NOT_AVAILABLE` | `NOT_AVAILABLE` | ✅ |
| Proteus 1ST2 formation-top availability | `NOT_AVAILABLE` | `NOT_AVAILABLE` | ✅ |

All figures above were freshly, independently recomputed from the real files by the Finding-1-corrected code — never copied from Increment 5/5.1's own documentation and asserted unchanged without recomputation. This is expected: Finding 1's fix only changes behavior when the intersection of canonical markers is empty, and the real Poseidon 2 / Boreas 1 files share every one of their canonical markers between the HRS and readable representations, so the corrected code path is never exercised by real data.

### 6.5 Byte identity of successful real-data outputs

All 6 CSV outputs and the JSON manifest, regenerated by the corrected code, were compared with `cmp` against the Increment 5.1 baseline's own delivered outputs (`outputs/05_formation_tops/` extracted from `Poseidon_1D_MEM_Increment_05_v5.1.zip`): `top_availability.csv`, `top_file_inventory.csv`, `top_hrs_vs_readable_reconciliation.csv`, `top_ingestion_issues.csv`, `top_marker_register.csv`, `top_survey_corrected_markers.csv`, `formation_top_manifest.json` — **all seven byte-identical**. All 3 QC figures (`fig01_poseidon2_tvdss_residual_by_marker.png`, `fig02_boreas1_tvdss_residual_by_marker.png`, `fig03_poseidon2_boreas1_marker_depth_panel.png`) — **all three byte-identical**.

### 6.6 Absolute-path scan of regenerated outputs

`grep -rl "/home/\|/root/\|/content/"` across the regenerated `outputs/05_formation_tops/` tree (all 6 CSVs, the JSON manifest, and the figures directory) returned **zero matches**.

---

## 7. Changed-file list (exhaustive, exactly as diffed against a clean-room extraction of the Increment 5.1 baseline ZIP)

| File | Change |
|---|---|
| `p2mem/io/tops.py` | Finding 1 only — `NO_COMMON_MARKERS` condition simplified from the two-branch Increment 5.1 form to the single strictly-correct `if not common_markers:` |
| `pyproject.toml` | version `0.5.1` → `0.5.2` |
| `p2mem/__init__.py` | version bump; new Increment 5.1.1 changelog paragraph |
| `README.md` | Increment 5.1.1 status/changelog updates (header, "New in the Increment 5.1.1 corrective patch" paragraph, "Increment 5.1.1 update" bullet under Scientific limitations) |
| `tests/test_tops.py` | 6 new regression tests (Finding 1, all four zero-common configurations plus the retained common-subset-with-one-sided-markers behavior) |
| `05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb` | regenerated: `%%writefile` cells updated to the corrected `p2mem/io/tops.py`/`pyproject.toml`/`p2mem/__init__.py`/`README.md`/`tests/test_tops.py`, introductory/status/completion-gate markdown and print statements updated to reference Increment 5.1.1 and the new 482-test target |
| `dev_scratch_inc5/build_notebook_05.py` | **dev-only, not packaged** — updated to emit the above notebook changes |
| `INCREMENT_05_1_1_MANIFEST.md` | **new** (this document) |
| `INCREMENT_05_1_1_SHA256SUMS.txt` | **new** |

No other file differs from the Increment 5.1 baseline ZIP — independently confirmed by a recursive diff of a clean-room extraction of `Poseidon_1D_MEM_Increment_05_v5.1.zip` against this build tree (excluding `dev_scratch_inc4_1/`, `dev_scratch_inc5/`, `__pycache__/`, and `.pytest_cache/`, none of which are packaged or is source; `outputs/` **is** compared, per the Finding 3 correction, and is confirmed byte-identical for every successful prior-increment and Increment 5 output — see Section 6.5). `config/formation_top_contracts.yml`, `p2mem/top_models.py`, `p2mem/io/tops_inventory.py`, and all locked Increment 1–5.1 files/tests are confirmed byte-identical to the Increment 5.1 baseline. `tests/fixtures/` is unchanged — no fixture was added, removed, or modified by this patch.

---

## 8. Test suite — actual results

- Increment 5.1 baseline (freshly re-verified before any change): `pytest -q` → **476 passed**.
- After this patch: `pytest -q` → **482 passed** (476 pre-existing + 6 new, all in `tests/test_tops.py`).
- All 6 new tests are listed individually in Section 1 above, covering all four required zero-common-marker configurations, the high-level `load_formation_top_well()` raise path, and the retained common-subset-plus-one-sided-marker non-fatal behavior.
- Every one of the 439 tests pre-dating Increment 5.1, and every one of the 37 tests added by Increment 5.1, passes unchanged (476 subtotal, re-confirmed).

---

## 9. Clean-room verification (actual, performed against the final `Poseidon_1D_MEM_Increment_05_v5.1.1.zip`)

1. **Extraction safety** — `Poseidon_1D_MEM_Increment_05_v5.1.1.zip` inspected entry-by-entry before extraction (no absolute paths, no `..` path-traversal segments, no symlinks) and then extracted into a new, empty directory.
2. **Checksums** — every entry in `INCREMENT_05_1_1_SHA256SUMS.txt` (excluding the ledger's own self-reference) verified against the extracted files: **all match**.
3. **Offline editable install** — `pip install -e . --no-build-isolation --no-index --no-deps -q` from the clean-room extraction: succeeds, `p2mem.__version__ == "0.5.2"`.
4. **Full combined test suite** — `pytest -q` from the clean-room extraction: **482 passed**, zero failures, zero errors, zero skips.
5. **All four zero-common-marker cases independently re-demonstrated** — HRS empty/readable non-empty, HRS non-empty/readable empty, both empty, both non-empty and disjoint: all four raise `NO_COMMON_MARKERS`, re-run directly against the clean-room extraction's own `p2mem` install.
6. **Common-subset-plus-one-sided-marker behavior re-demonstrated** — at least one shared marker plus an additional one-sided marker remains non-fatal and auditable (`NOT_COMPARABLE`), confirmed unchanged.
7. **Readable/HRS path-leak adversarial tests rerun** — all Increment 5.1 Finding-2 sanitization tests re-verified passing (part of the 482).
8. **Numerical-validation adversarial tests rerun** — all Increment 5.1 Finding-3 validation-preamble tests re-verified passing (part of the 482).
9. **Notebook structure/source parity** — all 65 cells carry unique IDs, every code cell has `execution_count: null` and `outputs: []`; every one of the 26 `%%writefile` cell bodies compared byte-for-byte against the corresponding packaged source file in the clean-room extraction: **zero mismatches**.
10. **Notebook execution semantics** — `dev_scratch_inc5/verify_execution_order_05.py`-equivalent execution (all 42 code cells, in order, from a fresh `/content`-style working directory, real files copied in at the exact contract-required paths) run against the clean-room extraction: **all 42 cells executed successfully**, the notebook's own internal `pytest -v` subprocess reported **482 passed**, the completion gate printed all 9 `[PASS]` lines under the title `INCREMENT 5 / 5.1 / 5.1.1 COMPLETION GATE`, and the final working directory equalled `PROJECT_ROOT`.
11. **Real-data integration** — `run_integration_05.py`-equivalent rerun from the clean-room extraction against the real approved files: **SUCCESS**, reproducing every value in Section 6's table to full floating-point precision.
12. **Byte identity of outputs/figures** — all 7 CSV/JSON files and all 3 PNG figures regenerated into the clean-room extraction's own `outputs/05_formation_tops/` tree, compared with `cmp` against the Increment 5.1 baseline's own delivered outputs: **all 10 byte-identical** (Section 6.5).
13. **Absolute-path scan** — `grep -rl "/home/\|/root/\|/content/"` across the clean-room extraction's regenerated `outputs/05_formation_tops/` tree: **zero matches** (Section 6.6).
14. **Synthetic-fixture-vs-private-file distinction confirmed** — the clean-room extraction's `tests/fixtures/` contains only small, fictional, synthetic LAS/checkshot/deviation/formation-top files (Finding 4); it contains no real formation-top file (`*HRS_tops*`, `*selected_well_tops*`), no real deviation-survey file (`*_dev.txt`), no real checkshot file, and `dev_scratch_inc4_1/`/`dev_scratch_inc5/` (the dev-only directories holding the real private files) are absent from the ZIP entirely.
15. **Locked-file byte comparison vs. the Increment 5.1 baseline** — every file in the clean-room extraction other than the 9 files listed in Section 7 compared byte-for-byte against a clean-room extraction of `Poseidon_1D_MEM_Increment_05_v5.1.zip` (the Increment 5.1 baseline specifically, not Increment 5): **zero differences**, including the full `outputs/` tree (Finding 3), `p2mem/top_models.py`, `p2mem/io/tops_inventory.py`, `config/formation_top_contracts.yml`, `tests/fixtures/`, and all other locked Increment 1–5.1 files/tests.

---

## 10. Checksum ledger and packaging

`INCREMENT_05_1_1_SHA256SUMS.txt` lists the SHA-256 of every file inside `Poseidon_1D_MEM_Increment_05_v5.1.1.zip`, computed from the final packaged tree, following the established self-exclusion-only ledger policy (the ledger file lists every packaged file except itself). `dev_scratch_inc4_1/`, `dev_scratch_inc5/` (including the real, private formation-top and deviation-survey files, and the dev-only scripts `build_notebook_05.py`/`run_integration_05.py`/`verify_execution_order_05.py`), `.pytest_cache/`, `__pycache__/`, and `p2mem.egg-info/` are excluded from the ZIP. **`outputs/` is packaged** (Finding 3 correction — this differs from the incorrect Section 7 wording in `INCREMENT_05_1_MANIFEST.md`, but matches the actual packaging policy used consistently since Increment 3).

---

## 11. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational**. This patch is a defect correction to the reconciliation layer plus documentation-accuracy corrections; it does not add, remove, or reclassify any scientific method, and it does not touch any calibration status.

---

## 12. Known limitations (unchanged from Increment 5 / 5.1; no new limitation introduced)

- All Increment 5 limitations stated in `INCREMENT_05_MANIFEST.md` remain in force (both formation-top file representations for both wells remain `well_identity_evidence_status: inferred_unverified`; Poseidon North 1 and Proteus 1ST2 have no approved formation-top file; the Poseidon 2 vertical-well-assumption defect and Boreas 1 survey-consistent finding are unchanged and disclosed exactly as before).
- All Increment 5.1 limitations stated in `INCREMENT_05_1_MANIFEST.md` Section 9 remain in force (the `"mapping"` value of `TopIngestionFailure.failure_origin` remains reserved but unreachable).
- No new limitation is introduced by Increment 5.1.1: Finding 1's fix is strictly a correctness fix with no new caveat, and Findings 2–4 are wording corrections with no functional effect.

---

## 13. Stop condition

Increment 5.1.1 is complete. This patch corrects exactly the one code finding and three documentation findings identified by the independent audit above, adds the mandatory regression tests, re-verifies every real-data non-regression requirement to full floating-point precision, and reproduces byte-identical successful outputs/figures. **Increment 6 (or any petrophysics/pore-pressure/mechanical-properties/stress/wellbore-stability work) has NOT been started.** No scientific result, tolerance, depth-mapping method, formation-top contract, or real-data output was changed anywhere in this patch. Per the governing instruction, this increment stops here.
