# Increment 3.1 Manifest — Corrective Patch to Increment 3

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.3.1
**Corrects:** Increment 3 (`p2mem` 0.3.0, `Poseidon_1D_MEM_Increment_03.zip`) — see `INCREMENT_03_MANIFEST.md`, packaged unmodified alongside this manifest except for one factual filename correction (Section 1, finding 1).
**Scope:** This is a controlled corrective patch to Increment 3 ONLY, applied in response to an independent technical audit. No Increment 4 work (checkshot, time-depth, formation tops, petrophysics, pore pressure, mechanical properties, stress modelling, or wellbore-stability) was performed, started, or is included here.
**Date generated:** 2026-09-01

This manifest records what was actually corrected, tested, and re-verified for Increment 3.1. Every number below is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously reported value carried over without re-confirmation.

---

## 1. The four audit findings and what was actually corrected

### Finding 1 — Source-filename defect (Colab/Drive lookup failure)

Increment 3 keyed the four deviation-survey files with underscores substituted for spaces (`Poseidon_2_dev.txt`, `Boreas_1_dev.txt`, `Poseidon_North_1_dev.txt`, `Proteus_1ST2_dev.txt`). The real files, as they exist in the project's Google Drive, carry literal spaces: `Poseidon 2_dev.txt`, `Boreas 1_dev.txt`, `Poseidon North 1_dev.txt`, `Proteus 1ST2_dev.txt`. Since contract resolution in `p2mem/io/deviation.py` performs an exact filename match, the underscored keys would never have resolved against the real files.

