# Increment 3.1.1 Manifest — Packaging-Only Corrective Patch (Colab Execution Order + Checksum Ledger)

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Patch classification:** Increment 3.1.1 — Colab notebook execution-order and audit-ledger correction (packaging/notebook only)
**Package version:** `p2mem` 0.3.1 — **unchanged**, since no Python package implementation was modified.
**Corrects:** Increment 3.1 (`p2mem` 0.3.1, `Poseidon_1D_MEM_Increment_03_v3.1.zip`) — see `INCREMENT_03_1_MANIFEST.md`.
**Scope:** strictly a packaging/notebook correction. No Increment 4 work (checkshot, time-depth, formation tops, petrophysics, pore pressure, mechanical properties, stress modelling, wellbore-stability) was started or performed.
**Date generated:** 2026-09-02

This manifest records what was actually corrected, tested, and re-verified for Increment 3.1.1. Every number below is taken directly from a command run against the code in this deliverable during clean-room verification — nothing here is an assumed, remembered, or previously reported value carried over without re-confirmation.

---

## 1. Confirmed Colab runtime defect

Increment 3.1 passed its static notebook/source parity audit (24 `%%writefile` cells, 0 mismatches), but a real Google Colab `Run all` from a fresh runtime exposed a defect that static parity checking cannot catch: **execution order**, not source content.

Google Colab's initial working directory is `/content`, not the project folder. The notebook defines `PROJECT_ROOT = "/content/drive/MyDrive/Poseidon_1D_MEM"` (Step 2), but Increment 3.1 did not change the working directory to `PROJECT_ROOT` until a `%cd` cell in Step 8 — several relative `%%writefile` cells later (Step 6 onward). On a genuinely fresh runtime, the first `%%writefile` targeting a subdirectory (`p2mem/__init__.py`) failed with:

```
FileNotFoundError: [Errno 2] No such file or directory: 'p2mem/__init__.py'
```

(`pyproject.toml`, the very first `%%writefile`, has no subdirectory component and would have silently succeeded by writing into `/content` instead of the project folder — masking the defect for one cell before it surfaced.) The user worked around this by manually inserting `os.chdir(PROJECT_ROOT)` and rerunning; after that manual fix, the real Colab completion gate passed all six checks. This patch makes that manual step unnecessary.

## 2. Correction made

A new **Step 2b** cell pair (one markdown, one code) was inserted into `03_Deviation_Survey_and_Depth_Framework.ipynb`, immediately after Step 2 (which defines `PROJECT_ROOT` and validates the locked Increment 2.1.1 foundation is present) and strictly before Step 6 (the first relative `%%writefile` cell):

```python
os.chdir(PROJECT_ROOT)

if Path.cwd().resolve() != Path(PROJECT_ROOT).resolve():
    raise RuntimeError(
        f"Failed to enter the project root. "
        f"Expected {PROJECT_ROOT}, actual working directory: {Path.cwd()}"
    )

if not Path("p2mem").is_dir():
    raise RuntimeError(
        f"Required p2mem directory is missing under {PROJECT_ROOT}. "
        "Extract the approved Increment package before running this notebook."
    )

print("Working directory confirmed:", Path.cwd())
```

(`import os` and `from pathlib import Path` are already in scope from the immediately preceding Step 2 cell.)

This satisfies every stated requirement:

1. The working-directory change now occurs before every relative `%%writefile` (Step 2b is cell-index 2 among code cells; the first `%%writefile` is cell-index 6 — see Section 4).
2. The fix does not rely on the notebook being opened from its Google Drive folder — it explicitly `chdir`s there regardless of the notebook's own starting directory.
3. No empty substitute `p2mem` directory is ever created — a missing foundation raises `RuntimeError` and stops, exactly as the locked-foundation check in Step 2 already does for its own files.
4. The existing locked-foundation validation (Step 2) is retained unchanged and still runs first, using absolute paths (`os.path.join(PROJECT_ROOT, f)`), so it was never affected by the working-directory defect itself.
5. `PROJECT_ROOT` remains the exact literal `"/content/drive/MyDrive/Poseidon_1D_MEM"` — not modified.
6. The pre-existing `%cd /content/drive/MyDrive/Poseidon_1D_MEM` cell in Step 8 (immediately before `pip install -q -e .`) is **retained**, now explicitly documented in its own markdown as a defensive, harmless second confirmation — it is not, and (with Step 2b now first) cannot be, the first working-directory change.
7. The notebook now supports Runtime → Restart session and Run all from an initial `/content` working directory — verified by actual execution, not assumed (Section 5).

