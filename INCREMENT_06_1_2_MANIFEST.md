# Increment 6.1.2 Manifest — Corrective Patch to Increment 6.1.1

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.2 → **0.6.3**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.1.zip`, SHA-256 `03aa9a197a55a0772df22995f868e71b6a8527408051f34a54cbfff2c156e44b` — **independently recomputed before any change; exact match.** The uploaded archive's browser-added `(1)` suffix is naming only; the verified bytes are the baseline, and every deliverable here uses clean canonical filenames. The build tree was extracted fresh from that verified archive.

**Baseline suite re-run before any change: 703 passed.**

**Scope:** two residual audit findings, both requiring implementation changes. No scientific threshold, tolerance, endpoint scenario, contiguity policy, GR disposition, depth-mapping rule, or real-data interpretation was altered. No runtime dependency was added — **NumPy and PyYAML remain the only two.**

**Increment 7 has NOT been started.** No pore pressure, NCT fitting, elastic-property calculation, rock strength, stress, or wellbore-stability work exists anywhere in this patch.

---

## 1. Finding 1 — the named-lithology validator was bidirectionally incorrect (CONFIRMED, CORRECTED)

### 1.1 Reproduction against the unmodified 6.1.1 baseline

All eight audited cases were reproduced exactly as stated, before any code was changed.

**False negatives — prohibited project-specific assertions that passed with ZERO violations:**

| Context | Text | Scope | 6.1.1 | 6.1.2 |
|---|---|---|---|---|
| `audit.interpretive` | *"Poseidon 2's shale volume is high."* | interpretive | **PASSED** | **VIOLATION** |
| `audit.explanatory` | *"Poseidon 2's shale volume is high."* | explanatory | **PASSED** | **VIOLATION** |
| `audit.interpretive` | *"Poseidon 2's shale volume is 70 percent."* | interpretive | **PASSED** | **VIOLATION** |
| `audit.explanatory` | *"Poseidon 2's shale volume is 70 percent."* | explanatory | **PASSED** | **VIOLATION** |
| `audit.interpretive` | *"The interval's shale volume is high."* | interpretive | **PASSED** | **VIOLATION** |
| `audit.interpretive` | *"The interval's shale volume exceeds 60 percent."* | interpretive | **PASSED** | **VIOLATION** |

**False positives — legitimate method/boundary statements reported as lithological assertions:**

| Context | Text | Scope | 6.1.1 | 6.1.2 |
|---|---|---|---|---|
| `audit.method` | *"This method contains a shale proxy calculation."* | interpretive | **VIOLATION** | **PASSES** |
| `audit.boundary` | *"The analysis shows no shale volume was computed."* | interpretive | **VIOLATION** | **PASSES** |

**Retained from 6.1.1 — must continue to fail, and do:**

| Context | Text | Scope | 6.1.2 |
|---|---|---|---|
| `Poseidon_2.config_notes` | *"This interval contains shale gas."* | interpretive | **VIOLATION** |
| `manifest.statement` | *"Poseidon 2 contains shale gas."* | explanatory | **VIOLATION** |

### 1.2 Root cause

Both directions of error share one cause: Increment 6.1.1 treated the method-phrase allowance as a property of the **sentence**, decided by a sentence-wide assertion-cue list plus a fixed look-behind window of three tokens.

- The look-behind window inspects only what precedes the phrase, so `is high`, `is 70 percent` and `exceeds 60 percent` — where the entire assertion lives — were never read.
- The normalizer replaced every non-alphanumeric character with a space, **destroying the possessive**. `Poseidon 2's shale volume` became `poseidon 2 s shale volume`, erasing the one construction that most directly attaches a rock property to a body of rock.
- Conversely, a sentence-wide cue fires on the presence of `contains` or `shows` without ever asking **what is predicated of what**. The subject of *"This method contains …"* is a calculation, and *"shows no … was computed"* is a denial; neither asserts anything about rock.

The claim in the Increment 6.1.1 record that the allowlist "can no longer hide a geological assertion" was therefore not supported, and is superseded by this manifest.

### 1.3 Correction — the allowance is decided per occurrence, from local grammar

