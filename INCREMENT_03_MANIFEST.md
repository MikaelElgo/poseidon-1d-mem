# Increment 3 Manifest — Deviation-Survey Ingestion, Minimum-Curvature Validation, and MD–TVD–TVDSS Depth Framework

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.3.0
**Builds on:** Increment 2.1.1 (`Poseidon_1D_MEM_Increment_02_v2.1.1.zip`), locked and unmodified — see Section 2.
**Date generated:** 2026-09-01

This manifest records what was actually implemented, tested, and re-verified for Increment 3. Every number in this document is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously-reported value carried over without re-confirmation.

> **Increment 3.1 correction notice:** an independent audit found this manifest's Section 3 table below displayed the four source filenames with underscores substituted for their real, literal spaces (e.g. `Poseidon_2_dev.txt` shown here instead of the actual `Poseidon 2_dev.txt`). The table has been corrected in place to the exact filenames below; the SHA-256 values, station counts, MD ranges, and every other finding in this document are unaffected (file content bytes never changed). See `INCREMENT_03_1_MANIFEST.md` for the full audit, three further corrections (absolute-path leakage, DLS-normalization disclosure, dogleg numerical-stability), and re-verification record.

---

## 1. Scope actually implemented

1. Petrel deviation-survey text-file ingestion for the four approved wells (Poseidon 2, Boreas 1, Poseidon North 1, Proteus 1ST2), with strict per-file structural and unit parsing (`p2mem/io/deviation.py`).
2. Explicit, human-authored, human-reviewable per-well deviation contracts with contract-authoring validation performed before any survey file is opened (`config/deviation_survey_contracts.yml`, loaded by `p2mem/io/deviation.py`).
3. Station-level quality control: monotonic MD, inclination range, numeric finiteness, required-column presence, duplicate-column and duplicate-MD rejection.
4. A standalone minimum-curvature trajectory engine (`p2mem/trajectory.py`) — dogleg angle, ratio factor with a numerically stable small-angle limit, TVD/Northing/Easting displacement, and dogleg severity — independent of and never overwriting the Petrel-supplied trajectory.
5. Independent comparison of the minimum-curvature-computed trajectory against the Petrel-supplied source trajectory (TVD, Easting-offset, Northing-offset), using `AZIM_GN` exclusively for grid-coordinate computation, plus three internal Petrel-source self-consistency checks (X ≈ X_wellhead + DX, Y ≈ Y_wellhead + DY, Z ≈ Datum − TVD).
6. An explicit, tested depth-reference-convention framework: MD/TVD referenced to the well datum and increasing downward; `TVDSS_m = TVD_m − DatumElevation_m`; `Z_m = DatumElevation_m − TVD_m` (equivalently `TVDSS_m = −Z_m`).
7. An explicit, auditable, never-silent depth-basis-selection policy (`petrel_source_trace` vs `minimum_curvature_computed`), declared per well in the contract YAML and propagated through typed results, CSV/JSON outputs, and the manifest.
8. MD-to-TVD/TVDSS mapping of the locked Increment 2.1.1 LAS `MD_m` curve for all four wells, using piecewise-linear station interpolation with extrapolation rejected by default (`p2mem/depth_mapping.py`).
9. Typed dataclass result objects and typed, isolated batch-ingestion failures for the new deviation layer (`p2mem/deviation_models.py`), fully independent of the locked LAS-layer dataclasses in `p2mem/models.py`.
10. Deterministic CSV/JSON outputs, five QC figures, a portable synthetic-fixture test suite, and a Colab-compatible notebook (`03_Deviation_Survey_and_Depth_Framework.ipynb`) documenting the above.

## 2. What this increment does not touch, and what it does not do

