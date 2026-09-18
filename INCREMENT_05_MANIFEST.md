# Increment 5 Manifest — Formation-Top Ingestion, Source Reconciliation, and Survey-Corrected Stratigraphic Depth Framework

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.5.0
**Builds on:** Increment 4.1.2 (`Poseidon_1D_MEM_Increment_04_v4.1.2.zip`), locked and unmodified — see Section 2.
**Date generated:** 2026-09-02

This manifest records what was actually implemented, tested, and re-verified for Increment 5. Every number in this document is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously reported value carried over without re-confirmation.

---

## 1. Scope actually implemented

1. Contract-driven formation-top file ingestion for the four approved files, keyed by exact filename and verified SHA-256, with structural parsing kept explicitly separate from contract resolution: `Top_Name`/`MDRT_m` "HRS" files (no comment lines, no well name in the body) and `TOP_NAME`/`MDRT_M`/`TVDSS_M`/`NOTE` "selected readable" files (leading `#`-comment lines preserved verbatim, a dashed separator line structurally recognized and skipped — never accidentally treated as a data row).
2. Preservation of every raw marker name and raw source depth from BOTH file representations, in original file order — nothing is ever silently overwritten, sorted, deduplicated, or repaired.
3. Explicit HRS-versus-selected-readable source RECONCILIATION per well (`p2mem.io.tops.reconcile_formation_top_sources`): marker matching by exact name, whitespace-normalized name, or an explicit human-authored alias contract (`marker_name_aliases` in `config/formation_top_contracts.yml`) — no fuzzy/similarity matching of any kind, at any tolerance. MDRT is cross-checked between the two sources within a documented 0.005 m tolerance (`MDRT_AGREEMENT_TOLERANCE_M`); a marker present in only one source is `NOT_COMPARABLE`; a marker on which the two sources disagree beyond tolerance is registered as a `MISMATCH` and its `mdrt_authority_basis` is `"disagreement_unresolved"` — the marker is excluded from depth mapping entirely rather than resolved by picking one file's value.
4. Mapping of each well's reconciled MDRT through the LOCKED Increment 3.1.1 `petrel_source_trace` survey trajectory, using the existing, UNMODIFIED `p2mem.depth_mapping.map_las_md_to_tvd_tvdss` (called once per marker, so one out-of-coverage marker never blocks mapping of the rest of the well); this increment never reimplements minimum curvature or the TVD/TVDSS formula. A marker whose reconciled MDRT falls outside the well's own surveyed MD coverage is reported as `mapping_status = "rejected_outside_coverage"` and never extrapolated.
5. An explicit, unambiguous residual field on every mapped marker: `TVDSS_residual_source_minus_survey_m = TVDSS_source_m - TVDSS_survey_corrected_m` (never a bare `error_m`).
6. Corrected, auditable stratigraphic marker records (`p2mem.top_models.TopMarkerRecord`) carrying every raw source value, the reconciled MDRT and its authority basis, and the survey-derived TVD/TVDSS — under separately named fields; raw values are never overwritten.
7. Formation-top availability/provenance records: Poseidon North 1 and Proteus 1ST2 have no approved formation-top file and are recorded as `formation_top_availability: NOT_AVAILABLE` — a factual data gap, never an ingestion failure, and never filled by substituting another well's tops or correlating them by depth alone.
8. Typed, frozen dataclass result objects for every formation-top object (`p2mem/top_models.py`), fully independent of the locked LAS/deviation/checkshot dataclasses, reusing (never redefining incompatibly) the project's established `well_identity_evidence_status`/`model_use_status` vocabulary from `p2mem.checkshot_models`.
9. Deterministic CSV/JSON outputs, three QC figures, a portable synthetic-fixture test suite, and a Colab-compatible notebook (`05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb`) documenting the above.

## 2. What this increment does not touch, and what it does not do