The exemption is no longer unconditional phrase removal, is no longer decided by sentence-wide cue detection, and no longer depends on a fixed look-behind window that ignores right-hand context. Each **occurrence** of an allowed phrase is classified from its own local grammar, and any one of four conditions withdraws its exemption:

| | Condition | Example that asserts | Example that does not |
|---|---|---|---|
| (a) | **Possessor** — the phrase is possessed by a geological entity | *"the interval's shale volume"*, *"Poseidon 2's shale volume"* | *"the project's shale proxy"*, *"the method's shale proxy calculation"* |
| (b) | **Modifier** — a magnitude sits immediately beside it, un-negated | *"a **high** shale volume"*, *"**significant** shale volume"* | *"**not** a calibrated shale volume"*, *"**no** shale volume"* |
| (c) | **Predicate** — an amount or dominance is asserted of it to the right | *"is high"*, *"is 70 percent"*, *"exceeds 60 percent"*, *"dominates the interval"*, *"of 70 percent"* | *"is dimensionless"*, *"was computed"*, *"is documented in the method register"* |
| (d) | **Composition** — a containment verb in the sentence takes a resolved **geological subject** | *"The unit comprises …"*, *"The well penetrated …"*, *"The section contains …"* | *"This method contains …"*, *"The module contains …"*, *"The export contains …"* |

Supporting mechanics:

- **Apostrophes are parsed, not erased.** A dedicated tokenizer returns a possessive flag per token and handles straight (`'`), typographic (`’`), modifier-letter (`ʼ`) and plural (`wells'`) forms.
- **A bare copula is deliberately insufficient.** `is` counts only when followed by a magnitude within three tokens, because *"the shale proxy **is** dimensionless"* states a property of the **method**. This single distinction is what keeps requirement 5's permitted sentences permitted while catching `is high`.
- **Subject heads are resolved, not searched for.** Walking left from a composition verb past determiners, conjunctions and bare numerals yields the head noun; only then is it tested against the geological-entity vocabulary. Searching the sentence for a geological word would have re-created the false-positive class (`lithology-dependent mask contains …` has head `mask`).
- **Sentence boundaries include line breaks**, so a multiline note cannot place an assertion and a clean method statement in the same unit of analysis.
- **Fail closed.** When a sentence predicates composition on a geological subject, no occurrence in it is exempt, even if that occurrence's own local context looks innocent.
- **`SCOPE_LABEL` is untouched and absolute.** A label is a verdict: `shale proxy`, `SHALE_PROXY_HIGH`, `shale volume high` and `shale-proxy` are all violations as labels.

No cue word was broadened to achieve this. The sentence-wide `GEOLOGICAL_ASSERTION_CUES` and the look-behind `ADJACENT_QUANTITY_CUES` were **removed** and replaced by structural vocabularies used positionally: `GEOLOGICAL_ENTITY_TOKENS`, `COMPOSITION_PREDICATES` (subject-gated), `MAGNITUDE_PREDICATES`, `MAGNITUDE_WORDS`, `COPULAR_VERBS`, `ATTRIBUTIVE_ROCK_TOKENS`, `NEGATION_TOKENS`. Reporting verbs (`shows`, `indicates`, `reports`) are deliberately absent from every one of them: they describe what an analysis says, not what a rock is.

### 1.4 Regression matrix

`VALIDATOR_MATRIX` in `tests/test_petrophysics.py` is table-driven and covers **59 rows**: all required PASS and FAIL sentences, both interpretive and explanatory scopes, upper/lower/mixed case, typographic and plural apostrophes, hyphenated and non-hyphenated `shale proxy`, commas, semicolons, parentheses, multiline text, clean-method-then-assertion and assertion-then-clean-method ordering, labels that must always fail, generic explanatory examples without project-well assignment, and project-well-specific explanatory assertions that must fail. A guard test asserts the matrix itself covers both directions (≥20 rows each) and all three scopes, so it cannot be quietly reduced to a one-sided list.

Two further tests pin the *structure* of the correction rather than its outputs: one shows the same verb producing opposite outcomes under different subjects (which a cue list cannot do), and one shows two sentences with identical left context differing on their right context (which a look-behind window cannot do).

### 1.5 Derived-gate path