**Corrected in:**
- `config/deviation_survey_contracts.yml` — the four top-level YAML keys are now the exact, literal, space-containing filenames.
- `03_Deviation_Survey_and_Depth_Framework.ipynb` — the notebook's `DEV_FILES` dict values (Step 4) are now the exact space-containing filenames; the accompanying markdown text and the phase-header corrective-patch note were updated to match.
- `tests/test_deviation.py` — added `test_real_filenames_with_spaces_resolve_successfully` (parametrized over all four real filenames, using `pytest`'s `tmp_path` fixture — no permanent fixture files added) proving each resolves cleanly, and `test_underscore_renamed_filename_does_not_silently_match_contract` proving an underscore-substituted filename is rejected with `FILENAME_MISMATCH`, not silently accepted.
- `INCREMENT_03_MANIFEST.md` — Section 3's source-filename table corrected in place (a factual documentation error; file content bytes and SHA-256 values are unaffected — see the correction notice added at the top of that document).
- `run_integration_03.py` (development-only orchestration script, not packaged) — re-pointed at the four real filenames for this session's real-data re-verification (see Section 4 below for why a dev-only verification-copy directory was needed, and its explicit disclosure).

**Not changed:** internal well-key dict keys (`Poseidon_2`, `Boreas_1`, `Poseidon_North_1`, `Proteus_1ST2`) remain underscored everywhere they were already underscored — they are Python-identifier-friendly internal keys, never used for filename lookup, and were never part of this defect.

No raw deviation file was renamed, rewritten, copied, or packaged as part of this correction — the code was corrected to accept the files' actual names, not the other way around.

### Finding 2 — Environment-specific absolute paths in exported outputs

Two diagnostic fields (a failure's `error_message`, and every row's `context`/`source_filename`) could embed a full, environment-dependent absolute build path (e.g. a Colab Drive-mount path or a local build directory) rather than just the file's basename.

**Corrected in:**
- `p2mem/io/deviation.py` (`resolve_deviation_contract`) — the `context` argument passed to every `err()`/`warn()` call now uses `header.source_filename` (a basename, already resolved from the contract lookup) instead of `header.source_path` (a full path).
- `p2mem/io/deviation_inventory.py` — added a `_sanitize_message()` helper (basename substring-replaces any embedded absolute path) applied to every exported `error_message`/`message` field; `source_filename` fields now use `Path(f.source_path).name` instead of `f.source_path.split("/")[-1]` (equivalent on POSIX, but explicit and portable).
- `tests/test_deviation_inventory.py` (**new file**) — six synthetic-fixture tests proving no row built by this module, for a successful well OR a failed one, ever embeds a fake absolute path injected into the underlying `source_path`/`message` fields.

**Not changed:** runtime-only objects (`DeviationHeaderInfo.source_path`, `DeviationIngestionFailure.source_path`) still carry the full path — this is intentional, for in-process debugging — only the *exported* fields were corrected.

### Finding 3 — Undisclosed DLS-normalization inference

The four files' headers state angles (AZIM_TN/INCL/AZIM_GN) are in degrees but never explicitly declare the length-normalization of the supplied `DLS` column. "Degrees per 30 metres" is the standard oilfield convention and was already used throughout Increment 3, but — unlike the pre-existing `MD_UNIT_NOT_EXPLICITLY_DECLARED` disclosure — this inference was not itself flagged as an inference.

**Corrected in:**
- `p2mem/io/deviation.py` (`load_deviation_file`) — after a successful minimum-curvature computation, every file's already-computed `mc.dls_deg_per_30m` is compared station-by-station against the file's own `DLS_source_deg_per_30m`, and a new `DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M` WARNING is raised for every successfully loaded file, carrying the actual computed maximum absolute discrepancy (not a hardcoded value) and stating explicitly that the raw `DLS_source_deg_per_30m` values are never altered by the check.
- `tests/test_deviation.py` — three new tests: the warning is always present on success; its reported discrepancy matches an independent recomputation (proving it is not hardcoded); the warning is still present even when trajectory validation separately raises a `WARNING`-severity status.
- Module/dataclass docstrings, the YAML contract's provenance notes, and the notebook's theory/QC/Step-11/Step-12 sections were all updated to describe this as an inference, verified against data — never as a header-declared unit.

**Design note on placement:** the check was placed in `load_deviation_file()`, executed only after `resolve_deviation_contract()` has already found zero ERRORs and minimum curvature has already been computed — not inside `resolve_deviation_contract()` itself, which must never raise and would otherwise need to run minimum curvature on potentially-invalid station data before that data's validity is confirmed.

**Actual warning totals produced by this patch** (real four-well run, reported below in Section 4 — not assumed): every one of the four wells now carries exactly two WARNING-severity issues (`MD_UNIT_NOT_EXPLICITLY_DECLARED` and `DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M`) — 4 + 4 = **8 total**, zero ERRORs.

### Finding 4 — Zero-dogleg numerical instability

The dogleg angle between successive stations was computed as `arccos(cos I₁ cos I₂ + sin I₁ sin I₂ cos(A₂−A₁))`. Because `arccos` has an unbounded derivative near an argument of 1, two stations with numerically identical inclination and azimuth produced a spurious ~8.54×10⁻⁷-degree nonzero dogleg instead of exactly zero.

**Corrected in:**
- `p2mem/trajectory.py` (`dogleg_angle_rad`) — replaced with the numerically stable vector formulation `β = atan2(‖u₁ × u₂‖, u₁·u₂)`, where `u = (cos I, sin I cos A, sin I sin A)` is each station's unit tangent vector. `atan2` has a bounded derivative everywhere, including at `β = 0`. The dot product is not clipped to `[-1, 1]` (unlike the old `arccos` call) since `atan2` does not require it — documented as a deliberate simplification in the function's docstring.
- The module's "Governing theory" docstring and the notebook's Theory section were both updated to present this as the actual implemented formulation, with the `arccos` form retained only as the underlying mathematical identity being evaluated.
- `_SMALL_DOGLEG_THRESHOLD_RAD`, `ratio_factor()`, `minimum_curvature_intervals()`, and `compute_minimum_curvature_trajectory()` are unchanged — the Taylor-series small-angle limit for the ratio factor remains valid and is unaffected by this change (confirmed by a dedicated new test — see Section 3).

**Not done:** no test tolerance was loosened to work around the old defect; the fix is in the computation itself, verified against an exact (bit-for-bit) zero-dogleg requirement, not an approximate one.

---

## 2. What was NOT touched

Confirmed byte-identical to the pre-patch Increment 3 build (`diff`/`cmp`, not merely "should be identical"): `p2mem/units.py`, `p2mem/models.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `config/las_curve_contracts.yml`, `tests/test_units.py`, `tests/test_las.py`. See Section 5 for the exact comparison method and result.

Explicitly out of scope, not implemented, not started: checkshot loading, time-depth relationships, formation-top loading or correction, any petrophysical interpretation, normal-compaction-trend fitting, pore-pressure prediction, elastic-property calculation, rock-strength correlation, in-situ stress modelling, wellbore-stability screening, or mud-weight recommendations. **Increment 4 has not been started.**

The real four-well deviation-survey and LAS data, the four contracts' tolerance values, `depth_basis_policy: petrel_source_trace`, and the unresolved Proteus 1ST2 trajectory discrepancy are all unchanged by this patch. The survey data itself was never modified, and the residual discrepancy was neither concealed nor used to justify loosening any tolerance.

---

## 3. Test suite — actual results

```
$ pip install -e . --break-system-packages -q
$ pytest -v
...
261 passed in 0.53s
```

Actual per-file counts, from `pytest -v` itself (not hand-computed): 94 `test_units.py` (locked) + 64 `test_las.py` (locked) + 27 `test_trajectory.py` (24 from Increment 3 + 3 new: identical-direction exact-zero dogleg, genuinely-tiny-dogleg preservation, near-vertical-wraparound ratio-factor stability) + 52 `test_deviation.py` (41 from Increment 3 + 11 new: 3 DLS-normalization-disclosure tests, and the real-filenames-with-spaces positive/negative tests parametrized over the 4 real wells each, i.e. 4+4=8 individually-collected parametrized cases) + 18 `test_depth_mapping.py` (unchanged) + 6 new `test_deviation_inventory.py` = 94+64+27+52+18+6 = **261**, matching pytest's own summary exactly: **261 passed, 0 failed, 0 errors, 0 skipped.**

`tests/test_trajectory.py` — the pre-existing `test_constant_inclination_straight_trajectory_matches_closed_form` test's approximate dogleg/DLS assertions (`atol=1e-5`) were tightened to an exact `np.array_equal(..., 0.0)` check, since the fix now makes this the correct, honest expectation rather than a tolerance to work around. The pre-existing wraparound test's tolerance was independently tightened from `abs=1e-10` to `abs=1e-12` (not loosened).

`p2mem.__version__` confirmed as `0.3.1` after the editable install.

---

## 4. Real-data integration — actual results (real four-well run, exact space-containing filenames)

A development-only orchestration script (`run_integration_03.py`, not packaged) was re-pointed at the four files using their exact literal names. **Disclosure on filename provenance:** the raw deviation files available in this build environment are themselves named with underscores (an artifact of how they were uploaded into this sandbox, not necessarily a re-creation of the user's actual Google Drive naming). Since this session has no direct access to the user's Google Drive to obtain space-named originals, byte-identical verification copies of the four real files were created under a separate, clearly labeled, dev-only directory (`data/raw/deviation_spacedname_verification/`, never packaged, never included in the deliverable ZIP) with the exact target filenames, to exercise the corrected code path end-to-end against files that are byte-for-byte identical to the originals except for their name. This verification method and its limitation are disclosed here rather than silently assumed away; the actual Google Drive files should be spot-checked by the user against the filenames in `config/deviation_survey_contracts.yml` before running the notebook.

```
LAS loaded: ['Boreas_1', 'Poseidon_2', 'Poseidon_North_1', 'Proteus_1ST2']   (4/4, 0 failed)
Deviation loaded: ['Boreas_1', 'Poseidon_2', 'Poseidon_North_1', 'Proteus_1ST2']   (4/4, 0 failed)

LAS MD fully inside survey MD coverage: all 4 wells (Poseidon_2, Boreas_1, Poseidon_North_1, Proteus_1ST2)
LAS MD→TVD/TVDSS mapping: n_extrapolated = 0 for all 4 wells

Trajectory validation (minimum curvature vs Petrel source):
  Poseidon_2:        overall=PASS    | TVD max|res|=0.000888 m | East max|res|=0.000007 m | North max|res|=0.000025 m
  Boreas_1:          overall=PASS    | TVD max|res|=0.001345 m | East max|res|=0.000016 m | North max|res|=0.000016 m
  Poseidon_North_1:  overall=PASS    | TVD max|res|=0.001948 m | East max|res|=0.000005 m | North max|res|=0.000029 m
  Proteus_1ST2:      overall=WARNING | TVD max|res|=0.191488 m | East max|res|=1.582982 m | North max|res|=0.880172 m

Total deviation stations across 4 wells: 560 (124 + 134 + 147 + 155)
Contracts passed: 4/4
Total LAS extrapolated samples: 0
```

**Per-well ingestion issues (actual, not assumed):** every one of the four wells carries exactly 2 WARNING-severity issues — `MD_UNIT_NOT_EXPLICITLY_DECLARED` and `DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M` — confirmed by counting the actual `deviation_ingestion_issues.csv` rows generated by this run: 4 + 4 = 8 rows, 0 ERROR rows.

**DLS-normalization independent-verification discrepancies (actual computed values, per well):**

| Well | Max \|DLS_source − DLS_recomputed\| (deg/30m) | Stations |
|---|---|---|
| Poseidon 2 | 1.482572×10⁻⁹ | 124 |
| Boreas 1 | 3.118738×10⁻⁹ | 134 |
| Poseidon North 1 | 1.656303×10⁻⁹ | 147 |
| Proteus 1ST2 | 3.586469×10⁻¹⁰ | 155 |

All four values are consistent with the pre-patch investigation's finding (~3.6×10⁻¹⁰ deg/30m for Proteus 1ST2) — the trajectory-computation fix (Finding 4) did not alter this conclusion.

**Proteus 1ST2 trajectory discrepancy: retained, unmodified, unconcealed.** The 0.191 m TVD / 1.58 m easting / 0.88 m northing maximum residuals above are unchanged in character from Increment 3 (see Section 5's honest floating-point-level comparison) and remain reported as an open, unresolved data-quality finding — the survey was not altered, no tolerance was loosened to hide or soften it, and it is still visibly flagged as `WARNING` (not silently passed).

---

## 5. Honest numerical comparison — before vs. after the dogleg fix (Finding 4)

The dogleg-angle fix changes only the vector formulation used to derive `β`; TVD/Northing/Easting displacement accumulation depends on inclination and azimuth directly (via `sin`/`cos`), not on `β`, so the physical trajectory reconstruction was expected to be unaffected except at the floating-point noise floor. This was verified directly, not merely asserted: the real four-well `trajectory_validation_summary.csv` from the pre-patch Increment 3 run was diffed field-by-field, per well, against this patch's regenerated output.

**Result:** maximum absolute change across all four wells and all reported residual statistics (TVD max/mean/RMSE/endpoint, easting, northing): **9.095×10⁻¹³ m** (TVD fields); easting/northing fields changed by at most **~7.1×10⁻¹⁵ m**. Every `PASS`/`WARNING` status is unchanged for every well and every metric. This is reported as an honest measured difference, not assumed to be zero and not hidden.

Separately, the dogleg-angle fix's own direct effect was verified by unit test: two stations with bit-for-bit identical inclination and azimuth now yield `β == 0.0` exactly (previously ~8.54×10⁻⁷ degrees); a genuinely tiny nonzero dogleg (10⁻⁶ degrees) is still correctly preserved and not erased by the fix; azimuth wraparound (359.5°→0.5°) and a near-vertical station pair both remain numerically stable.

---

## 6. Determinism and absolute-path verification

**Method:** the complete real four-well workflow (`run_integration_03.py`) was run from three different working directories: the primary build directory, and two independent temporary root directories (`/tmp/detroot_a`, `/tmp/detroot_b`, each an independent copy of the full source tree with its own editable `pip install`).

**Result:** all six exported machine-readable output files (`depth_reference_register.csv`, `deviation_depth_manifest.json`, `deviation_file_inventory.csv`, `deviation_ingestion_issues.csv`, `las_depth_mapping_summary.csv`, `trajectory_validation_summary.csv`) are **byte-identical** (`cmp -s`, exit 0) across all three runs. Neither temporary root's own path (`/tmp/detroot_a`, `/tmp/detroot_b`) appears anywhere in either run's output set.

**Absolute-path search (whole package, all output/deliverable file types):** `grep -rl "/home/claude\|/workspace\|/content/drive\|C:\\"` across every `.py`, `.yml`, `.md`, `.csv`, `.json`, and `.ipynb` file in the package found matches only in the two Colab notebooks' own markdown/code-cell **source** (e.g. `drive.mount('/content/drive')`, `%cd /content/drive/MyDrive/Poseidon_1D_MEM`) — these are the intended, user-facing Colab runtime paths the notebook instructs the user to use, not build-machine artifacts; the notebooks carry **zero saved execution outputs** (confirmed via `nbformat`: 0 of 67 code cells have a populated `outputs` field), so no absolute path from an actual run is embedded in either notebook. The five QC PNG figures were also checked (`strings <file> | grep`) for embedded paths in image metadata: none found. This finding is reported as a verified negative result, not an assumed one — no absolute-path difference is described here as an "acceptable environment-dependent exception."

---

## 7. Locked-file byte-identity verification

```
$ cmp p2mem/units.py <pre-patch>/p2mem/units.py                          -> byte-identical
$ cmp p2mem/models.py <pre-patch>/p2mem/models.py                        -> byte-identical
$ cmp p2mem/io/las.py <pre-patch>/p2mem/io/las.py                        -> byte-identical
$ cmp p2mem/io/inventory.py <pre-patch>/p2mem/io/inventory.py            -> byte-identical
$ cmp config/las_curve_contracts.yml <pre-patch>/config/...              -> byte-identical
$ cmp tests/test_units.py <pre-patch>/tests/test_units.py                -> byte-identical
$ cmp tests/test_las.py <pre-patch>/tests/test_las.py                    -> byte-identical
```

All seven locked files are confirmed byte-identical against the pre-patch Increment 3 build. No blocking defect was found in any of them during this corrective patch, so none were modified.

---

## 8. Notebook validation

- `nbformat.validate()` on the regenerated `03_Deviation_Survey_and_Depth_Framework.ipynb` (67 cells): **passed, no errors.**
- Programmatic `%%writefile`-cell-vs-packaged-source parity check (`verify_notebook_parity_03.py`, which scans every code cell beginning with `%%writefile` and compares its body byte-for-byte against the named file on disk): **24 cells checked, 0 mismatches, 0 missing files** (23 in the pre-patch Increment 3 build, +1 for the new `tests/test_deviation_inventory.py` cell).
- Changes to notebook content in this patch: (1) `DEV_FILES` mapping (Step 4) corrected to the exact space-containing filenames; (2) Step 4 markdown text and the Increment 3.1 corrective-patch note (phase header) updated; (3) Theory section extended to describe the `atan2`-based dogleg formulation; (4) Step 11 now prints every well's actual per-file ingestion issues (both WARNINGs), where Increment 3 printed none; (5) Step 12's Proteus investigation cell cross-references the new automatic DLS-normalization warning; (6) a new `%%writefile tests/test_deviation_inventory.py` cell added to Step 7b; (7) version references updated to 0.3.1.

---

## 9. Package inventory and checksums

Final deliverable: `Poseidon_1D_MEM_Increment_03_v3.1.zip`.

File count and every packaged file's SHA-256 (computed from the final packaged bytes, after extraction from the ZIP into a clean directory — not computed before packaging and assumed to survive unchanged) are recorded in the delivery message accompanying this manifest, since those values are only final once the ZIP itself is built; this manifest is packaged inside that same ZIP and is therefore excluded from its own checksum list by construction.

---

## 10. Stop condition

This corrective patch addresses ONLY the four findings above. No Increment 4 work (checkshot ingestion, time-depth conversion, formation-top correction, petrophysical interpretation, pore-pressure prediction, elastic-property calculation, rock-strength estimation, stress modelling, or wellbore-stability screening) was performed, started, or is included in this deliverable.