**Locked and unmodified from Increment 4.1.2** (confirmed byte-identical against `Poseidon_1D_MEM_Increment_04_v4.1.2.zip` — see Section 6): `p2mem/units.py`, `p2mem/models.py`, `p2mem/deviation_models.py`, `p2mem/trajectory.py`, `p2mem/depth_mapping.py`, `p2mem/checkshot_models.py`, `p2mem/time_depth.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `p2mem/io/checkshot.py`, `p2mem/io/checkshot_inventory.py`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, `config/checkshot_contracts.yml`, every existing test file, all three prior notebooks, and every prior increment's manifest/checksum file and CSV/JSON/figure outputs. No blocking defect was found in any of these during Increment 5 development, so none were modified. `p2mem/__init__.py`, `pyproject.toml`, and `README.md` were updated in place — version bump to 0.5.0 and Increment 5 scope documentation only, no change to any existing scientific statement.

**Explicitly out of scope for Increment 5** (not implemented, not started): gamma-ray normalization, shale-volume calculation, named lithology classification, petrophysical interpretation, method-eligibility masks, shallow-density modelling, overburden-stress integration, normal-compaction-trend (NCT) fitting, pore-pressure prediction, elastic-property calculation, rock-strength estimation, in-situ horizontal-stress modelling, and wellbore-stability screening. Increment 6 has **not** been started.

## 3. Real-data source facts (independently observed, not assumed)

Formation-top file SHA-256 (computed against the four raw files supplied for this project):

| Well | Representation | Source filename | Identity evidence | SHA-256 |
|---|---|---|---|---|
| Poseidon 2 | HRS | `Poseidon_2_HRS_tops_no_wellname_MDRT.txt` | `inferred_unverified` (filename-only) | `c907e81dc16bd72c209ffd9d1cc1e6e8837868e465d0fa627756e8c773737b9a` |
| Poseidon 2 | selected readable | `Poseidon_2_selected_well_tops.txt` | `inferred_unverified` (in-file comment) | `f4f057c44598efc7397029911521c10a0ec151f4b2387788b894bd99939c40a1` |
| Boreas 1 | HRS | `Boreas_1_HRS_tops_no_wellname_MDRT.txt` | `inferred_unverified` (filename-only) | `5504dfe9fdeb3e2b8e024f17d59aba345974d432bdce89f9c8e5b8fd156cc9b4` |
| Boreas 1 | selected readable | `Boreas_1_selected_well_tops.txt` | `inferred_unverified` (in-file comment) | `bc677bc6a5b852de8e0e6deb1afd9ff7936870df95517e608cc6d771eed6327f` |
| Poseidon North 1 | — | *(none — `formation_top_availability: NOT_AVAILABLE`)* | — | — |
| Proteus 1ST2 | — | *(none — `formation_top_availability: NOT_AVAILABLE`)* | — | — |

Marker counts and MDRT ranges (parsed from the files, not hard-coded): Poseidon 2 has 9 markers (Sea Bed through TD, MDRT 518.40–5356.00 m); Boreas 1 has 10 markers (Sea Bed through TD, including a Nome Fm pick absent from Poseidon 2's set, MDRT 513.70–5210.00 m). All four files are treated as private raw inputs: none is rewritten, renamed, "cleaned," or packaged in this deliverable — only their parsed statistics are.

**Well-identity evidence classification (deliberately more conservative than Increment 4's checkshot files).** The two "HRS" files carry no well name anywhere in the file body — the association with the stated project well rests on the filename alone, which the filename itself acknowledges ("...no_wellname..."). The two "selected readable" files DO name the well, but only in a leading `#` comment line ("Selected readable well tops for Poseidon 2" / "for Boreas 1") — this is project-supplied metadata embedded in the file, not independently verified file content. Increment 4 classified `Poseidon2-Checkshot.txt`/`Boreas1-Checkshot.txt` as `"verified"` on the reasoning that only one candidate well of each of those names exists in the project; that same filename-uniqueness reasoning is available here, but this increment declines to extend it to `"verified"` for either representation, because (a) the HRS filename's own text explicitly disclaims embedding a well identifier, underscoring that the association is a structural, not evidentiary, fact, and (b) the readable file's comment, while human-readable, is still project-authored text inside the file rather than an independently checkable identifier (e.g. a UWI, API number, or survey header field). All four files are therefore classified `well_identity_evidence_status: "inferred_unverified"`, a strictly more conservative choice than the nearest Increment 4 precedent, made explicitly and documented here rather than silently defaulting.

## 4. Source reconciliation results (actual, both wells)

