# Increment 4.1.2 Manifest — Colab Line-Ending Reproducibility and Truthful Completion-Gate Patch

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level / Uncalibrated Educational)
**Author:** Mikael Elgo
**Package version:** `p2mem` 0.4.1.1 (**unchanged** — this is a packaging/notebook-only patch; no `.py` implementation file changes)
**Corrective patch of:** Increment 4.1.1 (`Poseidon_1D_MEM_Increment_04_v4.1.1.zip`, `p2mem` 0.4.1.1)
**Date generated:** 2026-09-02

This manifest records what was actually corrected, and how it was actually verified, for Increment 4.1.2. Increment 4.1.2 is a **strictly scoped packaging and notebook-execution correction only**: it does not begin Increment 5, and it implements no formation-top correction, lithology interpretation, density modelling, pore-pressure prediction, elastic properties, rock strength, stress modelling, or wellbore-stability screening. No numerical method, contract, raw-data policy, or scientific output is changed. Both defects corrected here were found by a **real Google Colab fresh-runtime execution** of the Increment 4.1.1 notebook, not by any check that could run in this (Linux/Python, non-Colab) environment — that fact, and its consequences for what could and could not be independently re-verified here, is stated explicitly throughout this document rather than glossed over.

---

## 1. The two real defects, and why prior verification did not catch them

### 1.1 Defect 1 — Colab reconstructs the CRLF fixture as LF via `%%writefile`

**Observed (real Colab run):** `1 failed, 384 passed`, with the failure `tests/test_checkshot.py::test_valid_file_parses_header_and_rows` — `assert 'LF' == 'CRLF'`.

**Root cause.** The packaged fixture `tests/fixtures/checkshot_valid.txt` intentionally uses CRLF line endings (202 bytes, every line terminated `\r\n`, including the final line) — this is a deliberate parser regression fixture, not an accident, and it is the **only** CRLF-encoded fixture packaged anywhere in this project (confirmed by an explicit scan of every `checkshot_*.txt`, `dev_*.txt`, and `*.las` fixture: all others are LF-only). Increment 4.1.1's notebook wrote this fixture, like every other fixture, via a `%%writefile tests/fixtures/checkshot_valid.txt` cell whose cell source embeds the file's own bytes verbatim (including the literal `\r\n` bytes) inside the notebook's JSON. In a real Google Colab kernel, that cell's `\r\n` bytes reconstruct on disk as `\n`-only — i.e., something in Colab's own runtime path from "cell source text" to "file written by `%%writefile`" canonicalizes embedded CR/LF control bytes. This is a platform-specific behavior of the real Colab runtime that this project's own tooling cannot reproduce, for two independently confirmed reasons:

1. This project's own notebook-build script (`dev_scratch_inc4_1/build_notebook_04.py`'s `writefile_cell`) reads and embeds the fixture's raw bytes into the cell's JSON `source` losslessly — confirmed by direct inspection: the packaged fixture's bytes and the notebook cell's stored source bytes were identical before this patch.
2. Python's own text-mode file write on Linux is *also* a no-op for embedded `\r` bytes: `open(path, "w").write(body)`'s universal-newline translation only touches the literal `\n` character (translating it to `os.linesep`, which **is** `\n` on Linux) — a string that already contains `\r\n` round-trips through Linux text-mode writing completely unchanged. This means even this project's own dynamic re-execution harness (`dev_scratch_inc4_1/verify_execution_order_04.py`, which simulates every `%%writefile` cell with Python's own `Path.write_text()`) could not have observed this defect either — it is not merely that the STATIC source-vs-packaged-file byte comparison missed it (Section 1.1 below explains why that check is structurally blind to this), but that no check running entirely in Linux/Python — static or dynamic — could reproduce a corruption that occurs specifically inside a real Colab kernel's own cell-source handling.

**Why the static `%%writefile` parity audit did not, and could not, detect this.** That audit (used in every prior increment, and retained here — Section 4) compares the notebook's own stored JSON source bytes against the packaged file's bytes. Those two byte strings **were identical** before this patch (point 1 above) — the corruption is not a discrepancy between the notebook file and the packaged file; it is introduced by Colab's kernel at cell-execution time, downstream of both. A check that only ever compares two files that are already sitting on disk, never observing what a live kernel does with the cell's source text, has no way to see this class of defect.