**Locked and unmodified from Increment 2.1.1** (confirmed byte-identical — see Section 6): `p2mem/units.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `config/las_curve_contracts.yml`, `tests/test_units.py`, `tests/test_las.py`. No blocking defect was found in any of these during Increment 3 development, so none were modified.

**Explicitly out of scope for Increment 3** (not implemented, not started): checkshot loading, time-depth relationships, formation-top loading or correction, any petrophysical interpretation (gamma-ray normalization, shale volume, lithology classification), normal-compaction-trend fitting, pore-pressure prediction, elastic-property calculation, rock-strength correlation, in-situ stress modelling, wellbore-stability screening, and mud-weight recommendations. Increment 4 has **not** been started.

## 3. Real-data source facts (independently observed, not assumed)

Deviation-survey file SHA-256 (computed against the raw files supplied for this project):

| Well | Source filename | SHA-256 |
|---|---|---|
| Poseidon 2 | `Poseidon 2_dev.txt` | `862e3d765edb8ecda6a4ea45ac1cdf82b1588fa2999c49368dd24fd1953fafdf` |
| Boreas 1 | `Boreas 1_dev.txt` | `8dec7c18b39d5aa9b4dfc608c8a165ce6e066a85112e38905eaeb241c1932c64` |
| Poseidon North 1 | `Poseidon North 1_dev.txt` | `f8bea90b59bcfe72fd5e6d22d5a27b6fc2fe622c6b2df877065c206bb04c84e1` |
| Proteus 1ST2 | `Proteus 1ST2_dev.txt` | `16c656b14067b8df1af084332547e1bc1f6f0316e0bb438c4b56e00f7ebcd23e` |

Station counts, MD ranges, and max inclination (parsed from the files, not hard-coded — reproduced here as the confirmed result):

| Well | n_stations | MD range (m) | Max inclination (deg) |
|---|---|---|---|
| Poseidon 2 | 124 | 0.000 – 5356.000 | 4.990 |
| Boreas 1 | 134 | 0.000 – 5210.000 | 9.560 |
| Poseidon North 1 | 147 | 0.000 – 5287.518 | 4.626 |
| Proteus 1ST2 | 155 | −7.63e-07 – 5249.710 | 7.829 |

Total stations across all four wells: **560**.

Note on Proteus 1ST2's MD origin: the file's own first station reports MD = −7.63×10⁻⁷ m (a floating-point-scale value effectively at datum, not a meaningful negative depth). This value is preserved verbatim as parsed source data; it is never rounded, clamped, or silently treated as exactly 0.

Declared conventions, parsed from the files' own header blocks (not merely repeated from the design prompt): MD and TVD zero at the well datum and increasing downward; angles (INCL, AZIM_TN, AZIM_GN) in degrees; X/Y and DX/DY are grid coordinates in the CRS stated in each file's header (`GDA94 / MGA Zone 51`); Z is elevation, positive upward; the datum is the rotary table, referenced to MSL. MD's own unit is **not** explicitly stated in any of the four files' headers (only X/Y/DX/DY/Z/TVD are explicitly declared in metres, and the angle columns explicitly in degrees) — this gap is disclosed, not silently assumed (see Section 5, `MD_UNIT_NOT_EXPLICITLY_DECLARED`).

## 4. Theory implemented

Dogleg angle: `cos(β) = cos(I₁)·cos(I₂) + sin(I₁)·sin(I₂)·cos(A₂ − A₁)`.

Ratio factor: `RF = (2/β)·tan(β/2)` for `β` above a small-angle threshold (`1.0×10⁻⁹` rad); `RF → 1 + β²/12` (second-order Taylor expansion) below that threshold, to avoid the `0/0` numerical instability as `β → 0`.

Displacement per interval: `ΔTVD = (ΔMD/2)·(cos I₁ + cos I₂)·RF`; `ΔNorthing = (ΔMD/2)·(sin I₁ cos A₁ + sin I₂ cos A₂)·RF`; `ΔEasting = (ΔMD/2)·(sin I₁ sin A₁ + sin I₂ sin A₂)·RF`.

Dogleg severity: `DLS_deg/30m = (β_deg / ΔMD) × 30`.

Depth reference: `TVDSS_m = TVD_m − DatumElevation_m = −Z_m`.

All grid-coordinate computation uses `AZIM_GN` exclusively, never `AZIM_TN` and never a mix of the two — confirmed by code inspection and by a dedicated regression test (`tests/test_deviation.py`) using a fixture with `AZIM_TN` deliberately offset +5° from `AZIM_GN`.

## 5. Real four-well integration result (actual, re-run during this verification)

Command: `python3 run_integration_03.py` (build-time script; excluded from the packaged deliverable — see Section 9).

```
LAS loaded: ['Boreas_1', 'Poseidon_2', 'Poseidon_North_1', 'Proteus_1ST2']
LAS failed: []
Deviation loaded: ['Boreas_1', 'Poseidon_2', 'Poseidon_North_1', 'Proteus_1ST2']
Deviation failed: []