Reconciliation compared each well's HRS marker set against its selected-readable marker set (`p2mem.io.tops.reconcile_formation_top_sources`). Actual results, both wells:

| Well | Canonical markers | Exact/normalized name matches | Markers in only one source | MDRT agreement | MDRT mismatches |
|---|---|---|---|---|---|
| Poseidon 2 | 9 | 9 (exact match — see below) | 0 | 9/9 within 0.005 m tolerance | 0 |
| Boreas 1 | 10 | 10 (exact match — see below) | 0 | 10/10 within 0.005 m tolerance | 0 |

An exhaustive comparison of all four real files' marker names found every HRS marker name identical, byte-for-byte, to its corresponding readable-file marker name once only the readable file's own fixed-width space padding is stripped (`normalize_marker_name` — whitespace-only normalization, never touching case or punctuation). No alias-contract entry was needed for the real data; `marker_name_aliases: {}` in `config/formation_top_contracts.yml` remains empty for this reason, and is exercised only by `tests/test_tops.py`'s synthetic fixtures. Every marker in both wells mapped successfully within survey coverage (`mapping_status = "mapped_within_coverage"`); zero markers were rejected for coverage, and zero were left `not_mapped_mdrt_unresolved` — the real data presented no MDRT disagreement beyond tolerance in either well.

## 5. Regression findings (independently recomputed, real data — actual results)

### 5.1 Poseidon 2 — vertical-well-assumption depth-reference defect (confirmed, corrected in the derived representation)

Independently checking `TVDSS_source_m` against `MDRT_source_m - 21.8` (21.8 m being Poseidon 2's own rotary-table/Kelly-Bushing elevation, from the locked deviation-survey header) for every one of the 9 selected-readable markers:

```
Every one of 9 Poseidon 2 supplied TVDSS values equals MDRT_M - 21.8 m EXACTLY: True
```

This is a stronger, more precise finding than the "approximately `MDRT - 21.8 m`" anticipated in the approved design: the relationship is EXACT to the file's own two-decimal precision for all 9 markers, not merely approximate — confirming this file's TVDSS was generated by literally assuming a perfectly vertical well (TVD = MD from datum), never accounting for Poseidon 2's real, surveyed deviation.

Survey-corrected residuals (`TVDSS_residual_source_minus_survey_m = TVDSS_source_m - TVDSS_survey_corrected_m`), independently recomputed by mapping each marker's reconciled MDRT through the locked survey trajectory:

| Marker | TVDSS_source_m | TVDSS_survey_corrected_m | Residual (source − survey), m |
|---|---|---|---|
| Sea Bed | 496.60 | 496.6000 | **−0.0000** |
| Plover Fm (Top Reservoir) | 4902.30 | 4900.6204 | **+1.6796** |
| TD | 5334.20 | 5331.7104 | **+2.4896** |

All three reproduce the approved design's anticipated approximate values (≈0, ≈+1.68 m, ≈+2.49 m) essentially exactly. This is treated as a confirmed formation-top depth-reference defect, corrected in `TVDSS_survey_corrected_m` while `TVDSS_source_m` itself is preserved unmodified in every output for audit.

### 5.2 Boreas 1 — survey-consistent tops (confirmed; NOT corrected)

Independently computing the maximum absolute residual across all 10 mapped Boreas 1 markers:

```
Boreas 1 maximum absolute TVDSS residual across 10 mapped markers: 0.041602 m
(approved tolerance: < 0.05 m -> PASS)
```

`0.0416 m < 0.05 m` — within the approved Rev 1 design tolerance. Boreas 1's supplied TVDSS was independently confirmed NOT to follow the Poseidon-2-like vertical-assumption pattern (counter-example: Prion Fm, `2206.90 − 21.8 = 2185.10`, but the file states `2185.04`; the same check evaluated across the well's own rotary-table elevation returns `False` for every marker). This evidence — small residual, no vertical-assumption signature — supports the interpretation that Boreas 1's selected-readable TVDSS was generated from the well's real surveyed trajectory. Per the approved design's explicit instruction, Boreas 1 is **not** "corrected" merely because Poseidon 2 contains a defect: `TVDSS_source_m` and `TVDSS_survey_corrected_m` are both reported side by side, unmodified, with the small residual disclosed as evidence of consistency, not as a defect requiring correction.