**The fix — a targeted architectural fix, not an empirical patch for one observed instance.** The `%%writefile tests/fixtures/checkshot_valid.txt` cell is **removed** and replaced with an ordinary Python code cell (`crlf_exact_fixture_cell` in `build_notebook_04.py`) that:

1. Encodes the fixture's raw bytes via `repr()` into a Python `bytes`-literal (`_checkshot_valid_bytes = b'VELOCITY SURVEY:...\r\nDepth\tTVDSS\t...'` etc.) embedded directly in the cell's Python source.
2. Writes it with `Path.write_bytes()` — binary mode, immune to text-mode newline translation on any platform.

This removes the entire failure-mode class, not just this one observed instance: `repr()` of a Python `bytes` object always renders a carriage return as the two-character ASCII escape sequence `\r` and a line feed as `\n` — **never as a raw 0x0D/0x0A control byte** — so the notebook's own stored cell-source text contains **no actual line-break byte at all** for this file, anywhere, for **any** upstream normalizer (Colab's included, and any other present or future one) to find and canonicalize. The real CRLF bytes exist only once the Python interpreter parses the escape sequences back into real bytes **at cell-execution time**, and are written with `write_bytes()` (binary mode: no newline translation is possible on any platform, by construction — this is not specific to Linux the way the previous, insufficient reasoning was). The cell also asserts, at execution time, that the file it just wrote round-trips byte-identically and that every line feed is preceded by a carriage return (pure CRLF, no bare LF), so a future silent regression would fail loudly inside the notebook itself, not just in this project's own external verification.

The packaged fixture `tests/fixtures/checkshot_valid.txt` itself is **unchanged** — still CRLF, still 202 bytes, still ending in a final CRLF. The parser is **unchanged** — it still requires and reports `line_ending_convention == "CRLF"` for this file, and the test asserting that is **unchanged and unweakened**. This is preserved, per instruction, as an intentional parser regression fixture, not converted to LF or otherwise accommodated.

**Scope confirmation.** A project-wide scan (every packaged `checkshot_*.txt`, `dev_*.txt`, and `*.las` fixture) confirms `checkshot_valid.txt` is the **only** CRLF-encoded fixture anywhere in this project. No other `%%writefile` cell is exposed to this defect, so no other cell needs this fix.

### 1.2 Defect 2 — the completion gate never checked whether the tests actually passed

**Observed (real Colab run):** despite `1 failed, 384 passed`, the notebook continued past the failing test and its completion-gate cell printed every one of its (then ten) conditions as `[PASS]`.

**Root cause.** The Increment 4.1.1 notebook's Step 9 cell was the single line `!pytest -v` — a bare, `!`-prefixed shell-escape line. In Jupyter/Colab, such a line executes the shell command and the notebook continues to the next cell regardless of that command's exit status; nothing about a bare `!`-prefixed line's non-zero exit stops execution or is captured into any Python variable. Separately, and independently, the completion gate's own `gate_checks` dictionary (in Increment 4.1.1) never referenced the test outcome at all — no key, value, or condition in that dictionary was in any way a function of whether `pytest` had passed or failed. The gate's `[PASS]` printing was therefore **structurally independent** of the actual test result: it was not that the gate checked the wrong thing and got it wrong, but that it never checked the test result in the first place. This was a genuine false-positive completion gate, not a narrower reporting inaccuracy.

**The fix.** Step 9 is replaced with:

```python
import subprocess
import sys

FULL_TEST_SUITE_PASSED = False  # default to NOT passed; only set True below on returncode == 0

result = subprocess.run([sys.executable, "-m", "pytest", "-v"])
if result.returncode == 0:
    FULL_TEST_SUITE_PASSED = True
    print(f"\npytest returncode = {result.returncode}: full test suite passed with zero failures.")
else:
    raise RuntimeError(
        f"pytest returncode = {result.returncode} (non-zero): the combined test suite did NOT "
        f"pass with zero failures. FULL_TEST_SUITE_PASSED remains False. Stopping here rather "
        f"than continuing past a failing test suite - see the pytest output above for the "
        f"specific failure(s)."
    )
```

This uses the active interpreter (`sys.executable`) via `subprocess.run`, checks the actual `returncode`, and — as a first line of defense — `raise`s `RuntimeError` itself on any non-zero return code, stopping the notebook before the completion gate cell is ever reached.

As a **second, independent** line of defense (defense in depth, in case Step 9 were ever skipped, reordered, or its variable otherwise left unset), the completion gate's `gate_checks` dictionary gets a new, first-checked entry:

```python
"(4.1.2) Complete combined test suite passed with zero failures": (
    globals().get("FULL_TEST_SUITE_PASSED", False) is True
),
```

This is read via `globals().get(..., False)`, not a bare `FULL_TEST_SUITE_PASSED` name reference, so that if the variable were ever left completely undefined, this check fails **cleanly** as `False` (printed as an ordinary `[FAIL]` line) rather than crashing the whole gate cell with an uncaught `NameError` — either way, "the variable was never set" cannot result in this gate printing overall completion, since `all(gate_checks.values())` requires every entry, including this one, to be `True`, and `is True` matches only the literal boolean `True`. The gate's overall pass/fail decision, and its final print statements, are otherwise unchanged in structure (`all(gate_checks.values())` decides completion; a failure raises `RuntimeError` naming the gate).

No test count is hardcoded anywhere in this fix as a substitute for checking the actual result — completion is decided by the subprocess's real `returncode`, reported and re-checked, not assumed.

---

## 2. What was NOT touched

- No change to `pyproject.toml`, any `p2mem/*.py` module, any `config/*.yml` contract file, any `tests/*.py` test file, or any `tests/fixtures/*` fixture file — including `tests/fixtures/checkshot_valid.txt` itself, which remains byte-identical, CRLF, 202 bytes (confirmed in Section 6).
- No change to any numerical method, contract, raw-data policy, or scientific output. `p2mem.__version__` remains `0.4.1.1` (no version bump — no implementation file changed).
- No change to notebooks `02_LAS_Ingestion_and_Curve_Contracts.ipynb` or `03_Deviation_Survey_and_Depth_Framework.ipynb`.
- No change to any of the nine Increment 4.1.1 CSV/JSON outputs or five QC figures under `outputs/04_checkshot_time_depth/` — confirmed byte-identical (Section 5).
- No raw LAS, deviation, or checkshot input file is packaged in this or any prior deliverable ZIP; none was read to produce this patch (Sections 1 and 4's verification use only packaged fixtures and the notebook's own file-generation cells).
- No new scope: formation-top correction, petrophysics, pore-pressure prediction, mechanical/elastic properties, rock strength, stress modelling, and wellbore-stability screening remain entirely unimplemented and out of scope. **Increment 5 has NOT been started.**

## 3. Files changed (exhaustive, exactly as diffed against a clean-room extraction of the delivered Increment 4.1.1 ZIP)

**Notebook (1 file):**
- `04_Checkshot_QC_and_Time_Depth_Framework.ipynb` — rebuilt from `dev_scratch_inc4_1/build_notebook_04.py` (not packaged). 70 total cells (was 69): +1 new markdown cell (Step 7a) explaining the CRLF-cell rationale; the `checkshot_valid.txt` code cell itself is still exactly one cell (41 code cells total, unchanged), now generated by `crlf_exact_fixture_cell()` instead of `writefile_cell()`. Step 9's code cell replaced (bare `!pytest -v` → `subprocess.run` with explicit `returncode` check). Completion-gate markdown and code cell updated (new condition `(4.1.2)`, checked first). Top preamble, Step 6, and Limitations markdown updated with Increment 4.1.2 notices. `nbformat.validate()` passes; all 70 cells carry unique string `id` fields (Section 6).