LAS MD fully inside survey MD coverage for all four wells (Poseidon_2, Boreas_1,
Poseidon_North_1, Proteus_1ST2) - confirmed, not assumed.

Total deviation stations across 4 wells: 560
Contracts passed: 4/4
Trajectory validation status: Poseidon_2=PASS, Boreas_1=PASS, Poseidon_North_1=PASS, Proteus_1ST2=WARNING
Total LAS extrapolated samples (expected 0): 0
```

Every deviation file also carries one WARNING-severity ingestion issue: `MD_UNIT_NOT_EXPLICITLY_DECLARED` (see Section 3). This is a disclosed inference, not a silent assumption, and does not block ingestion.

### 5.1 Trajectory validation residuals (minimum-curvature vs Petrel-source)

| Well | TVD max\|res\| (m) | TVD status | Easting max\|res\| (m) | Northing max\|res\| (m) | Overall |
|---|---|---|---|---|---|
| Poseidon 2 | 0.000888 | PASS | 0.0000065 | 0.0000249 | **PASS** |
| Boreas 1 | 0.001345 | PASS | 0.0000157 | 0.0000156 | **PASS** |
| Poseidon North 1 | 0.001948 | PASS | 0.0000048 | 0.0000289 | **PASS** |
| Proteus 1ST2 | 0.191488 | WARNING | 1.582982 | 0.880172 | **WARNING** |

Internal Petrel-source self-consistency (X ≈ X_wellhead+DX, Y ≈ Y_wellhead+DY, Z ≈ Datum−TVD) passes for all four wells, including Proteus 1ST2 — the discrepancy is specific to the minimum-curvature reconstruction, not a defect in the Petrel-supplied source data's own internal consistency.

### 5.2 Proteus 1ST2 discrepancy — disclosed finding, not silently corrected

Per explicit instruction, this discrepancy is reported as an observed pattern and is not "corrected," the survey is not modified, and no tolerance was loosened to force a pass.

Independent verification performed for this manifest (`compute_minimum_curvature_trajectory` applied to Proteus 1ST2's own I/A/AZIM_GN columns, then compared to the file's own supplied `DLS_source_deg_per_30m` column, station by station):

```
n stations: 155
Max |DLS_source - DLS_recomputed|: 3.59e-10 deg/30m   (essentially floating-point noise)
Mean |DLS_source - DLS_recomputed|: 4.61e-11 deg/30m

Split at MD = 4200 m:
  MD <= 4200 m (n=120): max DLS diff = 1.34e-10 deg/30m ; max TVD residual = 0.0110 m
  MD >  4200 m (n=35):  max DLS diff = 3.59e-10 deg/30m ; max TVD residual = 0.1915 m