## 6. Locked-baseline integrity check (actual)

`diff -rq` between a clean extraction of `Poseidon_1D_MEM_Increment_04_v4.1.2.zip` and this deliverable's build tree (excluding dev-only directories, the new Increment 5 notebook, and this increment's own new files/outputs) reports exactly three differing files:

```
Files .../README.md and .../README.md differ
Files .../p2mem/__init__.py and .../p2mem/__init__.py differ
Files .../pyproject.toml and .../pyproject.toml differ
```

These are precisely the three files intentionally updated for version/documentation purposes (Section 2). No other locked file — including every prior increment's manifest, checksum ledger, CSV/JSON output, or figure — differs from the Increment 4.1.2 baseline.

## 7. Test-suite result (actual)

```
$ python3 -m pytest -q
439 passed in 0.87s
```

This is the complete combined suite: all 385 tests locked through Increment 4.1.2, plus 39 new tests in `tests/test_tops.py` and 15 new tests in `tests/test_tops_inventory.py` (39 + 15 = 54; 385 + 54 = 439). Every new test uses only small, synthetic, fictional fixtures (`tests/fixtures/top_*.txt`, "Test Well 1"/"Marker A/B/C(/D)") — no real project formation-top, deviation, checkshot, or LAS file is used as a unit-test fixture or packaged in this deliverable.

New coverage added in Increment 5 (`tests/test_tops.py`, 39 tests): structural parsing of both HRS and readable formats including comment/separator handling; file-not-found for both formats; malformed/non-finite/negative-depth rejection; contract resolution success and SHA-256/filename/well-name-comment mismatch detection; well-identity-never-verified assertion; marker-name normalization; alias-contract resolution with and without the alias present (proving no silent fuzzy matching); duplicate-marker-name and marker-order-reversal `ERROR` detection; missing-in-one-source `NOT_COMPARABLE` handling; MDRT-mismatch `WARNING` generation and the resulting exclusion of that marker from mapping while other markers in the same well still map normally; successful mapping within survey coverage; rejection of a marker outside coverage (never extrapolated); the explicit residual-sign-convention check; synthetic analogs of both real regression findings; ambiguous-dtype rejection (boolean, string); mismatched-array-length rejection; end-to-end success and two failure paths; YAML contract-definition validation (duplicate key, invalid enum); batch-loader failure isolation with absolute-path sanitization; and missing-contract/missing-deviation-result error paths. New coverage in `tests/test_tops_inventory.py` (15 tests): file-inventory two-rows-per-well construction; per-source-file error/warning counts; marker-register raw-value preservation and deterministic sort order; reconciliation-row `None`-field handling; corrected-marker-row explicit-residual and unmapped-marker handling; issues-row path sanitization; availability-row coverage of available/failed/not-available wells; and manifest Tier C classification, well-identity non-upgrade behavior, unmapped-marker exclusion from residual statistics, JSON determinism, and failed-well path sanitization.

## 8. Real formation-top integration result (actual, re-run during this verification)

```
$ python3 dev_scratch_inc5/run_integration_05.py
=== Regression finding 1: Poseidon 2 vertical-well-assumption defect ===
  Every one of 9 Poseidon 2 supplied TVDSS values equals MDRT_M - 21.8 m EXACTLY: True
  Sea Bed: TVDSS_residual_source_minus_survey_m = -0.0000 m
  Plover Fm (Top Reservoir): TVDSS_residual_source_minus_survey_m = 1.6796 m
  TD: TVDSS_residual_source_minus_survey_m = 2.4896 m

=== Regression finding 2: Boreas 1 survey-consistent tops ===
  Boreas 1 maximum absolute TVDSS residual across 10 mapped markers: 0.041602 m (approved tolerance: < 0.05 m -> PASS)
  Boreas 1 follows the Poseidon-2-like MDRT-21.8 pattern (must be False): False

=== Increment 5 real integration: SUCCESS ===
Formation-top wells loaded: ['Boreas_1', 'Poseidon_2']
Formation-top availability (NOT_AVAILABLE): ['Poseidon_North_1', 'Proteus_1ST2']
  Boreas_1: n_canonical_markers=10 n_mapped=10 n_rejected_outside_coverage=0 n_mdrt_unresolved=0
  Poseidon_2: n_canonical_markers=9 n_mapped=9 n_rejected_outside_coverage=0 n_mdrt_unresolved=0
```