Two markdown notes were added elsewhere for traceability: a "Packaging patch note (v3.1.1)" paragraph in the phase header (alongside the existing v3.1 corrective-patch note), and a note on the Step 8 `%cd` cell clarifying its now-secondary role.

## 3. What was NOT touched

This is a packaging/notebook-execution-order correction only. The following were verified byte-identical to the approved Increment 3.1 build (`cmp`, not merely "should be identical" — see Section 6):

`p2mem/units.py`, `p2mem/models.py`, `p2mem/io/las.py`, `p2mem/io/inventory.py`, `p2mem/trajectory.py`, `p2mem/deviation_models.py`, `p2mem/depth_mapping.py`, `p2mem/io/deviation.py`, `p2mem/io/deviation_inventory.py`, `p2mem/__init__.py`, `pyproject.toml`, `config/las_curve_contracts.yml`, `config/deviation_survey_contracts.yml`, `tests/test_units.py`, `tests/test_las.py`, `tests/test_trajectory.py`, `tests/test_deviation.py`, `tests/test_depth_mapping.py`, `tests/test_deviation_inventory.py`, all 22 test fixture files, all six deterministic output files, all five QC figures, and `README.md`.

`INCREMENT_03_MANIFEST.md` and `INCREMENT_03_1_MANIFEST.md` are carried forward unmodified from Increment 3.1. `p2mem.__version__` remains `0.3.1` — no package implementation changed, so no version bump was made or is warranted.

Explicitly out of scope, not implemented, not started: checkshot loading, time-depth relationships, formation-top correction, any petrophysical interpretation, normal-compaction-trend fitting, pore-pressure prediction, elastic-property calculation, rock-strength correlation, in-situ stress modelling, wellbore-stability screening, or mud-weight recommendations. **Increment 4 has not been started.**

## 4. Notebook-order regression protection (static checks on the actual cell source)

A new dev-only script, `verify_execution_order_03_1_1.py` (not packaged — mirrors the existing `verify_notebook_parity_03.py` dev tool), parses the regenerated notebook's real cells and proves, programmatically:

- `PROJECT_ROOT` is defined (code-cell index 1) before the `os.chdir(PROJECT_ROOT)` operation (code-cell index 2).
- `os.chdir(PROJECT_ROOT)` occurs before the first `%%writefile` cell (code-cell index 6).
- All 24 `%%writefile` targets are relative paths with no `..` escape — each therefore resolves strictly underneath `PROJECT_ROOT` given the confirmed `chdir` ordering above.
- No code cell before the `chdir` performs a relative `%%writefile` — the notebook does not depend on a pre-existing Colab working directory.
- All 24 `%%writefile` cell bodies remain byte-for-byte identical to their packaged target files (same method as, and consistent with, `verify_notebook_parity_03.py`).

**Actual result:** all five checks passed.

## 5. Realistic execution-order smoke test (actual execution, not static-only)

Static parity checking is exactly what Increment 3.1 already had, and it did not catch this defect — so this patch's verification also *actually executes* the notebook's relevant cells, not just inspects their source text.