Every injected prohibited statement is driven through the real manifest builder, not a helper. For each of six injections — including all four possessive/predicate forms — the run produces, together:

```
named_lithology_assigned == True
lithology_validation.n_violations > 0
completion gate == FAIL
```

For three legitimate method/boundary notes, and for the unchanged real packaged content:

```
named_lithology_assigned == False
lithology_validation.n_violations == 0
completion gate == PASS
```

The real manifest still reports **138 fields checked, 0 violations**.

---

## 2. Finding 2 — interval construction invariants were only partially enforced (CONFIRMED, CORRECTED)

### 2.1 Reproduction

Increment 6.1.1 stated the interruption-count identities were "enforced at construction". The constructor checked only `n_bridged_gaps == n_eligible_subruns - 1`, and skipped even that whenever either value was `None` or `n_eligible_subruns` was 0. The three records named in the audit were all constructible, and so were several more:

| Record | 6.1.1 | 6.1.2 |
|---|---|---|
| `samples=5, gaps=0, subruns=1` | **ACCEPTED** | `PetrophysicsInputError` |
| `samples=0, gaps=2, subruns=0` | **ACCEPTED** | `PetrophysicsInputError` |
| `samples=-1, gaps=-1, subruns=0` | **ACCEPTED** | `PetrophysicsInputError` |
| all three missing | **ACCEPTED** | `PetrophysicsInputError` |
| `samples=True, gaps=False, subruns=True` | **ACCEPTED** | `PetrophysicsInputError` |
| `samples=1, gaps=2, subruns=3` | **ACCEPTED** | `PetrophysicsInputError` |
| `n_interruptions=1` passed alongside | **silently ignored** | `PetrophysicsInputError` |
| numeric strings | `TypeError` (untyped) | `PetrophysicsInputError` |

### 2.2 Correction

All three counts are validated together as one coherent record, per field first (so the error names the offending field) and then by relationship:

1. all three required — a record missing a count is not a decomposition of anything;
2. strictly integral — `bool` rejected explicitly (it is a subclass of `int`, and a True/False count is the exact flag confusion that made the removed `n_interruptions` useless), strings and complex values never coerced, fractional floats rejected, whole-valued floats and NumPy integers accepted;
3. `n_bridged_samples >= 0`;
4. `n_bridged_gaps >= 0`;
5. `n_eligible_subruns >= 1` — a constructed record describes a block that exists;
6. `n_bridged_gaps == n_eligible_subruns - 1` — cutting a block into *k* pieces takes exactly *k−1* cuts;
7. `n_bridged_samples == 0` **if and only if** `n_bridged_gaps == 0`;
8. `n_bridged_gaps > 0 ⟹ n_bridged_samples >= n_bridged_gaps` — every distinct gap holds at least one ineligible sample;
9. every violation raises `PetrophysicsInputError` naming the field or the relationship;
10. the removed `n_interruptions` / `n_interrupted_subruns` names are rejected outright — no alias was restored, and a stale caller now fails loudly instead of writing a record with two of its three counts unset.

### 2.3 Matrices

`INTERVAL_VALID_MATRIX` (5 rows) covers the three mandatory valid cases `0/0/1`, `2/1/2`, `3/2/3`, plus the minimum `2/2/3` and NumPy integer inputs. `INTERVAL_INVALID_MATRIX` (22 rows) covers negatives in each field, zero sub-runs with and without gaps, samples without gaps, gaps without samples, more gaps than samples, gap/sub-run mismatch, each field missing individually and all three missing, explicit `None`, booleans, numeric strings, non-integral floats, complex values, and both legacy field names. A further test asserts every error message names the well/mask and the specific field or relationship, and another asserts the **real block builder** emits only records satisfying all eight rules — so the invariants describe what the code produces, not an aspiration it violates.

---

## 3. Scientific non-regression — every mandated value re-measured on real data