```

Observed pattern: the file's own supplied dogleg severity is reproduced by independent recomputation from the file's own inclination/azimuth columns to within floating-point noise at every station, including below MD 4200 m. The positional (TVD, Easting, Northing) residual between the minimum-curvature-integrated trajectory and the Petrel-supplied trajectory, by contrast, is small and bounded above MD ≈ 4200 m and grows specifically below it, reaching a maximum TVD residual of 0.191 m at the deepest station.

This pattern is consistent with the Petrel-supplied trajectory below ~4200 m having been generated, resampled, or referenced differently than a direct minimum-curvature integration of the same file's own station-to-station I/A/AZIM_GN values (for example, a different tie-on, a smoothing step, or a different curvature algorithm applied over that interval). **This is stated as an unconfirmed hypothesis consistent with the observed evidence, not as a proven cause** — no independent record (e.g. an original Petrel project file, a directional-driller's report, or a second recomputation tool) was available to confirm it. No other explanation has been ruled in or out.

### 5.3 Depth-basis selection

`depth_basis_policy: petrel_source_trace` is declared uniformly for all four wells in `config/deviation_survey_contracts.yml`. This is the conservative default suggested for this project: it uses the trajectory the operator's own workflow (Petrel) already relies on for all downstream depth referencing, rather than substituting an independently recomputed trajectory that has not been demonstrated to be more reliable, and it never uses the minimum-curvature comparison to erase or paper over the Proteus 1ST2 discrepancy — that discrepancy remains visible in the QC outputs (Section 5.1, Section 5.2, `fig04_mc_vs_petrel_residuals.png`) regardless of which trajectory is used for mapping. This default was not overridden for any well in this increment.

### 5.4 LAS MD → TVD/TVDSS mapping

| Well | Depth basis used | n_samples | LAS MD range (m) | Extrapolated samples | TVD @ final LAS MD (m) | TVDSS @ final LAS MD (m) |
|---|---|---|---|---|---|---|
| Poseidon 2 | petrel_source_trace | 31897 | 490.0 – 5350.9507 | 0 | 5348.480271 | 5326.680272 |
| Boreas 1 | petrel_source_trace | 32845 | 200.0 – 5205.4258 | 0 | 5201.430892 | 5179.630893 |
| Poseidon North 1 | petrel_source_trace | 31310 | 508.0 – 5279.4917 | 0 | 5277.263362 | 5255.263362 |
| Proteus 1ST2 | petrel_source_trace | 31235 | 489.5 – 5249.5615 | 0 | 5245.031942 | 5223.231943 |

Interpolation method used: `piecewise_linear_station_interpolation` (a piecewise-linear interpolation between adjacent survey stations, explicitly distinguished in code and documentation from a per-sample minimum-curvature recomputation). LAS MD lies fully inside its own well's survey MD coverage for all four wells; zero LAS samples were extrapolated for any well.

## 6. Locked-baseline integrity check (actual)

Every file listed in Section 2 as locked was compared byte-for-byte against the Increment 2.1.1 baseline (`Poseidon_1D_MEM_Increment_02_v2.1.1.zip`) immediately before packaging:

```
p2mem/units.py               unchanged
p2mem/io/las.py               unchanged
p2mem/io/inventory.py         unchanged
config/las_curve_contracts.yml  unchanged
tests/test_units.py           unchanged
tests/test_las.py             unchanged
```

## 7. Notebook/source parity verification (actual, programmatic)

Method: every code cell in `03_Deviation_Survey_and_Depth_Framework.ipynb` whose source begins with `%%writefile` was parsed to extract its target path and body; each body was compared byte-for-byte against the corresponding file actually packaged in this deliverable.

```
Checked 23 %%writefile cells against packaged source files.
PARITY OK: 0 mismatches, 0 missing files.
```

`nbformat.validate()` confirmed the notebook is structurally valid (66 total cells). This check was run once on the working tree during development and again during the independent clean-room re-extraction of the final ZIP (Section 10).

## 8. Test-suite result (actual)

Command: `pip install -e .` followed by `python3 -m pytest -v`, from the increment tree.

```
241 passed in 0.49s
```

Breakdown by file: `tests/test_units.py` (94, locked/unchanged) + `tests/test_las.py` (64, locked/unchanged) + `tests/test_trajectory.py` (24, new) + `tests/test_deviation.py` (41, new) + `tests/test_depth_mapping.py` (18, new) = **241**. All three new test files use synthetic fixtures only; none requires the real project deviation files or LAS files to run. `p2mem.__version__` confirmed as `0.3.0` after the editable install.

Two implementation issues were found and fixed during test development (both self-identified, no real-data numbers affected):

- A ~1×10⁻⁶-degree dogleg/DLS numerical noise floor from `arccos` ill-conditioning near a zero dogleg angle, documented in `trajectory.py`'s docstring and reflected in the corresponding test's tolerance (`atol=1e-5` degrees; TVD/N/E displacement deltas remain accurate to `atol=1e-9` m and are unaffected). **Increment 3.1 update:** a later independent audit judged this noise floor a genuine defect (not merely a tolerance-worthy artifact) and replaced the `arccos` formulation with a numerically stable `arctan2`-based one that reports exactly `0.0` for identical stations — see `INCREMENT_03_1_MANIFEST.md`.
- A test-fixture-construction bug in `tests/test_deviation.py` (`_base_contract` computing a default SHA-256 against a fixture file that a specific test deliberately does not create) — fixed by falling back to a placeholder hash only when the fixture file does not exist, before that test's explicit override is applied.

## 9. Output files (actual, regenerated during this verification)

Written to `outputs/03_deviation_depth/`:

- `deviation_file_inventory.csv` — per-well header/provenance/contract-status inventory (1397 bytes)
- `trajectory_validation_summary.csv` — per-well minimum-curvature-vs-source residual summary (3858 bytes)
- `depth_reference_register.csv` — per-well depth-reference conventions and selected depth basis (2746 bytes)
- `las_depth_mapping_summary.csv` — per-well LAS MD→TVD/TVDSS mapping summary (979 bytes)
- `deviation_ingestion_issues.csv` — every ingestion issue (all four wells' `MD_UNIT_NOT_EXPLICITLY_DECLARED` warnings) (2234 bytes)
- `deviation_depth_manifest.json` — machine-readable combined summary of all of the above (5120 bytes)

Figures written to `outputs/03_deviation_depth/figures/`:

- `fig01_plan_view.png` — four-well plan view, Petrel-supplied source trajectory, GDA94/MGA Zone 51 coordinates
- `fig02_vertical_sections.png` — per-well vertical section (TVD vs horizontal displacement), depth axis increasing downward
- `fig03_md_vs_tvd.png` — MD vs TVD for all four wells
- `fig04_mc_vs_petrel_residuals.png` — minimum-curvature-vs-Petrel TVD residual per well; Proteus 1ST2 shown on its own axis scale so its larger discrepancy is visible, not hidden or clipped to match the other three wells
- `fig05_las_depth_mapping_coverage.png` — mapped LAS MD→TVD and MD→TVDSS coverage for all four wells

No raw station arrays and no full LAS datasets are packaged in these outputs; all six CSV/JSON files are per-well summary/register tables.

## 10. Clean-room ZIP verification (actual, on fresh extraction)

Performed on a fresh extraction of `Poseidon_1D_MEM_Increment_03.zip` into an independent directory, separate from the development and staging trees:

```
Packaged file count:            62 regular files (61 + this manifest); 71 ZIP entries (62 files + 9 directories) -> MATCH
Checksum re-verification:       every packaged file's SHA-256 (Section 11) reproduced exactly on the fresh extraction -> MATCH
pip install -e .                -> succeeded; p2mem.__version__ == "0.3.0"
python3 -m pytest -q            -> 241 passed
Real 4-LAS + 4-deviation integration (dev-only raw files, not packaged, copied in only for this verification):
    Loaded: 4/4 LAS, 4/4 deviation; 0 failures
    Total stations: 560; contracts passed: 4/4
    Trajectory validation: Poseidon_2/Boreas_1/Poseidon_North_1 = PASS, Proteus_1ST2 = WARNING
    Extrapolated LAS samples: 0
    -> every number identical to Section 5