**Method:** `verify_execution_order_03_1_1.py` builds a realistic simulated Colab layout on this build machine, using the notebook's own unmodified literal path (`/content/drive/MyDrive/Poseidon_1D_MEM`), pre-populated with a realistic Increment 2.1.1 locked foundation (copied from the real approved files, including the directories — `p2mem/`, `p2mem/io/`, `config/`, `tests/`, `tests/fixtures/` — that a genuine prior-increment Drive folder would already contain). The process's own working directory is set to `/content` (Colab's actual default) before each test.

**Test B1 — confirms the original defect is real, not assumed:** running Step 2 followed directly by the 24 `%%writefile` cells *in their original (pre-3.1.1) order, without Step 2b*, actually raises `FileNotFoundError` writing `p2mem/__init__.py` — reproducing the exact real Colab error, from actual execution of the real cell source, with the real target paths. This confirms the smoke test exercises the genuine failure mode and did not construct a straw-man reproduction.

**Test B2 — confirms the fix actually works, from actual execution:** running the *corrected* cell order (Step 2 → Step 2b → the 24 `%%writefile` cells) from the same `/content` starting directory: the working directory after Step 2b is exactly `PROJECT_ROOT`; nothing is written directly under `/content` (only under the `PROJECT_ROOT` subtree reached via `/content/drive`); and all 24 files are written to their correct relative locations underneath `PROJECT_ROOT`, with content matching their packaged source exactly.

**Actual result:**

```
=== PART A: static structural checks on real notebook cell source ===
  [PASS] PROJECT_ROOT defined in code-cell index 1
  [PASS] os.chdir(PROJECT_ROOT) occurs in code-cell index 2 (before first %%writefile at 6)
  [PASS] All 24 %%writefile targets are relative paths with no '..' escape
  [PASS] No relative write occurs before the chdir
  [PASS] All 24 %%writefile cell bodies are byte-for-byte identical to their packaged target files.

=== PART B: realistic execution-order smoke test (actual execution, not static-only) ===
  -- B1: confirming the ORIGINAL defect (no chdir before first write) actually fails --
    [CONFIRMED] Without the chdir, writing 'p2mem/__init__.py' raises FileNotFoundError(2, 'No such file or directory')
  -- B2: running the CORRECTED cell order end-to-end from a fresh /content-style cwd --
    [PASS] Working directory after Step 2b is exactly PROJECT_ROOT: /content/drive/MyDrive/Poseidon_1D_MEM
    [PASS] Nothing was written directly under /content - only under PROJECT_ROOT via the 'drive' mount subtree.
    [PASS] All 24 relative %%writefile targets were actually written underneath PROJECT_ROOT, with correct content.

ALL CHECKS PASSED
```

This is reported as an actual execution-order proof, not only static parity.

## 6. Byte-identity verification against approved Increment 3.1

```
$ cmp p2mem/units.py <v3.1>/p2mem/units.py                                    -> byte-identical
$ cmp p2mem/models.py <v3.1>/p2mem/models.py                                  -> byte-identical
$ cmp p2mem/io/las.py <v3.1>/p2mem/io/las.py                                  -> byte-identical
$ cmp p2mem/io/inventory.py <v3.1>/p2mem/io/inventory.py                      -> byte-identical
$ cmp p2mem/trajectory.py <v3.1>/p2mem/trajectory.py                          -> byte-identical
$ cmp p2mem/deviation_models.py <v3.1>/p2mem/deviation_models.py              -> byte-identical
$ cmp p2mem/depth_mapping.py <v3.1>/p2mem/depth_mapping.py                    -> byte-identical
$ cmp p2mem/io/deviation.py <v3.1>/p2mem/io/deviation.py                      -> byte-identical
$ cmp p2mem/io/deviation_inventory.py <v3.1>/p2mem/io/deviation_inventory.py  -> byte-identical
$ cmp p2mem/__init__.py <v3.1>/p2mem/__init__.py                              -> byte-identical
$ cmp pyproject.toml <v3.1>/pyproject.toml                                    -> byte-identical
$ cmp config/las_curve_contracts.yml <v3.1>/config/...                       -> byte-identical
$ cmp config/deviation_survey_contracts.yml <v3.1>/config/...                -> byte-identical
$ cmp tests/test_units.py <v3.1>/tests/test_units.py                          -> byte-identical
$ cmp tests/test_las.py <v3.1>/tests/test_las.py                              -> byte-identical
$ cmp tests/test_trajectory.py <v3.1>/tests/test_trajectory.py                -> byte-identical
$ cmp tests/test_deviation.py <v3.1>/tests/test_deviation.py                  -> byte-identical
$ cmp tests/test_depth_mapping.py <v3.1>/tests/test_depth_mapping.py          -> byte-identical
$ cmp tests/test_deviation_inventory.py <v3.1>/tests/test_deviation_inventory.py -> byte-identical
```

All 19 checked files are byte-identical. A directory-level diff (`diff -rq`, excluding build caches) between the full Increment 3.1 build tree and the Increment 3.1.1 build tree found exactly **two** differing files in the entire project: `03_Deviation_Survey_and_Depth_Framework.ipynb` (the intended change) and `build_notebook_03.py` (the dev-only, unpackaged notebook-generation script). Nothing else in the tree — including all six deterministic outputs, all five QC figures, all 22 test fixtures, and `README.md` — differs at all.

The six deterministic outputs (`depth_reference_register.csv`, `deviation_depth_manifest.json`, `deviation_file_inventory.csv`, `deviation_ingestion_issues.csv`, `las_depth_mapping_summary.csv`, `trajectory_validation_summary.csv`) and the five QC figures (`fig01_plan_view.png` … `fig05_las_depth_mapping_coverage.png`) were each individually `cmp`-verified byte-identical to their Increment 3.1 counterparts (they were not regenerated, since no code that produces them changed).

## 7. Test suite — actual results

```
$ pytest -q
...
261 passed in 0.57s
```

Identical count to Increment 3.1, as expected — no test file changed. `p2mem.__version__` confirmed as `0.3.1`.

## 8. Notebook validation

- `nbformat.validate()` on the regenerated `03_Deviation_Survey_and_Depth_Framework.ipynb`: **passed, no errors.** Cell count: **69** (67 in Increment 3.1 + 2 new cells for Step 2b: one markdown, one code).
- `nbformat.validate()` on `02_LAS_Ingestion_and_Curve_Contracts.ipynb` (unchanged, carried forward): **passed, no errors.**
- Both notebooks confirmed to have **zero saved execution outputs** (checked via `nbformat`: 0 of 69 / 0 of the Increment-2 notebook's code cells have a populated `outputs` field) — neither notebook was executed and saved with outputs; they are delivered as source only, as in every prior increment.
- `%%writefile`-vs-packaged-source parity (`verify_notebook_parity_03.py`): **24 cells checked, 0 mismatches, 0 missing files** — unchanged from Increment 3.1, since none of the 24 target files' content changed (only their position in the cell sequence relative to the new Step 2b cell).

## 9. Checksum ledger

`INCREMENT_03_1_1_SHA256SUMS.txt` (new) contains the SHA-256 of every regular file in the final ZIP, sorted deterministically by relative POSIX path, **except the ledger file itself** — a checksum file cannot contain its own final checksum, since the ledger's own bytes (and therefore its hash) are not fixed until it is written. This is stated explicitly inside the ledger file. The final ZIP's own SHA-256 is reported separately, in the completion record (Section 13 below and the delivery message), since it is only known once the ZIP itself is assembled around the ledger.

## 10. Delivery

Deliverable: `Poseidon_1D_MEM_Increment_03_v3.1.1.zip`.

## 11. Changed and added files (complete list, relative to approved Increment 3.1)

**Changed:**
- `03_Deviation_Survey_and_Depth_Framework.ipynb` — Step 2b inserted (working-directory preflight); phase-header and Step 8 markdown updated for traceability; cell count 67 → 69.

**Added (packaged):**
- `INCREMENT_03_1_1_MANIFEST.md` (this file)
- `INCREMENT_03_1_1_SHA256SUMS.txt`

**Added (dev-only, NOT packaged):**
- `verify_execution_order_03_1_1.py` — the Section 4/5 regression-and-smoke-test script.

**Unchanged (all other packaged files):** every implementation module, both contract YAML files, every test file and fixture, every deterministic output, every QC figure, `README.md`, `pyproject.toml`, `p2mem/__init__.py`, `INCREMENT_02_v2.1.1_MANIFEST.md`, `INCREMENT_03_MANIFEST.md`, `INCREMENT_03_1_MANIFEST.md`, and `02_LAS_Ingestion_and_Curve_Contracts.ipynb`.

## 12. Stop condition

This packaging-only patch addresses ONLY the Colab execution-order defect and the missing checksum ledger. No Increment 4 work was performed, started, or is included in this deliverable.

## 13. Final ZIP identity

The final packaged ZIP's SHA-256 is reported in the accompanying completion record and delivery message, computed from the final packaged bytes after a clean-room extraction — not assumed to survive from a pre-packaging computation.
