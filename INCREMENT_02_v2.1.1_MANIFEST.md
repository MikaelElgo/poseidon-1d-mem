# Increment 2.1.1 Manifest — Notebook/Source Synchronization Patch

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.2.1 (unchanged — this is a packaging/notebook synchronization revision, not a scientific or package-version change)
**Builds on:** Increment 2.1 (`Poseidon_1D_MEM_Increment_02_v2.1.zip`) — its scientific implementation, LAS-parsing architecture, curve contracts, canonical naming, conversion logic, and test suite are **unchanged and preserved**. This patch corrects only a notebook/source synchronization gap identified by an independent audit.
**Date generated:** 2026-09-01

This manifest records what was actually corrected, tested, and re-verified for Increment 2.1.1. Every number in this document is taken directly from a command run against the code in this deliverable — nothing here is an assumed or previously-remembered value.

---

## 1. What this patch does and does not do

**Does:** Regenerates `02_LAS_Ingestion_and_Curve_Contracts.ipynb` so that every `%%writefile` cell body is byte-for-byte identical to its corresponding packaged source file.

**Does not:** Redesign, refactor, simplify, or extend the implementation; alter equations, constants, LAS parsing, curve contracts, canonical naming, conversion logic, test expectations, or real-data outputs; change scientific scope; start Increment 3; change the `p2mem` package version (remains `0.2.1`).

## 2. Audit finding and correction applied

An independent audit of the Increment 2.1 deliverable found that 3 of the notebook's 20 `%%writefile` cells were stale relative to the packaged source files (the other 17 were already byte-for-byte identical):

| # | Cell target | Issue found | Correction applied |
|---|---|---|---|
| 1 | `pyproject.toml` | Notebook wrote `version = "0.2.0"`; packaged/required version is `0.2.1`. | Notebook `%%writefile` body replaced with the exact packaged `pyproject.toml` (`version = "0.2.1"`). |
| 2 | `p2mem/__init__.py` | Notebook wrote `__version__ = "0.2.0"` and lacked the Increment 2.1 correction documentation in the module docstring. | Notebook `%%writefile` body replaced with the exact packaged `p2mem/__init__.py` (`__version__ = "0.2.1"`, full Increment 2.1 docstring). |
| 3 | `README.md` | Notebook wrote the old Increment 2 / v0.2.0 status section, referenced the old (non-existent, at that point) manifest, and omitted the Increment 2.1 corrections. | Notebook `%%writefile` body replaced with the exact packaged, corrected `README.md`. |

No other cell was touched. No Markdown/theory cell, no execution-order cell, and no other `%%writefile` cell was modified.

## 3. Notebook-source parity verification (actual, programmatic)

Method: every code cell whose source begins with `%%writefile` was parsed to extract its target path and body; each body was compared byte-for-byte (`==` on the decoded text, not a normalized or whitespace-trimmed comparison) against the corresponding file actually packaged in this deliverable.

```
Total %%writefile cells checked: 20
Mismatch count: 0
```

This check was run twice: once immediately after the patch (on the working tree) and once again during the independent clean-room re-extraction of the final ZIP (Section 7).

## 4. Test-suite result (actual)

Command run: `pip install -e .` followed by `python3 -m pytest -v`, from a clean copy of the corrected package tree (not the original Increment 2.1 tree — this run used the patched files).

```
158 passed in 0.95s
```

`p2mem.__version__` confirmed as `0.2.1` after the editable install. This is the same 158-test combined suite as Increment 2.1 (94 `tests/test_units.py` + 64 `tests/test_las.py`) — no test was added, removed, or altered by this patch, since `tests/` was not part of the stale-cell list.

## 5. Real four-well integration result (actual)

Re-run against the four exact raw LAS files (SHA-256 identity unchanged from Increment 2.1 — see Section 8), using the corrected package tree:

```
Loaded: ['Poseidon_2', 'Boreas_1', 'Poseidon_North_1', 'Proteus_1ST2']
Failed: []

Poseidon 2 rows: 31897 (expected 31897) -> MATCH
Poseidon 2 MD range: 490.0-5350.9507 (expected ~490.0-5350.9507)
Total rows across 4 wells: 127287 (expected 127287) -> MATCH
Boreas 1 rows: 32845 (expected 32845)
Poseidon North 1 rows: 31310 (expected 31310)
Proteus 1ST2 rows: 31235 (expected 31235)
Contracts passed: 4/4
Unresolved required curves across all loaded wells: 0 (expected 0)
```

All figures are identical to Increment 2.1 — this patch touches packaging/documentation only, not parsing or resolution logic.

## 6. Output reproducibility (actual)

All five files under `outputs/02_las_inventory/` were regenerated from the real four-well run above and compared byte-for-byte against the versions packaged in this deliverable:

```
las_curve_catalog.csv:        IDENTICAL
las_curve_coverage.csv:       IDENTICAL
las_file_inventory.csv:       IDENTICAL
las_ingestion_issues.csv:     IDENTICAL
las_ingestion_manifest.json:  IDENTICAL
```

## 7. Archive verification (actual, clean-room re-extraction of the final ZIP)

`Poseidon_1D_MEM_Increment_02_v2.1.1.zip` was extracted into a fresh temporary directory, independent of the working tree used to build it, and every check above was repeated against that extraction:

- File count: 29 (28 packaged files + this manifest) — matches Section 9.
- Checksum verification: all 28 packaged-file SHA-256 values match Section 9 exactly; zero mismatches, zero missing, zero extra.
- Notebook JSON validation: `nbformat.validate()` passed; 55 cells.
- Notebook/source parity: 20 `%%writefile` cells checked, 0 mismatches (Section 3 repeated against the extracted copy).
- Editable installation: `pip install -e .` succeeded; `p2mem.__version__ == "0.2.1"`.
- Full test suite: `158 passed`.
- Four-well integration: all row counts, contract statuses, and unresolved-curve counts identical to Section 5.
- Inventory-output reproducibility: all five files identical to Section 6.

## 8. Raw LAS file identity (SHA-256, for provenance only — files not included)

Unchanged from Increment 2 / 2.1.

| Well | Source filename | Rows | SHA-256 |
|---|---|---:|---|
| Poseidon 2 | Poseidon_2_logs.las | 31,897 | `4684864b2d4b37be1f132cc264d4672055865aa283b4fc7d7ef702f5d9a86828` |
| Boreas 1 | Boreas_1_logs.las | 32,845 | `b2fdf60cd9dfeb7843ffa211232d909e7e76b6122cb2fd84f212edc2371dd61f` |
| Poseidon North 1 | Poseidon_North_1_logs.las | 31,310 | `ca3fe7b6547a72559127fab8c9540643600f4207efd067b84a08ad219354d78f` |
| Proteus 1ST2 | Proteus_1ST2_logs.las | 31,235 | `ffb100de5fdd5e0639eee71a59a2602aad19a386116d48b8110912e58939e92f` |

## 9. Files included in this deliverable

`Poseidon_1D_MEM_Increment_02_v2.1.1.zip` contains exactly **28 files** (SHA-256 of each as packaged), **plus this manifest itself (29 files total)**. This count was computed programmatically from the staged deliverable directory, not assumed or hand-counted. This manifest's own hash is intentionally omitted from the table below (a file cannot meaningfully declare its own hash before it is finished being written).

Only one file's hash differs from the Increment 2.1 (v2.1) manifest: `02_LAS_Ingestion_and_Curve_Contracts.ipynb` (the file this patch corrected). Every other file's hash is unchanged from Increment 2.1, confirming that no scientific, parsing, contract, or test content was touched.

