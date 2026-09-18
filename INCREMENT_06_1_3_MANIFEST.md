# Increment 6.1.3 Manifest — Architectural Corrective Patch to Increment 6.1.2

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.3 → **0.6.4**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.2.zip`, SHA-256 `fb390271a32cc1446bffeb61e6140b87df9214618c42a81306e6d0967d6bbb8b` — **independently recomputed before any change; exact match.** Extracted fresh; no drifted tree reused.

**Baseline suite re-run before any change: 818 passed.**

**Scope:** the two residual findings, corrected by changing the architecture rather than extending it. No scientific threshold, tolerance, endpoint scenario, contiguity policy, GR disposition, depth-mapping rule, or real-data interpretation was altered. No runtime dependency added — **NumPy and PyYAML remain the only two.**

**Increment 7 has NOT been started.**

---

## 1. Finding 1 — the validator was overfit to its own test sentences

### 1.1 Reproduction against the unmodified 6.1.2 baseline

All six reported cases reproduce exactly. Nothing was disputed.

| Text | Scope | 6.1.2 | Required |
|---|---|---|---|
| The interval has a shale volume. | interpretive **and** explanatory | **PASSED** | violation |
| Poseidon 2 has shale volume. | interpretive **and** explanatory | **PASSED** | violation |
| The shale volume in Poseidon 2 exceeds 60 percent. | interpretive **and** explanatory | **PASSED** | violation |
| Poseidon 2 shale volume was determined to be high. | interpretive **and** explanatory | **PASSED** | violation |
| The well contains no shale volume estimate. | interpretive | **VIOLATION** | pass |
| This method for the interval contains a shale proxy calculation. | interpretive | **VIOLATION** | pass |

### 1.2 Why each escaped — and why that pattern is the real finding

| Escape | Mechanism |
|---|---|
| `has a shale volume` | `has` was not in `MAGNITUDE_PREDICATES`. A **list gap.** |
| `in Poseidon 2` | a *prepositional* possessor where only the genitive `'s` was parsed. A **list gap.** |
| `was determined to be high` | the magnitude sits four tokens right of a three-token look-ahead. A **window edge.** |
| `contains no … estimate` | the composition rule fired on subject `well` without reading the negation. A **rule-order gap.** |

The obvious response — add `has`, add prepositions, widen the window, order the rules — is exactly what produced this table twice already. Increment 6.1.1 was overfit to the eight sentences of its audit; Increment 6.1.2 was overfit to the eight sentences of *its* audit, and its manifest claimed the correction was "grammatical, not lexical." That claim was wrong: positional lexical matching over free text is still lexical matching.

**The finding is not that the vocabularies were too small. It is that deciding, from arbitrary English, whether a rock name is being *used* or *mentioned* is an unbounded natural-language task, and no finite grammar closes it.** A third round of sentences would produce a third instance.

### 1.3 Correction — remove the question, do not answer it better

Every scope is now decided by **set membership or exact equality**. Nothing in the validator can be described as parsing a sentence.

| Scope | Rule | Decidable by |
|---|---|---|
| `SCOPE_LABEL` | any prohibited token violates | token membership |
| `SCOPE_INTERPRETIVE` | **zero allowance** — any prohibited token violates | token membership |
| `SCOPE_METHOD` *(new)* | text must **equal** a member of the closed `METHOD_STATEMENTS` registry | exact equality |
| `SCOPE_EXPLANATORY` | rock name permitted unless the sentence refers to a project well **or a project rock body** | token membership |

Project-specific prose has no exemption path, so there is nothing to bypass. The project still states its own boundaries — through the registry, by registered identity with explicit provenance, never by phrasing.

**The deletion is the correction.** `ALLOWED_METHOD_TERM_PHRASES`, `GEOLOGICAL_ENTITY_TOKENS`, `COMPOSITION_PREDICATES`, `MAGNITUDE_PREDICATES`, `MAGNITUDE_WORDS`, `COPULAR_VERBS`, `ATTRIBUTIVE_ROCK_TOKENS`, `NEGATION_TOKENS`, `MODIFIER_LOOKBACK`, `PREDICATE_LOOKAHEAD`, `_occurrence_is_rock_assertion`, `_apply_method_phrase_allowance`, `_subject_head`, `_sentence_asserts_composition`, `_is_magnitude` and the `allow_method_phrases` parameter are all **gone**, and `test_no_grammar_machinery_survives` asserts none of them is importable. A future reader can confirm the architecture changed without reading a single rule.

Explanatory scope was widened in the same pass: 6.1.2 checked well *names* only, which is why an assertion about "the interval" behaved inconsistently between scopes. A project rock body is now a project reference whether or not a well is named beside it.

### 1.4 The registry was measured, not designed

Scanning every string literal in active packaged source and every persisted field under a zero-allowance rule returned **exactly five** strings carrying a prohibited token for a legitimate reason:

| `statement_id` | Where it is persisted |
|---|---|
| `proxy_limitations` | `limitations` field of every row of `gr_proxy_sensitivity_summary.csv` |
| `proxy_calibration_status` | `calibration_status` value — `screening_proxy_uncalibrated_not_a_shale_volume` |
| `shale_proxy_transform_policy_key` | a required key of the configured petrophysics policy block |
| `increment_title` | `increment_title` in `petrophysics_eligibility_manifest.json` |
| `proxy_transform_name` | `transform_name` of `GrProxyResult` (carries no prohibited token; registered for completeness) |

Each entry declares `permitted_terms`, so a registered statement cannot quietly acquire a new rock name. Membership is **exact**: truncations, fragments, case changes, trailing whitespace and suffixed variants are all refused, because "close enough" would reintroduce the judgement being removed.

### 1.5 A gap neither audit reported

Three of those five — `proxy_calibration_status`, `proxy_limitations` and `increment_title` — are written into packaged exports and **had never been inside the validated scope in any increment**. A label value literally containing `not_a_shale_volume` has been shipping in every row of `gr_proxy_sensitivity_summary.csv` since Increment 6, and no validator had ever scanned it. The reported false negatives were sentences someone would have to author; this was content the project already ships. All three are now in scope.

### 1.6 Disclosed contract change

The four sentences both audits reported as **false positives** now violate in interpretive scope **by design**, because that scope permits nothing. The need they expressed is real and is met by the registry instead. Free-text method prose is no longer permitted in any scope — permitting it is what required a grammar, and the grammar is what failed twice. `test_unregistered_method_prose_violates_everywhere` and `test_the_need_those_sentences_expressed_is_met_by_the_registry` assert both halves so this can never happen silently.

The one place this touched real content: the Boreas 1 per-well note used `shale-proxy` three times as a method name. It now names the quantity by its own self-labelling identifier — *"FORMAL EXCLUSION from every lithology-dependent, GR-normalized, screening-proxy (`VSH_GR_linear_proxy_frac`) and NCT-candidate calculation"* — which is more precise, not less. **All four real per-well notes now pass under zero allowance.** The note text reaches no packaged output, so no CSV or figure changes.

### 1.7 The acceptance criterion is closure, not a sentence list

`test_zero_allowance_closure_over_every_prohibited_term_and_position` runs **every** prohibited term through **fourteen** carrier constructions — including the exact forms that defeated 6.1.1 and 6.1.2 (`has a {t}`, `the interval's {t} is high`, `the {t} in Poseidon 2 exceeds 60 percent`, `Poseidon 2 {t} was determined to be high`), plus line breaks, parentheses, case changes and hyphen adjacency. That is **462 enumerated cases** in one test, and the space is enumerated rather than sampled. A companion test proves closure for labels.

This is the criterion that makes stopping defensible. It is not "these N sentences pass"; it is "there is no exemption path, over the whole vocabulary, in every position."

---

## 2. Finding 2 — residual type-gate defects (CONFIRMED, CORRECTED)

| Case | 6.1.2 | 6.1.3 |
|---|---|---|
| `0.0 / 0.0 / 1.0` | **ACCEPTED** despite an integer contract | `PetrophysicsInputError` |
| `NaN` | `ValueError` from `int()` | `PetrophysicsInputError` ("not finite") |
| `Inf` / `-Inf` | `OverflowError` from `int()` | `PetrophysicsInputError` ("not finite") |
| `n_bridged_sample=99` (typo) | **silently ignored** | `PetrophysicsInputError` ("unknown field") |
| `zzz=1` | **silently ignored** | `PetrophysicsInputError` ("unknown field") |

Three changes:

1. **Keyword acceptance is a whitelist** over the declared `__slots__`. Increment 6.1.2 rejected only the two known legacy names — a *denylist* where the contract wanted a *whitelist*, which is the same category error as guarding a prohibition with an allowlist, in the same patch. A misspelled count name silently left the real count unset.
2. **Floats are rejected outright**, including whole-valued ones. `0.0` is not `0`; accepting it would make the type gate depend on the value.
3. **The type is decided before any conversion is attempted**, so a non-finite value cannot raise an untyped exception from `int()` first.

The eight relational invariants from Increment 6.1.2 are unchanged and still enforced. `np.integer` inputs remain accepted; the real block builder emits them, and the four-well integration run proves it.

---

## 3. Scientific non-regression — every mandated value re-measured

| Quantity | Required | Measured |
|---|---|---|
| Boreas 1 ECGR median | ≈ 8.3968 API | **8.3968 API** |
| Boreas 1 negative / zero samples | 4 / 42 | **4 / 42** |
| Boreas 1 samples above declared seabed | 2,059 | **2,059** |
| Boreas 1 endpoints / proxies / lithology-dependent masks | 0 / 0 / 0 | **0 / 0 / 0** |
| Vp/Vs — Boreas 1 (K ≤ 0 / K > 0, ν < 0) | 0 / 1 | **0 / 1** |
| Vp/Vs — Poseidon 2 | 0 / 22 | **0 / 22** |
| Vp/Vs — Poseidon North 1 | 4 / 3 | **4 / 3** |
| Vp/Vs — Proteus 1ST2 | 0 / 3 | **0 / 3** |
| Interval register rows | 5,857 | **5,857** |
| Interrupted blocks / gaps / samples | 327 / 443 / 666 | **327 / 443 / 666** |
| Blocks with ≥ 2 gaps / max gaps | 85 / 5 | **85 / 5** |
| Poseidon 2 configured gross | ≈ 144.42 – 1,159.22 m, ×8.03 | **144.42 – 1,159.22 m, ×8.03** |
| Poseidon 2 strict-no-gap | ≈ 140.00 – 1,110.24 m, ×7.93 | **140.00 – 1,110.24 m, ×7.93** |
| `n_extrapolated` per well | 0 | **0** |
| Named lithology assigned | none | **false**, 143 fields checked, 0 violations |