Deterministic byte identity was independently confirmed by running this script twice into two separately copied output directories and comparing with `diff -rq`: zero differences across all 6 CSVs, the JSON manifest, and all 3 PNG figures. No absolute path (`/home/`, `/root/`, `/content/`) appears in any output CSV or JSON — confirmed by direct `grep`.

## 9. Output files (actual, regenerated during this verification)

Written to `outputs/05_formation_tops/`:

- `top_file_inventory.csv` — 6 rows (2 per available well, 1 per NOT_AVAILABLE well)
- `top_marker_register.csv` — 38 rows (raw HRS + raw readable rows for both wells: 9+9 for Poseidon 2, 10+10 for Boreas 1)
- `top_hrs_vs_readable_reconciliation.csv` — 19 rows (9 + 10 canonical markers)
- `top_survey_corrected_markers.csv` — 19 rows
- `top_ingestion_issues.csv` — 6 rows (3 disclosure `WARNING`s per well: filename-only identity, in-file-comment identity, supplied-TVDSS-not-corrected-depth)
- `top_availability.csv` — 4 rows (2 available, 2 `NOT_AVAILABLE`)
- `formation_top_manifest.json` — Tier C classification, per-well provenance/evidence/mapping statistics, both source file hashes per well, failed-well ledger (empty)

Figures written to `outputs/05_formation_tops/figures/`: `fig01_poseidon2_tvdss_residual_by_marker.png`, `fig02_boreas1_tvdss_residual_by_marker.png`, `fig03_poseidon2_boreas1_marker_depth_panel.png` — each carries units, well name(s), the survey-corrected depth basis, the well's evidence classification, and a Tier C footer; Fig 3 is explicitly captioned as a marker-depth comparison, not a geological correlation or lithology interpretation; source and survey-corrected series are never plotted without distinguishable styling/legends.

## 10. Notebook verification (actual, programmatic)

`05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb` (61 cells) was validated three independent ways:

1. **Structural validity:** `nbformat.validate()` passes; every cell has a unique string `id`; every code cell has `execution_count: null` and `outputs: []` (zero saved execution outputs).
2. **Static execution-order checks** (`dev_scratch_inc5/verify_execution_order_05.py`, Part A): `PROJECT_ROOT` is defined before `os.chdir(PROJECT_ROOT)`, which precedes every `%%writefile` cell; every `%%writefile` target is a relative path with no `..` escape; every `%%writefile` body is confirmed LF-only (no CRLF-sensitive fixture exists in Increment 5, so the Increment 4.1.2 explicit-bytes mechanism is correctly not used here).
3. **Real runtime reconstruction** (same script, Part B — not merely static source parity): every one of the notebook's 38 code cells was actually executed, in order, in a single namespace, starting from a fresh simulated `/content`-style process directory pre-populated with a clean Increment 4.1.2 foundation and the real approved input files at their exact contract-matching paths, with every Increment-5 `%%writefile` target first removed so a passing run proves the notebook's OWN cells reconstruct everything needed. Result:

```
All 38 code cells executed successfully from a fresh process cwd.
Final working directory: /content/drive/MyDrive/Poseidon_1D_MEM
EXECUTION SMOKE TEST: PASSED
```

This run included a genuine `subprocess.run([sys.executable, "-m", "pytest", "-v"])` inside the reconstructed tree (439 passed, `FULL_TEST_SUITE_PASSED = True`), the real formation-top integration (Section 8's findings reproduced inside the notebook's own reconstructed environment), and the completion gate printing all 9 conditions `[PASS]`.

## 11. Clean-room ZIP verification (actual, on fresh extraction)

