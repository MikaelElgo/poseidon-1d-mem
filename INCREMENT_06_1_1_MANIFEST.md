# Increment 6.1.1 Manifest — Corrective Patch to Increment 6.1

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.1 → **0.6.2**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.zip`, SHA-256 `817a3260fa10f63fe6fda2e3d242cb37f8ed38d088032069448c145037bfb0ac` — **independently recomputed before any change; exact match.** The build tree was extracted fresh from that verified archive; no drifted working tree was reused.

**Scope:** five audit findings, corrected. This is **not** documentation-only: findings 1, 3 and 4 required implementation changes to the lithology validator, the interval reporting schema, and the notebook completion gate.

**Increment 7 has NOT been started.** No pore pressure, NCT fitting, elastic-property calculation, rock strength, stress, or wellbore-stability work exists anywhere in this patch. No configured bridging tolerance, endpoint rule, proxy threshold, physical bound, or qualifying-block policy was changed.

---

## 1. Finding 1 — named-lithology validator bypass (CONFIRMED, CORRECTED)

### 1.1 Reproduction

Both cases named in the audit were reproduced against the unmodified 6.1 baseline and returned **zero violations**:

| Case | Context | Text | 6.1 result | 6.1.1 result |
|---|---|---|---|---|
| 1 | `Poseidon_2.config_notes` (`SCOPE_INTERPRETIVE`) | *"This interval contains shale gas."* | **0 violations** | **VIOLATION** `['shale']` |
| 2 | `manifest.statement` (`SCOPE_EXPLANATORY`) | *"Poseidon 2 contains shale gas."* | **0 violations** | **VIOLATION** `['shale']` |

The cause was `ALLOWED_METHOD_TERM_PHRASES`, the list of phrases per-well prose may use to name a *method category*. It contained `"shale gas"`, which is not a method-category phrase at all — it is a direct geological/hydrocarbon assertion. Any sentence containing it therefore had the word `shale` stripped before the prohibited-vocabulary scan, and the assertion passed.

### 1.2 Allowlist minimisation — determined empirically, not by judgement alone

A probe ran `find_prohibited_lithology_terms` over the **real** validation scope (every persisted label, generated status, per-well note, mask name/note/purpose, and manifest statement in the packaged project) with and without each allowlist entry, to establish which entries are actually load-bearing:

| Phrase | Rescues real project content? | Disposition |
|---|---|---|
| `shale proxy` | **Yes** — it is the name of the only proxy this project computes | **RETAINED** |
| `shale volume` | No occurrence today, but it is the quantity the project explicitly **denies** computing ("this is not a calibrated shale volume") | **RETAINED** — required to state a project boundary |
| `shale index` | No | **REMOVED** — pure attack surface |
| `shale flag` | No | **REMOVED** — pure attack surface |
| `shale gas` | No | **REMOVED** — not a method name; the bypass itself |

```python
ALLOWED_METHOD_TERM_PHRASES = ("shale proxy", "shale volume")
```

Every surviving phrase ends in a method/quantity noun, and a regression test asserts that property so the list cannot silently readmit a rock or hydrocarbon assertion.

### 1.3 The allowance is now defeasible, not absolute

Removing `"shale gas"` alone would still leave `"This interval has a high shale volume."` passing — a magnitude attached to the well, which is an assertion about the rock, not a method name. Two mechanisms were added:

1. **Per-sentence geological-assertion cues.** The text is split into sentences; in any sentence carrying a cue (`contains`, `comprises`, `consists`, `composed`, `penetrated`, `encountered`, `hosts`, `bearing`, `rich`, `dominated`, `deposited`, `interbedded`, `facies`, …) the allowance is suppressed **entirely** and every rock name in it is reported.
2. **Adjacent quantity cues.** Within the three tokens immediately preceding an allowed phrase, a quantity cue (`has`, `high`, `elevated`, `significant`, `shows`, `indicates`, …) suppresses the allowance for that phrase only.

Evaluation is **per sentence** by design. A clean method sentence cannot license an assertion in the next one, and one assertion does not void the allowance across an entire long note.

`lithology` / `lithological` are deliberately **not** cues: they appear legitimately in this project's own language (`lithology-dependent mask`, "remains UNRESOLVED in lithology") and name no rock.

### 1.4 Discrimination battery — all nine cases correct

| Text (interpretive scope) | Verdict |
|---|---|
| "Excluded from every shale-proxy calculation." | pass |
| "This is a screening proxy, not a calibrated shale volume." | pass |
| "No shale volume is computed anywhere in this increment." | pass |
| "The shale proxy is dimensionless and uncalibrated." | pass |
| "This interval contains shale gas." | **violation** |
| "Poseidon 2 contains shale gas." (explanatory) | **violation** |
| "This interval has a high shale volume." | **violation** |
| "A shale-bearing facies dominates here." | **violation** |
| "The proxy is a shale proxy. This interval contains shale." | **violation** |

`SCOPE_LABEL` is unaffected: `SHALE_PROXY_HIGH`, `shale proxy` and `shale volume high` are all violations as labels, with zero latitude, exactly as before.

### 1.5 Gate consequence

Injecting **either** audited bypass case into real manifest-building content now produces, together:

- `named_lithology_assigned == true`
- `lithology_validation.n_violations > 0`
- completion gate **FAILS**

Regression tests cover the two exact audited cases, allowlist membership and minimality, the absence of any hydrocarbon phrase from every allowlist constant in the module, cue suppression, adjacency suppression, per-sentence evaluation, label strictness, preservation of legitimate method/quantity prose, and both gate-level injections. **The clean, real manifest still reports 138 fields checked, 0 violations, `named_lithology_assigned: false`.**

---

## 2. Finding 2 — stale Vp/Vs scientific description in active source (CONFIRMED, CORRECTED)

### 2.1 Reproduction

The **live** top-level docstring of `p2mem/method_eligibility.py` still read, at lines 34–35 of the 6.1 baseline:

> "… inside the Poisson domain (Vp/Vs > sqrt(2), i.e. Poisson ratio > 0) …"

This contradicted the implementation corrected in Increment 6.1 in three ways at once: it asserted a *physical-possibility* framing, it named a *Poisson-domain boundary*, and it stated a strictly **exclusive** bound where the code implements an **inclusive** one.

### 2.2 Correction

The active docstring now states:

- a **configured non-negative-Poisson-ratio applicability screen** — a conservative project policy about admissible inputs;
- an **inclusive** `Vp/Vs >= sqrt(2)` bound (at `r = sqrt(2)`, `nu = 0` exactly, and a non-negative-`nu` policy must accept it);
- explicitly, that this is **not** a physical-possibility test and **not** a boundary of the mathematical Poisson domain.

The function docstring of `compute_dynamic_elastic_eligibility` was brought into agreement, and the corresponding `%%writefile` body in the notebook was regenerated from the file on disk and re-verified byte-for-byte.

### 2.3 Sweep of all active content

A sweep of active source, README, notebook narrative and source cells, config, and current outputs for `"inside the Poisson domain"`, `"Vp/Vs > sqrt(2)"` and `"Poisson ratio > 0"` leaves exactly three residues, all legitimate:

| Location | Nature |
|---|---|
| `config/petrophysics_eligibility.yml` line 345 | a clearly marked **rename-history** comment recording the superseded key names |
| `tests/test_method_eligibility.py` | two **negative** assertions proving the old wording is gone |
| `README.md`, `p2mem/__init__.py` (6.1.1 changelog) | the old wording quoted **as** superseded history, in the sentence describing its correction |

Locked Increment 6 and 6.1 historical records retain their original wording, preserved as history and not rewritten.

### 2.4 Regression tests

Three new tests: the active **module** docstring must contain the corrected language (whitespace-normalised, so a line wrap cannot defeat it); the active **function** docstring must agree with the inclusive bound it implements; and no active `p2mem/**/*.py` file may reintroduce any of the three forbidden phrases.

---

## 3. Finding 3 — ambiguous / incorrect interruption counts (CONFIRMED, CORRECTED)

### 3.1 Reproduction

In the 6.1 interval register, **327** blocks carried bridged samples. Every one of them reported `n_interruptions == 1` — a boolean flag presented in the grammatical form of a count, which invites summation — while `n_interrupted_subruns` ranged from 1 to 5 under a name that does not say what is counted.

### 3.2 Correction — three separately named, independently meaningful quantities

| Field | Meaning |
|---|---|
| `n_bridged_samples` | total ineligible samples absorbed **inside** the gross block |
| `n_bridged_gaps` | number of **distinct** bridged runs of ineligible samples |
| `n_eligible_subruns` | number of maximal **strictly contiguous** eligible sub-runs |

They are not redundant: one gap may absorb several samples, so `n_bridged_samples` and `n_bridged_gaps` differ in general. The required identities hold and are **enforced at construction** — an interval record violating them raises `PetrophysicsInputError` rather than being exported:

- no gap → `0 / 0 / 1`;
- two separate bridged gaps in one configured block → `n_bridged_gaps = 2`, `n_eligible_subruns = 3`;
- wherever `n_eligible_subruns > 0` → `n_bridged_gaps = n_eligible_subruns − 1`.

### 3.3 Measured on the real data (regenerated register, 5,857 interval rows)

| `n_bridged_gaps` | blocks | `n_eligible_subruns` | blocks |
|---|---|---|---|
| 0 | 5,530 | 1 | 5,530 |
| 1 | 242 | 2 | 242 |
| 2 | 62 | 3 | 62 |
| 3 | 17 | 4 | 17 |
| 4 | 4 | 5 | 4 |
| 5 | 2 | 6 | 2 |

327 blocks are bridged (unchanged), absorbing **666** ineligible samples across **443** distinct gaps. The identity holds for every one of the 5,857 rows. The former `n_interruptions` value of 1 is now visibly wrong for the 85 blocks with two or more distinct gaps.

### 3.4 Exports

`n_interruptions` and `n_interrupted_subruns` **no longer appear in any active CSV or JSON export** — no aliases were retained. `thickness_sensitivity_summary.csv` distinguishes three separate questions about the same population: `n_bridged_samples_in_qualifying_blocks`, `n_bridged_gaps_in_qualifying_blocks`, and `n_interrupted_qualifying_blocks` (blocks with at least one gap). Each row's `population_statement` names all three.

### 3.5 Tests

Seven new tests, including the required synthetic case with **two separate bridged gaps inside one configured block**, a generalised identity check, a case where one gap absorbs several samples so gaps and samples differ, rejection of an inconsistent record at construction, and an assertion that the ambiguous aliases are absent from active exports.

**Configured bridging tolerances and the qualifying-block policy are unchanged.** All qualifying-thickness figures are byte-identical to 6.1 apart from the added and renamed count columns.

---

## 4. Finding 4 — notebook output-count error (CONFIRMED, CORRECTED)

The notebook creates and checks **eight** deterministic CSV/JSON outputs while both the gate Markdown and the printed gate label said "7 deterministic output files". Both now say **8**, and the gate no longer trusts the label:

```python
"8 deterministic output files declared and present": (
    len(_expected_outputs) == 8
    and all(os.path.exists(os.path.join(OUT_DIR, fn)) for fn in _expected_outputs)
),
```

The count and the existence of all eight are asserted explicitly, so the label can never drift from the list again. The regenerated notebook contains **zero** occurrences of "7 deterministic" and two of "8 deterministic". Four figures remain separate: **12 outputs/figures in total**.

The eight deterministic outputs are `gr_family_qc_summary.csv`, `gr_endpoint_scenarios.csv`, `gr_proxy_sensitivity_summary.csv`, `method_eligibility_summary.csv`, `eligibility_interval_register.csv`, `thickness_sensitivity_summary.csv`, `petrophysics_eligibility_issues.csv`, `petrophysics_eligibility_manifest.json`.

---

## 5. Finding 5 — incorrect Increment 6.1 delta arithmetic (CONFIRMED; SUPERSEDED, NOT REWRITTEN)

### 5.1 The superseded statement

`INCREMENT_06_1_COMPLETION_RECORD.md` §8 states:

> **Changed (12):** … plus regenerated `outputs/06_petrophysics_eligibility/` (fig01, fig04 and five tables).

**That statement is inaccurate and is hereby explicitly superseded.** It counted a regenerated output *directory* as a single line item covering seven distinct files. The locked Increment 6.1 record is **not** rewritten — it stands as issued, with this manifest recording the correction.

### 5.2 Measured delta — Increment 6 → Increment 6.1

Clean recursive comparison of a fresh extraction of `Poseidon_1D_MEM_Increment_06.zip` against a fresh extraction of `Poseidon_1D_MEM_Increment_06_v6.1.zip`, by SHA-256 per path:

**Changed — 18 files:**

1. `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`
2. `README.md`
3. `config/petrophysics_eligibility.yml`
4. `outputs/06_petrophysics_eligibility/eligibility_interval_register.csv`
5. `outputs/06_petrophysics_eligibility/figures/fig01_gr_family_raw_qc.png`
6. `outputs/06_petrophysics_eligibility/figures/fig04_sonic_nct_candidate_interval_sensitivity.png`
7. `outputs/06_petrophysics_eligibility/gr_family_qc_summary.csv`
8. `outputs/06_petrophysics_eligibility/gr_proxy_sensitivity_summary.csv`
9. `outputs/06_petrophysics_eligibility/method_eligibility_summary.csv`
10. `outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json`
11. `p2mem/__init__.py`
12. `p2mem/io/petrophysics_inventory.py`
13. `p2mem/method_eligibility.py`
14. `p2mem/petrophysics.py`
15. `p2mem/wellframe_models.py`
16. `pyproject.toml`
17. `tests/test_method_eligibility.py`
18. `tests/test_petrophysics.py`

**Added — 3 files:**

1. `INCREMENT_06_1_MANIFEST.md`
2. `INCREMENT_06_1_SHA256SUMS.txt`
3. `outputs/06_petrophysics_eligibility/thickness_sensitivity_summary.csv`

**Removed — 0 files. Total path differences — 21.**

The superseded "Changed (12)" figure therefore understated the changed-file count by six, all of them regenerated outputs hidden behind a directory-level line item.

### 5.3 Measured delta — Increment 6.1 → Increment 6.1.1

**Changed — 11 files:**

1. `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`
2. `README.md`
3. `outputs/06_petrophysics_eligibility/eligibility_interval_register.csv`
4. `outputs/06_petrophysics_eligibility/thickness_sensitivity_summary.csv`
5. `p2mem/__init__.py`
6. `p2mem/io/petrophysics_inventory.py`
7. `p2mem/method_eligibility.py`
8. `p2mem/wellframe_models.py`
9. `pyproject.toml`
10. `tests/test_method_eligibility.py`
11. `tests/test_petrophysics.py`

**Added — 2 files:**

1. `INCREMENT_06_1_1_MANIFEST.md`
2. `INCREMENT_06_1_1_SHA256SUMS.txt`

**Removed — 0 files. Total path differences — 13.**

No output directory or wildcard is counted as one file anywhere above. Note that six output files changed in 6.1 but only two change here: the 6.1.1 corrections alter the interval reporting **schema**, not the figures or the summary statistics, so `fig01`, `fig04`, `gr_family_qc_summary.csv`, `gr_endpoint_scenarios.csv`, `gr_proxy_sensitivity_summary.csv`, `method_eligibility_summary.csv`, `petrophysics_eligibility_issues.csv` and `petrophysics_eligibility_manifest.json` are byte-identical to 6.1.

**Dev-only, never packaged** (reported separately, never counted in the ZIP delta): `dev_scratch_inc6/build_notebook_06.py` (findings 4 and the version bump), and the unchanged `run_integration_06.py`, `verify_execution_order_06.py`, `probe_vpvs_domain.py`, `probe_*.py`.

---

## 6. Test suite — actual results

| | Count |
|---|---|
| Increment 6.1 baseline, re-verified from the clean-room extraction before any change | **670 passed** |
| After Increment 6.1.1 | **703 passed** (0 failed, 0 errors, 0 skipped) |
| New tests added | **33** — `test_petrophysics.py` +20 (91 → 111), `test_method_eligibility.py` +13 (61 → 74); `test_wellframe.py` unchanged at 36 |
| Locked Increment 1–5.1.2 tests, run in isolation | **482 passed**, across **11** locked test files, all **byte-identical** to the 5.1.2 package |
| Notebook's own `pytest -v` during fresh execution | **703 passed** |

The 670 baseline cases all remain passing; the 33 new cases are additional, not substitutions.

Only **three** pre-existing files differ from the locked Increment 5.1.2 baseline — `pyproject.toml`, `p2mem/__init__.py`, `README.md` — the exact three permitted since Increment 6.

---

## 7. Non-regression — every required invariant, re-measured

| Invariant | Result |
|---|---|
| 4 LAS files and 4 deviation surveys load | 8/8, zero failures |
| 4 well frames assemble, row counts and order preserved | 4/4 |
| Extrapolated samples | **0** |
| Boreas 1 QC-only: endpoints / proxies / lithology-dependent masks | **0 / 0 / 0**, `BOREAS_ECGR_SCALE_UNRESOLVED` |
| Vp/Vs decomposition — Boreas 1 (non-positive K / positive-K, negative ν) | **0 / 1** |
| Poseidon 2 | **0 / 22** |
| Poseidon North 1 | **4 / 3** |
| Proteus 1ST2 | **0 / 3** |
| Poseidon North 1 use-status | `screening_proxy_allowed_depth_tied` |
| Poseidon 2 configured **gross** thickness sensitivity | 144.42 – 1,159.22 m (factor **8.03**) |
| Poseidon 2 **strict-no-gap** | 140.00 – 1,110.24 m (factor **7.93**) |
| Named lithology assigned anywhere | **NO** — derived, 138 fields checked, 0 violations |
| Increment 7 | **not started** |

---

## 8. Clean-room verification (all 14 required steps, against the final ZIP)

1. Increment 6.1 baseline SHA-256 independently recomputed **before any change**: exact match to `817a3260…0ac`.
2. Extraction safety — every ZIP entry scanned for absolute paths, `..` traversal and symlinks: **none found**.
3. Offline editable installation from the clean-room extraction: succeeded, `p2mem.__version__ == "0.6.2"`.
4. Complete `pytest` run: **703 collected, 703 passed**, 0 failed, 0 errors, 0 skipped.
5. All 670 original cases still pass; 33 new cases added on top.
6. Locked-file audit: only the three permitted files differ from 5.1.2; 11 locked test files byte-identical; locked suite **482 passed** in isolation.
7. Notebook structure: **73 cells**, all IDs unique, **zero** saved outputs and zero execution counts.
8. `%%writefile` parity: **14/14 byte-identical** to the files on disk.
9. Fresh execution-order smoke test from a `/content`-style sandbox: **38/38 code cells** executed, internal `pytest` **703 passed**, **17/17** gate checks `[PASS]`.
10. Four-well real-data integration: 8/8 files loaded, 4/4 frames assembled, zero extrapolated.
11. Deterministic output reproduction from two independent roots (notebook sandbox vs. build tree): **all 12 outputs/figures byte-identical**.
12. Checksum ledger verified against the final ZIP: every packaged file present and matching.
13. Absolute-path scan of all outputs: **zero matches**. No real LAS, deviation, checkshot, formation-top or Vp/Vs file is packaged; the packaged `.las` files are synthetic `tests/fixtures/` files, unchanged from the baseline; no `dev_scratch_*` directory is packaged.
14. Final ZIP SHA-256: recorded in `INCREMENT_06_1_1_COMPLETION_RECORD.md`.

---

## 9. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** This patch corrects reporting fidelity and validator integrity. It adds no calibration evidence, computes no new physical quantity, and raises no assurance level. Eligibility remains an input-admissibility statement, not a validity statement; the screening proxy remains uncalibrated and endpoint-sensitive; lithology remains **unresolved** in every well.

## 10. Stop condition

Increment 6.1.1 is complete as of this manifest. Per the governing instruction, work stops here to await independent audit. **Increment 7 has not been started.**