Output byte-comparison (regenerated outputs vs. the outputs shipped in the ZIP):
    depth_reference_register.csv, deviation_depth_manifest.json, deviation_file_inventory.csv,
    las_depth_mapping_summary.csv, trajectory_validation_summary.csv -> byte-identical
    deviation_ingestion_issues.csv -> identical apart from one embedded absolute source-file path
      in its "context" column, which legitimately reflects the working directory the ingestion was
      run from in each environment; all severities, codes, messages, and well/file identifiers match
Figures:                        all 5 PNGs re-generated, opened, and verified as uncorrupted; visually
                                 consistent with the figures reviewed during development (Section 9)
Notebook:                       nbformat.validate() passed (66 cells); %%writefile/source parity
                                 re-check -> 0 mismatches, 0 missing files (23 cells checked)
Locked-file byte comparison:    p2mem/units.py, p2mem/io/las.py, p2mem/io/inventory.py,
                                 config/las_curve_contracts.yml, tests/test_units.py, tests/test_las.py
                                 -> unchanged, matches Section 6
```

All checks passed. No discrepancy was found other than the expected environment-dependent absolute path noted above.

## 11. Packaged file inventory and checksums

Total packaged regular files (excluding this manifest): **61**. Including this manifest: **62** regular files (plus 9 directory entries in the ZIP archive listing, for 71 total ZIP entries — this is a normal artifact of `zip -r` recording directory entries and is not a discrepancy).

SHA-256 of every packaged file except this manifest itself (computed from the staged deliverable tree immediately before archiving):

```
ce671c5f6373e6fddd60bfa9fff8c6e1df6fac99f36aee01ebfc28142df7f31d  02_LAS_Ingestion_and_Curve_Contracts.ipynb
c156b1909dc1ee77c949ba4779c3f6dd28ef8993c83a701e9e18d99b8d9c130f  03_Deviation_Survey_and_Depth_Framework.ipynb
6ae8074880e3ce91208a499292047b52070f0d10c19039b738ab9cd50002d345  INCREMENT_02_v2.1.1_MANIFEST.md
2a6ddc0288ed1dd0904a2953a2d6aa43f1bbad4a472ff93e9f1c1c11bce88f26  README.md
5ccfbab98f4e9ce935dd7f0bc4ab5ef87613ec0c4cce31f66bec9568fabe2837  config/deviation_survey_contracts.yml
99890577e078fefa6669d7abbd8163da0fd9d28d7f9e0ee18bf015015edf7d82  config/las_curve_contracts.yml
9655b3c03a583e761cbb253168757a4d47b7b8f14f881a777267bde2f493059a  outputs/02_las_inventory/las_curve_catalog.csv
056d234bbdb0e453efd0d508dc77328606f1b35de631a84f4f78d50b8af1cd22  outputs/02_las_inventory/las_curve_coverage.csv
e67deae5b9e023d3da54d2bcbf25d48b17da3849e2b2a901d1bc1e5f6a9805e2  outputs/02_las_inventory/las_file_inventory.csv
b61234b66726ff9711e752bd121056bcee9b562f5a8df5ace125f5823f111deb  outputs/02_las_inventory/las_ingestion_issues.csv
c30e57205e535a3c092a4fb184f6599ad74509fd74c242e3e6bd6e79a9e8a3b8  outputs/02_las_inventory/las_ingestion_manifest.json
5401aa9a3afc25bd5c533f6e111d64bb50fa145eba7d899f7e11c9e7bd0fdfe3  outputs/03_deviation_depth/depth_reference_register.csv
6c5038179506c2a095370adf1549fe9c2d1abf2157866ea450d7b0fa2d116965  outputs/03_deviation_depth/deviation_depth_manifest.json
d6052eef729c4c3199c23cbd625749bd03d43a8c1525862aee5dd2779e3945d7  outputs/03_deviation_depth/deviation_file_inventory.csv
f3f2fecbfbbd9e1948e08f630c28f4b9cce1209bed080a57bed934eac383f609  outputs/03_deviation_depth/deviation_ingestion_issues.csv
15e82708e653b0f34fe29ad6f20a78f072907608b6c4d37d165ed3e6729c6113  outputs/03_deviation_depth/figures/fig01_plan_view.png
104ff8e8621a915944f0c2779a8171e3e95907a56d3b8affef17d85bf494a9f7  outputs/03_deviation_depth/figures/fig02_vertical_sections.png
ea60020b7853fb6aa2b4af1abd45a59426288c36cc2aa3e0b71bb19d994f94ff  outputs/03_deviation_depth/figures/fig03_md_vs_tvd.png
b2e8eb47d93058f9fbdb8db4b9592427b1e97838cccc23cfbaf9453824a3c51e  outputs/03_deviation_depth/figures/fig04_mc_vs_petrel_residuals.png
3eab43cfd3cf738ee3d9910b3c78a25b987a318d9a6c5c9e043182db49c07e18  outputs/03_deviation_depth/figures/fig05_las_depth_mapping_coverage.png
1a1cfc4304924543f34193fc3fc9144602f060a5b73053afcf8df58b1397f22e  outputs/03_deviation_depth/las_depth_mapping_summary.csv
4f47f5037f577053b73462f9c9b1f9b08951e332c343e3076cae07fd65b1bf47  outputs/03_deviation_depth/trajectory_validation_summary.csv
23dee77984cc8726516fabff3b1b097cdb2fbf886706bd424e77bbfde31e6208  p2mem/__init__.py
43bbd59cf9b508f4ff2d14860e0e5fce466dbde66d6eebd547896fde9a850b4c  p2mem/depth_mapping.py
8208dc492cb7d3f17432fb7ced1d28d48e49363cbe5134202824d24419a2a2fa  p2mem/deviation_models.py
b47ec45d9fe73e0abe8964a741a35cf3ed182976bd7f400829adebf721f788c0  p2mem/io/__init__.py
718cf5f3e24324404cd700e25df04a12518cda5738936348789455c7cad8602d  p2mem/io/deviation.py
24e32d73bb2d54099749fcc39626b8acd969908e7c65f871b6613a77dcfea0b4  p2mem/io/deviation_inventory.py
68de13e917e19035ae6a71e724802d27a526ca79ca78b7f1d6b8edd5c39b123f  p2mem/io/inventory.py
f320d2be79c4755716e61c65f4252311a8828d2f370e429a66552e8b202491fb  p2mem/io/las.py
d109ecc4513a12734d795345b82f9582498c58a46b713218b30f7dbf72240a74  p2mem/models.py
aee7465a2f0843486324633e252973b2913b266c270ba9cca76d1764384bfeb7  p2mem/trajectory.py
35ac5090a5ac27b8d654528c1c8c484c785ac6fcd1f85efac53171b5a720883a  p2mem/units.py
e649390bed4c08b4930141a5be98c01440ada6aa1a5d9b4d6e2b0665385f798c  pyproject.toml
bf961187697d96606358fb8de8b7608ba38ed5188ae9ffc097a1613274c4a949  tests/fixtures/dev_duplicate_column.txt
9d5aa2551bd9640d5420c32c981e8a041a551a601e5a248c8fe8d87380f5faf9  tests/fixtures/dev_duplicate_md.txt
3afd6611db2033ec10aa95c9a4a1fb3e365a5c0ba43c925dd7e58068c418e2e6  tests/fixtures/dev_invalid_inclination.txt
af7e16abc4851381bb168ecde67ca611c3a291c730514fefc4931a265c59cd4b  tests/fixtures/dev_malformed_numeric_row.txt
f24f1e35cb0d92b5209dce97540c26086506220a87ede916fd39335018ea540f  tests/fixtures/dev_missing_column.txt
cc44a185786d3746ea67fdf7094daf79ba1e5d9fe9889321b6709812c7e04058  tests/fixtures/dev_near_zero_negative_origin.txt
0c23a513af1b24add368a2cc4dd12ffb9e604da66dce2dc6ed7c7076ea45feb7  tests/fixtures/dev_non_monotonic_md.txt
da8f160dc824b0e6d392b47283df90ed22ef2085ebda3879b303b0c193035e57  tests/fixtures/dev_nonfinite_token.txt
19f68792bae09e7197a2e4855acb47c33a5483e6efa4e3b67d3156c212d4a14c  tests/fixtures/dev_row_width_mismatch.txt
b154a1229e060a9c4f3569d74ae9855e5f1b28e1d82873f802cefb1378ad8ddc  tests/fixtures/dev_unsupported_angle_convention.txt
fd4421d4db8476dd5e37d3ec57625febbb9dff75c5487f4c5cd685c98a2bd0e7  tests/fixtures/dev_valid.txt
7704b4051bd607d0e692d8208494befcc914b35b29f4dbe5c14658da8d6bf790  tests/fixtures/duplicate_description.las
5c83a8ff8ae1b377d7feec147523ba01c5bd0931acdd17157befb5ad83f32a44  tests/fixtures/empty_mnemonic_with_description.las
96d35f90e9d172f04ba227d8853ddf70a089e3a69a97dd965ff63392b029f3c5  tests/fixtures/malformed_numeric_row.las
c23e0afb37bf8f1e79e240fa344bacb04497991ab68848f1862617ba689fcab6  tests/fixtures/mismatched_width_row.las
12117b46b8042c6c640b30b00e8b0d27670a2cc0561668f07de7d640c3fbe6f8  tests/fixtures/missing_null.las
0c7f7b10a7bd6430ad8c4e6691915de910fe4d476994af2e8c726464aa3bcca8  tests/fixtures/missing_well.las
0eb058d3209259ccd626a8d952efa6a7acf4b70b5f83ad07443e083597d78c0f  tests/fixtures/non_finite_token.las
5f95e2af86a2b9dd3e8ece0cf5c740629c3a84d15b1f3ea3cbbfc234ff649d92  tests/fixtures/non_monotonic_and_duplicate_md.las
7313cccfdc1866b5889a98ba1ca516ab034a373782dc6293eba0d78ecc01701e  tests/fixtures/standard_mnemonics.las
b31f975231df263678346096044ddbe81d1f9ca0d31d1dab4aa94b2d277c1147  tests/fixtures/vers_mismatch.las
019f97042a6935d3dcff062ccc44b408b614e6bf3c1e976d2ec00122aee37075  tests/fixtures/wrapped_unsupported.las
6df41a12c1b262656c24b42e9982332e33aaa05499c217b8fc8bd05dd59283ff  tests/test_depth_mapping.py
52439340ce716c45fde705161bc9f42cb333552317fb7319d4cb6ed1381c24ad  tests/test_deviation.py
eafd1a5592d02ecaeaad10bb1120b51212ed8fcf7f42c7bcf708713435aa91f3  tests/test_las.py
b39e91e0061b368aadfb742878063eeb1de8852b85c7625dc60f08662c6683fd  tests/test_trajectory.py
c5ed260fab4f1328531d1d916f2f093d3ec5d6e63953aa3c2930358ba32e6017  tests/test_units.py
```

## 12. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational 1D Mechanical Earth Model**. Nothing in Increment 3 constitutes an independent calibration event. The near-exact minimum-curvature-vs-Petrel agreement for three wells demonstrates internal numerical consistency of this codebase's trajectory engine against Petrel's own supplied trajectory — it is not a field calibration and does not raise the assurance tier.

## 13. Known limitations

- MD's unit is inferred, not explicitly declared in any of the four source files (Section 3); this is disclosed as a permanent WARNING on every load, not silently assumed away.
- The Proteus 1ST2 trajectory discrepancy below ~MD 4200 m is unresolved and its cause is unconfirmed (Section 5.2). The `petrel_source_trace` depth basis was selected as the conservative default for downstream mapping; this does not resolve or hide the discrepancy, which remains visible in the QC outputs.
- Poseidon North 1's well type is recorded as `UNDEFINED` in its own source file header; this is preserved verbatim, not inferred or corrected.
- This increment performs deviation-survey ingestion, trajectory validation, and depth mapping only. No checkshot, time-depth, formation-top, petrophysical, pore-pressure, elastic-property, rock-strength, stress, or wellbore-stability work has been performed.

## 14. Increment 4 status

**Increment 4 has not been started.** No checkshot loading, time-depth conversion, formation-top processing, or petrophysical work of any kind is present in this deliverable.