| Quantity | Required | Measured |
|---|---|---|
| Boreas 1 ECGR median | ≈ 8.3968 API | **8.3968 API** |
| Boreas 1 negative samples | 4 | **4** |
| Boreas 1 zero samples | 42 | **42** |
| Boreas 1 samples above declared seabed | 2,059 | **2,059** |
| Boreas 1 endpoints / proxies / lithology-dependent masks | 0 / 0 / 0 | **0 / 0 / 0** |
| Vp/Vs — Boreas 1 (non-positive K / positive-K, negative ν) | 0 / 1 | **0 / 1** |
| Vp/Vs — Poseidon 2 | 0 / 22 | **0 / 22** |
| Vp/Vs — Poseidon North 1 | 4 / 3 | **4 / 3** |
| Vp/Vs — Proteus 1ST2 | 0 / 3 | **0 / 3** |
| Interval register rows | 5,857 | **5,857** |
| Interrupted blocks | 327 | **327** |
| Distinct bridged gaps | 443 | **443** |
| Bridged samples | 666 | **666** |
| Blocks with ≥ 2 gaps | 85 | **85** |
| Maximum gaps in one block | 5 | **5** |
| Poseidon 2 configured gross | ≈ 144.42 – 1,159.22 m, factor 8.03 | **144.42 – 1,159.22 m, factor 8.03** |
| Poseidon 2 strict-no-gap | ≈ 140.00 – 1,110.24 m, factor 7.93 | **140.00 – 1,110.24 m, factor 7.93** |
| `n_extrapolated` per well | 0 | **0** |
| Deterministic outputs / figures | 8 CSV+JSON / 4 PNG | **8 / 4** |
| Named lithology assigned | none | **false**, 138 fields checked, 0 violations |

**All 12 outputs and figures are byte-identical to Increment 6.1.1**, verified by SHA-256 against the pristine baseline extraction before regeneration. No scientific computation or configured policy changed, so none was expected to differ, and none does.

---

## 4. Exact packaged delta — Increment 6.1.1 → Increment 6.1.2

Measured by clean recursive SHA-256 comparison of fresh extractions.

**Changed — 8 files:**

1. `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb` — regenerated; two new narrative sections, two new gate checks, `%%writefile` bodies refreshed from the corrected sources
2. `README.md` — Increment 6.1.2 release line and limitations bullet
3. `p2mem/__init__.py` — version 0.6.3 and the Increment 6.1.2 changelog
4. `p2mem/method_eligibility.py` — Finding 2, full interval-record invariant enforcement
5. `p2mem/wellframe_models.py` — Finding 1, per-occurrence validator redesign
6. `pyproject.toml` — version 0.6.3 (dependency list untouched)
7. `tests/test_method_eligibility.py` — interval matrices and derived-gate injections
8. `tests/test_petrophysics.py` — validator discrimination matrix

**Added — 2 files:** `INCREMENT_06_1_2_MANIFEST.md`, `INCREMENT_06_1_2_SHA256SUMS.txt`.

**Removed — 0 files. Total path differences — 10.**

**Byte-identical to 6.1.1**, listed individually so no output hides behind a directory: `config/petrophysics_eligibility.yml`; `p2mem/petrophysics.py`, `p2mem/petrophysics_models.py`, `p2mem/wellframe.py`; `tests/test_wellframe.py`, `tests/synthetic_inc6.py`; all 8 deterministic outputs (`eligibility_interval_register.csv`, `gr_endpoint_scenarios.csv`, `gr_family_qc_summary.csv`, `gr_proxy_sensitivity_summary.csv`, `method_eligibility_summary.csv`, `petrophysics_eligibility_issues.csv`, `thickness_sensitivity_summary.csv`, `petrophysics_eligibility_manifest.json`) and all 4 figures (`fig01`–`fig04`); every locked Increment 1–5.1.2 file; and all historical manifests and ledgers through `INCREMENT_06_1_1_*`, which are **not rewritten**.

**Locked-baseline audit:** of the 150 files inherited from Increment 5.1.2, exactly **three** differ — `pyproject.toml`, `p2mem/__init__.py`, `README.md` — the three historically permitted additive metadata files. No unauthorized locked file changed.

**Dev-only, never packaged** (reported separately): `dev_scratch_inc6/build_notebook_06.py` (changed); `run_integration_06.py`, `verify_execution_order_06.py`, `probe_*.py`, `dev_scratch_inc4_1/`, `dev_scratch_inc5/` (unchanged).

---

## 5. Test suite — actual measured counts