1. `Poseidon_1D_MEM_Increment_05.zip` extracted into an independent, empty directory.
2. Every SHA-256 in `INCREMENT_05_SHA256SUMS.txt` verified against the extracted files: all match.
3. `pip install -e . --no-build-isolation --no-index --no-deps -q` (offline, no network) succeeds; `python3 -c "import p2mem; print(p2mem.__version__)"` → `0.5.0`.
4. `python3 -m pytest -q` inside the extracted tree → `439 passed`.
5. `python3 dev_scratch_inc5/run_integration_05.py`-equivalent real-data integration (Section 8) reproduced against the extracted tree's package code, using the four private top files supplied separately (never packaged) — findings identical to Section 8.
6. All 7 deterministic CSV/JSON outputs and 3 figures regenerated byte-identical to Section 9 (confirmed via `diff -rq` against the pre-packaging outputs directory).
7. No absolute path (`/home/`, `/root/`, `/content/`, or any container-specific path) found anywhere in the packaged source, tests, config, notebook, or regenerated outputs.
8. No raw LAS, deviation, checkshot, or formation-top file is present anywhere in the extracted archive — confirmed by listing every file under `data/` (empty placeholder structure only) and grepping the archive's file list for the four approved formation-top filenames and every prior increment's raw filenames (checkshot, deviation, LAS): zero matches.
9. Every locked prior-increment file and output (Section 6) confirmed byte-identical inside the extracted archive against the Increment 4.1.2 baseline, matching the pre-packaging check.

## 12. Packaged file inventory

`Poseidon_1D_MEM_Increment_05.zip` contains: all locked Increment 1–4.1.2 source, tests, config, notebooks, manifests, and checksum ledgers (unmodified except the three files named in Section 2); the three new Increment 5 modules (`p2mem/top_models.py`, `p2mem/io/tops.py`, `p2mem/io/tops_inventory.py`); `config/formation_top_contracts.yml`; `tests/test_tops.py`, `tests/test_tops_inventory.py`, and 13 new synthetic fixture files under `tests/fixtures/`; `05_Formation_Tops_and_Stratigraphic_Depth_Framework.ipynb`; and the regenerated `outputs/05_formation_tops/` directory (CSVs, JSON manifest, figures). Excluded from the package: `dev_scratch_inc4_1/` and `dev_scratch_inc5/` (dev-only scripts and the four real, private formation-top files), `.pytest_cache/`, and all `__pycache__/` directories.

## 13. Assurance classification

Tier C — Screening-Level / Uncalibrated Educational, consistent with the rest of this project. This increment adds a factual, auditable depth-reference layer (marker ingestion, reconciliation, and survey-corrected mapping) — it performs no petrophysical, lithological, or geomechanical interpretation of any kind, and no claim of calibration is made anywhere in this deliverable.

## 14. Known limitations

- The real data presented zero MDRT disagreements beyond tolerance and zero out-of-coverage markers for either well, so the `disagreement_unresolved` / `rejected_outside_coverage` code paths, while implemented, tested against synthetic fixtures, and demonstrably reachable, are not exercised by any real marker in this increment's actual data.
- Both formation-top file representations for both wells are `well_identity_evidence_status: inferred_unverified` (Section 3) — a deliberately conservative classification; no independent, content-based verification of well identity was possible from the files themselves.
- Poseidon North 1 and Proteus 1ST2 have no approved formation-top file; this is disclosed as a factual data gap (`NOT_AVAILABLE`), not resolved, corrected, or worked around.
- Boreas 1's small but non-zero residual (0.0416 m) is disclosed as evidence of survey consistency, not proof of exact agreement; no claim beyond "below the approved 0.05 m tolerance" is made.
- The Poseidon 2 – Boreas 1 marker-depth panel (Fig 3) asserts no geological, stratigraphic, or genetic relationship between the two wells' markers — it is a depth-axis comparison only.
- This increment does not attempt to explain WHY Poseidon 2's selected-readable file was generated under a vertical-well assumption (e.g., which workflow or tool produced it) — only that the pattern is present, exact, and correctable in the derived representation.

## 15. Increment 6 status

**Not started.** No gamma-ray normalization, shale-volume calculation, lithology classification, petrophysical interpretation, density modelling, NCT fitting, pore-pressure prediction, elastic-property calculation, rock-strength estimation, stress modelling, or wellbore-stability code exists anywhere in this deliverable. Per the approved scope, this increment stops here and awaits independent audit before any further phase begins.