| Path | SHA-256 |
|---|---|
| `02_LAS_Ingestion_and_Curve_Contracts.ipynb` | `ce671c5f6373e6fddd60bfa9fff8c6e1df6fac99f36aee01ebfc28142df7f31d` |
| `README.md` | `1d53d338fee738791f7092f4d8ba5a5154258acabefb4219508a4efbc5f979aa` |
| `config/las_curve_contracts.yml` | `99890577e078fefa6669d7abbd8163da0fd9d28d7f9e0ee18bf015015edf7d82` |
| `outputs/02_las_inventory/las_curve_catalog.csv` | `9655b3c03a583e761cbb253168757a4d47b7b8f14f881a777267bde2f493059a` |
| `outputs/02_las_inventory/las_curve_coverage.csv` | `056d234bbdb0e453efd0d508dc77328606f1b35de631a84f4f78d50b8af1cd22` |
| `outputs/02_las_inventory/las_file_inventory.csv` | `e67deae5b9e023d3da54d2bcbf25d48b17da3849e2b2a901d1bc1e5f6a9805e2` |
| `outputs/02_las_inventory/las_ingestion_issues.csv` | `b61234b66726ff9711e752bd121056bcee9b562f5a8df5ace125f5823f111deb` |
| `outputs/02_las_inventory/las_ingestion_manifest.json` | `c30e57205e535a3c092a4fb184f6599ad74509fd74c242e3e6bd6e79a9e8a3b8` |
| `p2mem/__init__.py` | `f0c29ee883891c6b000a8c2dafbeba7840deb306515db750e407b34198aab2c3` |
| `p2mem/io/__init__.py` | `b47ec45d9fe73e0abe8964a741a35cf3ed182976bd7f400829adebf721f788c0` |
| `p2mem/io/inventory.py` | `68de13e917e19035ae6a71e724802d27a526ca79ca78b7f1d6b8edd5c39b123f` |
| `p2mem/io/las.py` | `f320d2be79c4755716e61c65f4252311a8828d2f370e429a66552e8b202491fb` |
| `p2mem/models.py` | `d109ecc4513a12734d795345b82f9582498c58a46b713218b30f7dbf72240a74` |
| `p2mem/units.py` | `35ac5090a5ac27b8d654528c1c8c484c785ac6fcd1f85efac53171b5a720883a` |
| `pyproject.toml` | `3175bfdd19461752b993601c7c42100aa8e40852c939daadfc905b4ca61de514` |
| `tests/fixtures/duplicate_description.las` | `7704b4051bd607d0e692d8208494befcc914b35b29f4dbe5c14658da8d6bf790` |
| `tests/fixtures/empty_mnemonic_with_description.las` | `5c83a8ff8ae1b377d7feec147523ba01c5bd0931acdd17157befb5ad83f32a44` |
| `tests/fixtures/malformed_numeric_row.las` | `96d35f90e9d172f04ba227d8853ddf70a089e3a69a97dd965ff63392b029f3c5` |
| `tests/fixtures/mismatched_width_row.las` | `c23e0afb37bf8f1e79e240fa344bacb04497991ab68848f1862617ba689fcab6` |
| `tests/fixtures/missing_null.las` | `12117b46b8042c6c640b30b00e8b0d27670a2cc0561668f07de7d640c3fbe6f8` |
| `tests/fixtures/missing_well.las` | `0c7f7b10a7bd6430ad8c4e6691915de910fe4d476994af2e8c726464aa3bcca8` |
| `tests/fixtures/non_finite_token.las` | `0eb058d3209259ccd626a8d952efa6a7acf4b70b5f83ad07443e083597d78c0f` |
| `tests/fixtures/non_monotonic_and_duplicate_md.las` | `5f95e2af86a2b9dd3e8ece0cf5c740629c3a84d15b1f3ea3cbbfc234ff649d92` |
| `tests/fixtures/standard_mnemonics.las` | `7313cccfdc1866b5889a98ba1ca516ab034a373782dc6293eba0d78ecc01701e` |
| `tests/fixtures/vers_mismatch.las` | `b31f975231df263678346096044ddbe81d1f9ca0d31d1dab4aa94b2d277c1147` |
| `tests/fixtures/wrapped_unsupported.las` | `019f97042a6935d3dcff062ccc44b408b614e6bf3c1e976d2ec00122aee37075` |
| `tests/test_las.py` | `eafd1a5592d02ecaeaad10bb1120b51212ed8fcf7f42c7bcf708713435aa91f3` |
| `tests/test_units.py` | `c5ed260fab4f1328531d1d916f2f093d3ec5d6e63953aa3c2930358ba32e6017` |

## 10. Files deliberately excluded from this deliverable

- `data/raw/logs/Poseidon_2_logs.las`, `Boreas_1_logs.las`, `Poseidon_North_1_logs.las`, `Proteus_1ST2_logs.las` — the four raw, immutable input files. Identity recorded by SHA-256 in Section 8.
- `run_integration.py` — a build-time-only verification script. Not part of the installable package; the same steps are implemented as notebook cells.
- `build_notebook_02.py` — the build-time script used to programmatically assemble the notebook from the tested source files.
- `INCREMENT_02_v2.1_MANIFEST.md` — superseded by this manifest; not repackaged here.
- Increment 1 / 1.1 artifacts and the original Increment 2 (v0.2.0) and Increment 2.1 (v0.2.1, pre-patch) deliverable ZIPs — already delivered separately; not repackaged here.
- `.pytest_cache/`, `p2mem.egg-info/`, `__pycache__/` — build/tool artifacts, not source.

## 11. How to reproduce this manifest

```bash
pip install -e .
pytest -v                     # expect: 158 passed
```

The exact file count and per-file SHA-256 in Section 9 were computed with:

```python
import hashlib
from pathlib import Path
files = sorted(p for p in Path(".").rglob("*") if p.is_file())
print(len(files))
for f in files:
    print(hashlib.sha256(f.read_bytes()).hexdigest(), f)
```

run against the staged deliverable directory (before this manifest file itself was added to it) — never hand-counted or assumed.

Notebook/source parity was reproduced with a script that parses every `%%writefile` code cell (via `nbformat`), extracts its target path and body, and compares that body against `Path(path).read_text()` for the corresponding packaged file — reporting a mismatch count, expected `0` across all 20 cells.

To reproduce the real four-well integration result, place the four raw LAS files (matching the SHA-256 values in Section 8) under `data/raw/logs/` and run `02_LAS_Ingestion_and_Curve_Contracts.ipynb` (Google Colab; checks for the four exact filenames and stops cleanly with a named list of any that are missing).

## 12. Assurance-level statement

This patch changes notebook/documentation packaging only — no scientific, parsing, contract, naming, conversion, or test content was altered. It does not change the project's assurance classification: **Tier C — Screening-Level / Uncalibrated Educational**. Increment 3 (deviation-survey processing or any later-phase geomechanical calculation) has **not** been started.