| | Count |
|---|---|
| Increment 6.1.1 baseline, re-run before any change | **703 passed** |
| After Increment 6.1.2 | **818 passed** (0 failed, 0 errors, 0 skipped) |
| New tests added | **115** — `test_petrophysics.py` +74 (111 → 185), `test_method_eligibility.py` +41 (74 → 115); `test_wellframe.py` unchanged at 36 |
| Locked Increment 1–5.1.2 tests, run in isolation | **482 passed** across **11** byte-identical files |
| Notebook's own `pytest` subprocess during fresh execution | **818 passed** |

One pre-existing test was amended, not weakened: `test_inconsistent_interval_record_is_rejected_at_construction` previously omitted `n_bridged_samples`, which the stricter constructor now rejects earlier under the missing-field rule. It supplies all three counts so the gap/sub-run mismatch remains the *only* defect under test. The assertion it makes is unchanged.

---

## 6. Notebook

| Property | Value |
|---|---|
| Cells | **73** (38 code, 35 markdown) |
| Unique cell IDs | yes |
| Saved execution outputs / counts | **zero** |
| `nbformat.validate()` | **passes** |
| `%%writefile` bodies verified byte-for-byte | **14 / 14** |
| Code cells executed in real order from a fresh `/content`-style root | **38 / 38** |
| Test cell | real `pytest` subprocess, return code inspected |
| Completion-gate checks | **19 / 19 `[PASS]`** |

**The gate count changed from 17 to 19**, honestly reported: two checks were added, both exercising the live implementation rather than a recorded result — one asserting the validator discriminates in *both* directions (rejecting five project-specific assertions, permitting four legitimate method/boundary statements, and giving a label no latitude), and one asserting every interval record produced by the run satisfies all eight count invariants *and* that the live constructor refuses the three record shapes that were constructible before this patch. Neither is hardcoded; both would fail if the corrections were reverted.

---

## 7. Clean-room verification (all 17 required steps, against a fresh extraction of the final ZIP)

1. ZIP safety — every entry scanned for absolute paths, `..` traversal, duplicate names and symlinks: **none found**.
2. Offline editable install from the extraction: **succeeded**.
3. `p2mem.__version__`: **`0.6.3`**, resolved from the extracted tree.
4. Full combined test suite: **818 passed**, 0 failed, 0 errors, 0 skipped.
5. Locked-test subset in isolation: **482 passed**.
6. Notebook validation and source parity: 73 cells, unique IDs, zero outputs, `nbformat.validate()` passes, **14/14** `%%writefile` bodies byte-identical.
7. Full notebook execution from a fresh simulated Colab root: **38/38** cells, internal pytest **818 passed**, **19/19** gate checks `[PASS]`.
8. Real four-well integration: 4 approved LAS + 4 approved deviation surveys loaded, 4 frames assembled, zero extrapolated.
9. Outputs regenerated independently from two different project roots (clean-room extraction and notebook sandbox).
10. Byte determinism across roots: **all 12 identical**.
11. All scientific outputs/figures byte-identical to Increment 6.1.1: **12 / 12**.
12. Absolute-path scan of every output: **zero matches**.
13. No private LAS, deviation, checkshot, formation-top or Vp/Vs file packaged; the packaged `.las` files are synthetic `tests/fixtures/` files, unchanged from the baseline.
14. Recursive comparison against Increment 6.1.1: **8 changed, 2 added, 0 removed**, each listed individually in §4.
15. Common-file comparison against locked Increment 5.1.2: only the three permitted metadata files differ.
16. Deterministically sorted SHA-256 ledger created and verified entry by entry against the clean-room extraction.
17. No `__pycache__`, `.pyc`, `.pytest_cache`, editable-install artifact or `dev_scratch_*` script is packaged.

---

## 8. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** This patch corrects validator integrity and record-invariant enforcement. It adds no calibration evidence, computes no new physical quantity, changes no configured policy, and raises no assurance level. Eligibility remains an input-admissibility statement, not a validity statement; the screening proxy remains uncalibrated and endpoint-sensitive; lithology remains **unresolved** in every well.

## 9. Stop condition

Increment 6.1.2 is complete as of this manifest. Per the governing instruction, work stops here to await independent audit. **Increment 7 has not been started.**