**Documentation (1 file):**
- `INCREMENT_04_1_1_MANIFEST.md` — corrected in place: a new correction notice added immediately after the introductory paragraph (following the established Increment 3.1/4.1/4.1.1 precedent of amending a prior manifest's specific error in place, without rewriting or concealing the rest of the document), stating explicitly that a real Colab run exposed both the line-ending-reconstruction defect and the false-positive completion gate, and that Section 6's own clean-room-simulation language, while an accurate description of what that Linux-based simulation observed, was an insufficient proxy for real Colab runtime behavior for this fixture. Every other finding in that document is unaffected and unchanged.

**Packaging (1 file):**
- `INCREMENT_04_1_2_SHA256SUMS.txt` (NEW) — see Section 7.

**Manifest (1 file):**
- `INCREMENT_04_1_2_MANIFEST.md` (NEW, this file).

Total: **4 changed or new packaged files**. No `p2mem/*.py`, `pyproject.toml`, `config/*.yml`, `tests/*.py`, `tests/fixtures/*`, `README.md`, or output file differs from the Increment 4.1.1 baseline — confirmed exhaustively by `diff -rq` (Section 6).

## 4. Dev-only (not packaged) changes supporting this patch

- `dev_scratch_inc4_1/build_notebook_04.py` — module docstring updated (also correcting a pre-existing, unrelated stale reference to a nonexistent `verify_notebook_parity_04.py` file, replaced with references to the two scripts that actually exist: `verify_execution_order_04.py` and the new `verify_crlf_fixture_and_gate_04.py`); `writefile_cell`'s comment clarified on the scope of its own byte-correctness guarantee; new function `crlf_exact_fixture_cell()` added (Section 1.1); the fixture-writing loop, Step 9's cell, and the completion-gate cell's construction updated to match Section 1's fixes.
- `dev_scratch_inc4_1/verify_crlf_fixture_and_gate_04.py` (NEW) — the dedicated execution-semantics verification script required by this patch's scope (Section 5). Not packaged; requires no real checkshot/deviation/LAS data.
- `dev_scratch_inc4_1/verify_execution_order_04.py` — unchanged. Its pre-existing `!pytest` special-case branch is now unreachable for this notebook specifically (Step 9 no longer starts with `!pytest`), so this notebook's Step 9 cell now falls through to that harness's generic `exec()` branch — which is a **more faithful** simulation than before, since it now runs the real `subprocess.run(...)` call exactly as the notebook contains it, rather than a separate shim. This script is shared dev infrastructure and was not modified, since doing so is not required by this patch's scope.

## 5. Execution-semantics verification (the new dedicated script) — actual results

Static source-text comparison (Section 6's `%%writefile` parity audit) is retained but, per Section 1.1, is **structurally incapable** of detecting the class of defect that motivated this patch. Per this patch's explicit requirement, a new, dedicated, dev-only script — `dev_scratch_inc4_1/verify_crlf_fixture_and_gate_04.py` — was written to test the notebook's **actual execution behavior** instead, and was run against this deliverable's rebuilt notebook. It requires no real checkshot/deviation/LAS data (it only reproduces the notebook's file-generation-and-test-running cells, code-cells 6–29, stopping strictly before the real-data-dependent "Real Checkshot Integration" section). Actual output, this run:

```
[check] 21 %%writefile cells found (checkshot_valid.txt correctly excluded from this count) -> OK
[check] CRLF cell at code-cell index 14
[check] pytest-subprocess cell at code-cell index 29
[check] completion-gate cell at code-cell index 40
[check] file-generation cells form one contiguous block: code-cells 6-27 -> OK
[gen] ... 21 %%writefile cells + the CRLF cell executed into a fresh temp project root ...
[check] all 22 file-generation cells executed without error -> OK
[check] generated fixture (202 bytes) is byte-identical to packaged tests/fixtures/checkshot_valid.txt -> OK
[check] p2mem.io.checkshot.parse_checkshot_header reports line_ending_convention == 'CRLF' -> OK
============================= 124 passed in 0.40s ==============================
[check] pytest returncode = 0 -> OK (zero failures, actual subprocess result, not assumed)
[extract] gate expression (verbatim from the notebook's own gate cell):
    globals().get("FULL_TEST_SUITE_PASSED", False) is True
[check] FULL_TEST_SUITE_PASSED never set (Step 9 skipped entirely) -> gate entry = False (expected False) -> OK
[check] FULL_TEST_SUITE_PASSED = False (simulated non-zero pytest returncode) -> gate entry = False (expected False) -> OK
[check] FULL_TEST_SUITE_PASSED = 1 (truthy but not the literal bool True) -> gate entry = False (expected False) -> OK
[check] FULL_TEST_SUITE_PASSED = True (simulated returncode == 0) -> gate entry = True (expected True) -> OK
[check] a False (4.1.2) entry forces all(gate_checks.values()) == False even when every other entry is True -> OK
[check] a True (4.1.2) entry does not by itself force all(gate_checks.values()) == True (every other entry still matters) -> OK

EXECUTION-SEMANTICS VERIFICATION: PASSED
```

This directly satisfies the required 7-item check: (1) the notebook's file-generation sequence was reproduced from a fresh, empty temporary project root by extracting and executing the real cell source from the notebook JSON itself; (2) the Step 7a binary-writing cell for `checkshot_valid.txt` was executed exactly as stored in the notebook; (3)–(4) the resulting file is byte-identical to the packaged fixture and its detected line-ending convention is CRLF (via the real `p2mem.io.checkshot.parse_checkshot_header`, not a hand-rolled recheck); (5)–(6) the complete test suite generated by this reproduction (`tests/test_checkshot.py`, `tests/test_time_depth.py`, `tests/test_checkshot_inventory.py` — the three Increment-4-family test files this notebook itself writes; 124 tests) was run via `python -m pytest` with `cwd` set to the fresh temp root, relying on `python -m`'s documented `sys.path[0]` insertion to import the freshly-written temp-root `p2mem` package rather than the actually pip-installed editable one, and reported `returncode == 0` with zero failures — the actual subprocess result, not assumed; (7) the completion gate's own `(4.1.2)` condition — extracted verbatim from the notebook's gate cell, not re-typed — was confirmed to evaluate `False` when `FULL_TEST_SUITE_PASSED` is unset, `False`, or merely truthy-but-not-`True`, and `True` only for the literal boolean `True`, with a concrete demonstration that a single `False` entry forces `all(gate_checks.values())` to `False` regardless of every other entry.

**Note on scope of item 5's "complete test suite."** This script's reproduction covers exactly what the notebook's own file-generation-and-Step-9 cells produce and test (the three Increment-4-family test files; 124 tests) — it does not reconstruct the full locked Increment 1–3.1.1 foundation (which this notebook does not `%%writefile` either; it only checks that foundation's presence, per Step 2). The full, actual combined suite (all locked-foundation tests plus these) is separately confirmed at **385 passed, zero failures** against the real, complete package tree in Section 6 below (clean-room ZIP extraction) and Section 5 of `verify_execution_order_04.py`'s own real-data run (Section 6).

## 6. Full clean-room verification (actual results)

Performed against a fresh extraction of the final `Poseidon_1D_MEM_Increment_04_v4.1.2.zip` into a clean directory, independent of the build tree:

1. **Checksum verification:** `sha256sum -c INCREMENT_04_1_2_SHA256SUMS.txt` — all files OK.
2. **Offline install:** `pip install -e . --no-build-isolation --no-index --no-deps` — succeeds; `python3 -c "import p2mem; print(p2mem.__version__)"` → `0.4.1.1` (unchanged).
3. **Full test suite:** `python3 -m pytest -q` → **385 passed**, zero failures (identical count to Increment 4.1.1 — no test added, removed, or changed, since no `tests/*.py` file changed).
4. **Notebook structure:** `nbformat.validate()` passes; 70 total cells, 41 code cells, all carrying unique string `id` fields.
5. **`%%writefile` byte-parity audit (retained, static):** 21 `%%writefile` cells (22 from Increment 4.1.1 minus `tests/fixtures/checkshot_valid.txt`, which Increment 4.1.2 excludes from this mechanism per Section 1.1) — **21/21 match, 0 mismatches** against the corresponding packaged files, exact byte comparison, no universal-newline normalization. `checkshot_valid.txt` is confirmed excluded from both the `%%writefile` cell set and this count; it is separately verified by the dedicated execution-semantics script (Section 5), not by static text comparison, per Section 1.1's explanation of why static comparison cannot detect this class of defect.
6. **Execution-semantics verification (dynamic, the new required check):** `dev_scratch_inc4_1/verify_crlf_fixture_and_gate_04.py` re-run against the clean-room-extracted notebook — identical output to Section 5, `EXECUTION-SEMANTICS VERIFICATION: PASSED`.
7. **Real-data execution smoke test:** `dev_scratch_inc4_1/verify_execution_order_04.py` re-run (using the private real checkshot/deviation/LAS data held only in this dev tree's `dev_scratch_inc4_1/`, never packaged) — all 41 code cells executed successfully from a fresh `/content`-style working directory; the completion gate printed all **eleven** `[PASS]` entries (the ten from Increment 4/4.1/4.1.1, plus the new `(4.1.2)` entry, printed first); every real-data statistic (raw checkshot row counts 220/212/232; residuals 0.089305 m / 0.791865 m / 0.389789 m; sonic drift +16.663754 ms / +4.447901 %; axis-tie counts) reproduced identically to the Increment 4.1.1-verified values — nothing scientific changed.
8. **Output byte-identity:** `diff -rq` between this deliverable's `outputs/04_checkshot_time_depth/` and the Increment 4.1.1 baseline's — **zero differences**. All nine CSV/JSON outputs and all five QC figures are byte-identical.
9. **No unintended file changes:** `diff -rq` between a clean-room extraction of the delivered Increment 4.1.1 ZIP and this deliverable's build tree (excluding build artifacts: `.pytest_cache`, `__pycache__`) reports differences in exactly one file — the notebook — plus the 3 new/amended documentation/packaging files listed in Section 3. No `p2mem/*.py`, `pyproject.toml`, `config/*.yml`, `tests/*.py`, `tests/fixtures/*`, or output file differs.
10. **Absolute-path leakage:** `grep -rn "/home/claude\|/root/\|/tmp/"` over every packaged `.py`/`.md`/`.csv`/`.json`/`.ipynb`/`.yml`/`.toml`/`.txt` file in the clean-room extraction returned matches only inside pre-existing, self-referential test-assertion strings (e.g. `tests/test_checkshot_inventory.py`'s `/home/user/secret_build_dir/...` fixtures, unchanged from Increment 4) and this manifest's/the notebook's own documentation describing this check — no actual leaked build path was found.
11. **Deterministic regeneration:** the notebook-reconstruction logic in Section 5's script was re-run from two independent temporary roots; both produced byte-identical generated files.
12. **No private data packaged:** confirmed the final ZIP contains no raw LAS, deviation, or checkshot input file, and no `dev_scratch_inc4_1/` content — `unzip -l` listing inspected directly.

## 7. Checksum ledger and packaging

`INCREMENT_04_1_2_MANIFEST.md` (this file) was finalized FIRST, before any checksum was computed. `INCREMENT_04_1_2_SHA256SUMS.txt` then records the SHA-256 of every OTHER regular file packaged in `Poseidon_1D_MEM_Increment_04_v4.1.2.zip`, computed from the final packaged bytes — **including this manifest's own checksum** and the amended `INCREMENT_04_1_1_MANIFEST.md`'s checksum — following the same self-exclusion-only ledger policy established in Increment 4.1/4.1.1: the ledger excludes ONLY itself.

The final ZIP archive's own SHA-256 (the hash of the `.zip` file itself, not of any file inside it) is reported separately, in the completion record and the delivery message, since it is only known once the ZIP is assembled around this manifest and the checksum ledger. No private raw checkshot, deviation, or LAS input file is packaged in this or any prior deliverable ZIP.

## 8. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational 1D Mechanical Earth Model**. This patch corrects a packaging/notebook-execution defect (Colab-specific line-ending reconstruction) and a software-QA defect (a non-blocking, false-positive completion gate); it performs no new calibration, changes no numerical method, and raises no independent evidence toward a higher assurance tier.

## 9. Known limitations (Increment 4.1.2-specific)

- **This environment cannot execute inside a real Google Colab runtime.** The verification in Sections 5 and 6 is the strongest verification available in a Linux/Python environment (full notebook-JSON extraction and execution of the real cell source; byte-identity and line-ending-detection checks against the real parser; the full test suite run against notebook-generated files; direct evaluation of the extracted gate expression under simulated failure) — it is **not** a literal re-run inside Colab itself. This is a disclosed limitation, not assumed away: the fix's correctness argument (Section 1.1) is therefore an architectural one (removing an entire class of failure mode, by construction, rather than empirically re-testing the one observed Colab behavior), since the one thing that cannot be independently re-confirmed here is a live Colab execution.
- Item 7 of the required execution-semantics verification (the completion gate cannot pass on a simulated non-zero pytest return code) is necessarily a **direct evaluation of the gate's extracted expression under simulated globals**, not a full end-to-end notebook run that reaches a genuinely failing state — a real run of this notebook that reaches the completion gate has, by construction, already passed Step 9's own `RuntimeError`-raising check, so it cannot itself demonstrate a failing gate. This is disclosed rather than presented as an equivalent to an actual observed failure.
- All limitations disclosed in `INCREMENT_04_MANIFEST.md`, `INCREMENT_04_1_MANIFEST.md`, and `INCREMENT_04_1_1_MANIFEST.md` (Boreas 1 / Proteus 1ST2 depth-datum offset patterns, Proteus 1ST2 identity inference, the sonic-vs-checkshot raypath difference, the axis-tie median-representative screening-level choice, the numerical-validation corrections' scope, and every downstream-phase scope exclusion) remain fully in force and are unaffected by this patch.

## 10. Stop condition

Increment 4.1.2 is complete as of this manifest. Per the governing instruction for this patch: **Increment 5 has NOT been started**, and no formation-top correction, lithology interpretation, density modelling, pore-pressure prediction, elastic properties, rock strength, stress modelling, or wellbore-stability analysis has been implemented. This corrective patch is the entirety of the scope delivered here.