### 3.1 Output byte-identity — 11 of 12, with the twelfth fully accounted for

**Eleven of twelve outputs and figures are byte-identical to Increment 6.1.2**: all 4 figures and all 7 CSVs, including the two that carry the word `shale`, because the registry stores the existing strings verbatim rather than rewording them.

`petrophysics_eligibility_manifest.json` differs. A key-by-key comparison of the flattened manifest gives **exactly one changed key, zero added, zero removed**:

```
/lithology_validation/n_fields_checked   138 -> 143
```

That is the disclosed consequence of §1.5: five registered method statements entered the validated scope. No scientific value moved. This change was predicted before it was made rather than explained after.

---

## 4. Exact packaged delta — Increment 6.1.2 → Increment 6.1.3

**Changed — 11 files:** `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`, `README.md`, `config/petrophysics_eligibility.yml`, `outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json`, `p2mem/__init__.py`, `p2mem/io/petrophysics_inventory.py`, `p2mem/method_eligibility.py`, `p2mem/wellframe_models.py`, `pyproject.toml`, `tests/test_method_eligibility.py`, `tests/test_petrophysics.py`.

**Removed — 0. Total path differences — 13.** Package grew from 182 to 184 files.

**Added — 2 files:** `INCREMENT_06_1_3_MANIFEST.md`, `INCREMENT_06_1_3_SHA256SUMS.txt`.

The authoritative file-by-file delta measured from the final ZIP is recorded in `INCREMENT_06_1_3_COMPLETION_RECORD.md` §5.

**Locked-baseline audit:** of the 150 files inherited from Increment 5.1.2, exactly three differ — `pyproject.toml`, `p2mem/__init__.py`, `README.md` — the three historically permitted additive metadata files. No historical manifest, ledger or completion record was rewritten.

---

## 5. Test suite — measured, and honestly lower

| | Count |
|---|---|
| Increment 6.1.2 baseline, re-run before any change | **818 passed** |
| After Increment 6.1.3 | **782 passed** (0 failed, 0 errors, 0 skipped) |
| Net change | **−36** |

**The count went down, and that is the correct outcome.** `tests/test_petrophysics.py` fell from 185 to 137 (−48) because the grammar-era tests — the 59-row discrimination matrix, the allowlist-minimality tests, the cue-list and look-behind structural tests — assert the behaviour of a mechanism that **no longer exists**. Keeping them would have required keeping the mechanism. `tests/test_method_eligibility.py` rose from 115 to 127 (+12).

Coverage rose while the count fell: the 59 example rows are replaced by one closure test that enumerates **462 cases**, plus a label-closure test, registry-contract tests, near-miss tests, and the full 14-sentence audit record from both rounds retained as a regression record rather than as the criterion.

Two pre-existing tests were **amended to the new contract, not weakened**: `test_method_category_name_is_permitted_in_prose_but_not_in_a_label` became `test_method_wording_is_not_permitted_in_prose_and_never_in_a_label`, and the interval matrix's float rows now expect the stricter float rejection. No test was deleted to make a failure go away.

---

## 6. Notebook

| Property | Value |
|---|---|
| Cells | **73** (38 code, 35 markdown) |
| `nbformat.validate()` | passes |
| Unique cell IDs / saved outputs | yes / **zero** |
| `%%writefile` parity | **14 / 14 byte-identical** |
| Code cells executed from a fresh `/content`-style root | **38 / 38** |
| Completion-gate checks | **20 / 20 `[PASS]`** |

**The gate count changed from 19 to 20, reported as measured.** The 6.1.2 check *"validator discriminates in BOTH directions"* was itself an example list, and would have passed on the broken 6.1.2 build. It is replaced by two stronger checks that run against the live implementation: *"Zero-allowance closure holds for EVERY prohibited term and carrier"*, and *"Method registry admits its 5 members and refuses a near-miss"*. The interval check gained the four residual type-gate rejections.

---

## 7. Clean-room verification

All 17 steps were run against a fresh extraction of the final ZIP; results are recorded in `INCREMENT_06_1_3_COMPLETION_RECORD.md` §8. No required check failed.

## 8. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** This patch corrects validator architecture and record-invariant typing. It adds no calibration evidence, computes no new physical quantity, and raises no assurance level.

## 9. Stop condition

Increment 6.1.3 is complete as of this manifest. **Increment 7 has not been started.**
