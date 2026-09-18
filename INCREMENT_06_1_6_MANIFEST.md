# Increment 6.1.6 Manifest — Authorization Enforced at the Emission Boundary

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.6 → **0.6.7**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.5.zip`, SHA-256 `0932b96cac0b65cedd854a833268d9e34b5908536ed33614a3d48ef44d234e63` — **independently recomputed from the uploaded archive before any change; exact match.** 188 entries scanned: no absolute paths, no `..` traversal, no duplicates, no symlinks. Extracted fresh into a new clean directory.

**Baseline suite re-run before any change: 866 passed.** Baseline `p2mem.__version__` = `0.6.6`.

**Scope:** where authorization is enforced, not what the science says. No scientific calculation, endpoint scenario, threshold, mask, well disposition, depth mapping, GR result, Vp/Vs result, contiguity calculation, figure or scientific interpretation was changed. No runtime dependency added — **NumPy and PyYAML remain the only two.** **11 of the 12 outputs and figures are byte-identical to Increment 6.1.5**; the twelfth differs only inside `/lithology_validation`, and that difference is disclosed in full in §6.

**Increment 7 has NOT been started.**

---

## 1. Reproduction of all five findings, performed against the untouched baseline before any edit

### 1.1 Finding 1 — the exported endpoint description bypassed validation entirely

Constructed on the untouched 6.1.5 tree:

```python
sc = GrEndpointScenario(..., description="The interval is chalk.")
rows = build_gr_endpoint_scenario_rows([sc])
rows[0]["description"]   # -> 'The interval is chalk.'   PERSISTED VERBATIM
```

`build_lithology_validation_scope()` was then called on the same run. It never receives endpoint scenarios or endpoint rows: the string `"The interval is chalk."` is **absent from all 143 scope entries**, so it cannot affect `named_lithology_assigned`, which remained `False`.

**Reported precisely, including the part that is inconvenient to the narrative:** the chalk sentence *does* fail `validate_controlled_text` in `SCOPE_INTERPRETIVE`, `SCOPE_METHOD`, `SCOPE_EXPLANATORY` **and** `SCOPE_LABEL` under 6.1.5 — 6.1.5 genuinely closed the unit validator. The defect is not that the validator accepts it. The defect is that **the export path never asks the validator.** The unit-level function is closed; the boundary at which bytes are written is not. That is the entire subject of this increment.

### 1.2 Finding 2 — output coverage was incomplete, measured rather than assumed

Every string-valued field of all eight builders was inventoried by enumerating the actual emitted records, not by reading the source. Fields emitted to disk in 6.1.5 that **no** validation scope inspected:

| Artifact | Field | Status in 6.1.5 |
|---|---|---|
| `gr_endpoint_scenarios.csv` | `description` | never presented to any validator |
| `thickness_sensitivity_summary.csv` | `limitations`, `contiguity_policy_note` | present in the scope object only as one representative copy; **the 70 emitted row occurrences were never individually checked** |
| `method_eligibility_summary.csv` | `limiting_criterion`, `limiting_reason`, `exclusion_reason` | partially represented |
| `gr_family_qc_summary.csv` | `purpose`, `population_statement`, `seabed_basis` | not consistently represented |
| `petrophysics_eligibility_issues.csv` | `message`, `detail` | not represented |
| `petrophysics_eligibility_manifest.json` | prose fields incl. `lithology_validation.derivation` | not represented |
| `eligibility_interval_register.csv` | `limitations`, `contiguity_policy_note`, `gap_summary` | one representative copy only |

**A registry entry is not equivalent to validating every emitted occurrence.** 6.1.5 reported `n_fields_checked = 143` against a manually reconstructed scope object; the actual number of emitted string field occurrences in the same run is **60,021**. The gap was 59,878 occurrences.

### 1.3 Finding 3 — the field-kind label mismatch

Under 6.1.5:

```python
validate_controlled_text("Poseidon_2.use_status", "GR", SCOPE_LABEL)   # -> PASSED
```

`ApprovedLabel.field_kind` existed and was populated, but `APPROVED_LABELS` was keyed **by value only**, so any approved value authorized any field. `"GR"` — approved as a `gr_family_source_curve_name` — authorized a `use_status`. The context string `"Poseidon_2.use_status"` was never parsed and could not have been trusted if it had been.

### 1.4 Finding 4 — the exported derivation was stale

Both the packaged `petrophysics_eligibility_manifest.json` and the builder emitted:

> "Interpretive fields admit no prohibited term at all; explanatory text may use a rock name as a generic example…"

That describes the **6.1.4 blacklist model**, which 6.1.5 replaced. It was shipped inside the artifact that is supposed to record how the conclusion was reached.

### 1.5 Finding 5 — the manifest statement was duplicated

`_named_lithology_statement` was a hardcoded literal inside `build_petrophysics_manifest()`, with a second copy in `REGISTERED_STATEMENTS`. Editing one and not the other would have changed the persisted text while the gate stayed green, because the gate validated the registry copy.

---

## 2. Correction — a closed output-field policy at the serialization boundary

`p2mem/io/output_policy.py` (**new, 1,544 lines**) makes emission the enforcement point.

```
build exact pre-serialization records
        │
        ▼
collect EVERY string field occurrence  (row × column, JSON leaf)
        │
        ▼
classify under OUTPUT_FIELD_POLICY[(artifact, field_path)]   ← closed; unknown ⇒ FAIL
        │
        ▼
authorize by category
        │
        ├── any unclassified / unauthorized / kind-mismatch ⇒ raise, WRITE NOTHING
        ▼
serialize to disk
        │
        ▼
re-read the WRITTEN BYTES and re-authorize   ← post-authorization mutation detection
```

`export_authorized_outputs()` performs all five steps. The completion gate validates **the same records that are written**, not a parallel reconstruction.

### 2.1 The eight categories — every field is exactly one of them

| # | Category | Guarantee | Policy entries |
|---|---|---|---:|
| 1 | `identifier` | structural identifier / well or scenario key, drawn from a closed set of run-supplied keys | 14 |
| 2 | `filename` | basename only; no separators, no traversal, no absolute path | 3 |
| 3 | `structural_enum` | unit string, depth-reference string, or enumerated structural token from a declared closed set | 46 |
| 4 | `typed_label` | `APPROVED_LABELS[field_kind][value]` — **exact `field_kind` required** | 22 |
| 5 | `registered_statement` | resolves to a declared `statement_id` **and** matches its exact registered text | 15 |
| 6 | `controlled_template` | declared `template_id`, typed substitutions only (`decimal`, `integer`, `quoted_policy_name`) | 3 |
| 7 | `structured_diagnostic` | machine grammar only: `name=integer`, `name(number<number)`, `CODE:token`, `;`-joined, plus enumerated sentinels — **admits no sentence** | 4 |
| 8 | `sanitized_diagnostic` | see §2.3 — **explicitly outside the controlled-interpretation guarantee** | 9 |
| | **`OUTPUT_FIELD_POLICY`** | 74 CSV columns + 42 normalized JSON paths | **116** |

`CATEGORIES` is a closed tuple of exactly these eight. There is **no generic category that permits arbitrary prose.** A string field with no policy entry is a hard failure, not a default-allow: `test_an_unknown_output_column_fails_coverage`, `test_an_unknown_json_path_fails_coverage`, `test_an_unknown_artifact_fails_coverage`, `test_a_missing_declared_artifact_fails_the_gate` and `test_removing_a_required_policy_entry_fails_the_gate` each demonstrate this on real records.

`test_every_emitted_string_field_has_exactly_one_policy_classification` asserts the partition is a partition: every occurrence classifies once, under one category, with no overlap and no gap.

### 2.2 Occurrence counting is per-occurrence, not per-distinct-value

Every row × column pair and every JSON leaf is counted and authorized **individually**. The 70 identical `limitations` strings in `thickness_sensitivity_summary.csv` are 70 authorizations, not one. `test_every_occurrence_is_validated_not_merely_each_registry_entry` mutates a single row out of many and asserts the violation is reported for that row; `test_coverage_counters_are_internally_consistent` asserts controlled + structural + unguaranteed = total, with no double counting.

### 2.3 The sanitized diagnostic contract, stated honestly

Nine fields carry text derived from caught exceptions and file-level QC messages: they cannot be enumerated in advance, because their content originates outside this package. Their contract is:

- length ≤ **1,200** characters;
- restricted character set (printable ASCII subset);
- **no** newline, **no** backslash, **no** `://`;
- the value is emitted only through the sanitizer, never interpolated raw.

**This is a safety and provenance contract, not an interpretation guarantee.** `UNGUARANTEED_CATEGORIES = ("structured_diagnostic", "sanitized_diagnostic")` and the coverage report counts them in a **separate** `n_unguaranteed_occurrences` bucket that is never folded into `n_controlled_occurrences`. The assurance statement in §7 excludes them by name. They are tested separately — five dedicated tests listed in §2.3.1 — and are **not** covered by the claim that arbitrary free text cannot enter controlled fields, because for these two categories that claim would be false.

#### 2.3.1 The five dedicated diagnostic tests

| Test | Asserts |
|---|---|
| `test_the_sanitized_diagnostic_contract_bounds_length` | 1,200 characters pass, 1,201 fail |
| `test_the_sanitized_diagnostic_contract_rejects_control_and_path_sequences` | newline, carriage return, tab, `\`, `https://…`, `file:///…` all refused |
| `test_the_sanitized_diagnostic_contract_restricts_the_charset` | en-dash, degree sign and NUL refused |
| `test_a_sanitized_diagnostic_is_not_counted_as_a_controlled_field` | **the claim boundary itself** — prose *passes* the sanitized contract (by design), and passing it moves `n_unguaranteed_occurrences`, never `n_controlled_occurrences`. This test fails if the sanitized category is ever quietly folded into the controlled bucket to improve a coverage number |
| `test_the_structured_diagnostic_grammar_admits_no_sentence` | the other unguaranteed category refuses `"The interval is chalk."`, `"Everything looks fine."`, `"gaps=3; the operator was competent"` and a generated novel token |

The fourth of these is deliberately a test that the guarantee **does not** extend to diagnostics. It is written to fail if a future increment overstates the claim.

### 2.4 Labels are authorized by `(field_kind, value)`

`APPROVED_LABELS` is now a two-level mapping `field_kind → value → ApprovedLabel`, built from a flat list, with **duplicate `(field_kind, value)` raising at import**. `Authorization` carries an explicit `field_kind`; `SCOPE_LABEL` requires the caller to supply it and **never parses it out of a context string.**

| Call | Result |
|---|---|
| `use_status="screening_proxy_allowed"` | **PASS** |
| `gr_family_source_curve_name="GR"` | **PASS** |
| `use_status="GR"` | **FAIL** — "approved under `gr_family_source_curve_name`, not `use_status`" |
| `mask_name="measured"` | **FAIL** — approved under `evidence_class` |
| `field_kind="lithology"` (unknown kind) | **FAIL** — unknown field kind |
| `field_kind` omitted | **FAIL** |

`test_every_approved_label_passes_under_its_own_field_kind` (19 labels) and `test_every_label_fails_under_every_other_field_kind` run the **complete cross-product**: 19 labels × 7 field kinds = 133 checks, of which 19 must pass and **114 must fail**. Two label values were added to `evidence_class` (`assumed_configured`, `correlation_derived_screening_proxy_uncalibrated`) because the real run emits them — measured, not designed: **17 → 19 labels across 7 field kinds.**

### 2.5 Findings 4 and 5 closed at the source

- The stale derivation string is deleted. `lithology_validation.derivation` is now emitted from a **single** registered statement, `OUTPUT_STATEMENTS["lithology_validation_derivation"]`, and describes the model actually in force. A new field `lithology_validation.model = "positive_authorization_at_emission_boundary"` records it as a token, not prose.
- The duplicated literal is deleted. `build_petrophysics_manifest()` now reads `REGISTERED_STATEMENTS["named_lithology_statement"].text`. `test_no_duplicated_manifest_statement_literal_remains` asserts the literal no longer appears in `build_petrophysics_manifest`'s source and that the builder reads the registry instead, so the two copies cannot silently diverge because there is only one. `test_manifest_uses_the_canonical_registered_statement` and `test_post_authorization_mutation_of_the_manifest_statement_is_caught` cover the emitted value.

---

## 3. The export path now refuses to write

`build_gr_endpoint_scenario_rows()` authorizes `description` **as it builds the row**:

```python
"description": _assert_emitted_field_authorized(
    "gr_endpoint_scenarios.csv", "description", sc.description,
    f"{sc.well_key}/{sc.scenario_name}") and sc.description
```

An unauthorized description raises `PetrophysicsInputError` at build time — the row is never constructed, so it can never reach a file. `test_endpoint_row_builder_rejects_unauthorized_description` constructs exactly the Finding 1 object — parametrized over the chalk sentence, innocent prose and three generated novel tokens — and asserts the raise. `test_rejection_does_not_depend_on_lithology_recognition` proves the rock-name linter is empty for every one of those probes, and `test_a_registered_endpoint_description_is_accepted` proves the path is not simply closed.

At the artifact level, `export_authorized_outputs()` validates **before** opening any file:

| Test | Asserts |
|---|---|
| `test_export_refuses_to_write_anything_when_a_field_is_unauthorized` | on rejection, **no file is created and no existing file is modified** |
| `test_post_authorization_mutation_of_the_manifest_statement_is_caught` | a record mutated between authorization and serialization is caught by the re-read |
| `test_mutating_any_controlled_prose_field_is_rejected` | each controlled prose field, mutated one at a time on real records, is rejected (parametrized over every one) |
| `test_every_cross_field_label_substitution_is_rejected` | cross-field label substitution on real records is rejected |
| `test_gate_fails_when_a_final_emitted_controlled_field_is_unauthorized` | the completion gate itself goes red, not just the validator |
| `test_the_real_packaged_records_keep_the_gate_passing` | the gate is not red for everything — the real records pass |

---

## 4. Adversarial verification

Fourteen new adversarial tests operate on **the real packaged records**, with a `_builder_payloads()` fallback that regenerates equivalent records from the real builders when the output directory has not yet been written — so the tests run in a clean checkout rather than silently skipping. Novel probe tokens are generated from a seeded RNG and each is verified invisible to the rock-name linter before use, so a pass proves the architecture and not a finite example set.

**Suite: 866 → 916 passed, 916 collected, 0 failed, 0 error.**
`tests/test_method_eligibility.py` 138 → **185**; `tests/test_petrophysics.py` 210 → **213**; all other test modules unchanged. **26 new test functions**, several parametrized, for **+50 collected tests**.

---

## 5. Measured emitted-field coverage — the actual bytes on disk

Produced by re-reading the eight written files and authorizing every string field occurrence in them:

| artifact | total | ident | file | struct_enum | label | stmt | tmpl | struct_diag | sanit_diag |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `eligibility_interval_register.csv` | 58,527 | 11,671 | 0 | 29,285 | 5,857 | 5,857 | 0 | 5,857 | 0 |
| `gr_endpoint_scenarios.csv` | 81 | 18 | 0 | 36 | 9 | 18 | 0 | 0 | 0 |
| `gr_family_qc_summary.csv` | 57 | 4 | 4 | 16 | 21 | 8 | 4 | 0 | 0 |
| `gr_proxy_sensitivity_summary.csv` | 99 | 18 | 0 | 45 | 27 | 9 | 0 | 0 | 0 |
| `method_eligibility_summary.csv` | 488 | 62 | 0 | 245 | 72 | 70 | 0 | 39 | 0 |
| `petrophysics_eligibility_issues.csv` | 5 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 2 |
| `petrophysics_eligibility_manifest.json` | 220 | 43 | 8 | 85 | 61 | 12 | 4 | 5 | 2 |
| `thickness_sensitivity_summary.csv` | 544 | 124 | 0 | 210 | 70 | 70 | 70 | 0 | 0 |
| **TOTAL** | **60,021** | **11,940** | **12** | **29,925** | **6,117** | **6,044** | **78** | **5,901** | **4** |

| Result | Value |
|---|---|
| Artifacts inspected | **8 / 8 declared** |
| String field occurrences authorized | **60,021** |
| Controlled (`typed_label` + `registered_statement` + `controlled_template`) | **12,239** |
| Structural (`identifier` + `filename` + `structural_enum`) | **41,877** |
| Outside the interpretation guarantee (both diagnostic categories) | **5,905** |
| **Unclassified fields** | **0** |
| **Unauthorized controlled fields** | **0** |
| **Field-kind mismatches** | **0** |
| Distinct labels / statements / templates actually used | **19 / 28 / 3** |
| Post-serialization re-check | **OK** |

**Disclosed difference between the two passes.** The pre-serialization pass over the in-memory records reports **54,118** occurrences (12,239 controlled / 35,974 structural / 5,905 unguaranteed); the post-serialization pass over the written bytes reports **60,021** (12,239 / 41,877 / 5,905). The two **controlled** and **unguaranteed** counts are identical; the structural count rises by 5,903 because CSV serialization materializes boolean and numeric columns as strings, which the in-memory pass sees as non-strings and the on-disk pass correctly sees as `structural_enum` strings. The re-authorization gate check therefore compares `n_controlled_occurrences`, `n_unguaranteed_occurrences` and overall `ok` rather than the raw total, and says so in the notebook comment. **This is a real property of CSV, not a masked failure**, and it is stated here rather than hidden behind an equal-totals claim that would be false.

The manifest's own embedded `emitted_field_coverage` block reports the **7-CSV subset** (53,905 occurrences, 12,162 controlled, 35,845 structural, 5,898 unguaranteed) because the manifest cannot present itself while it is still being built. The export gate always requires the full declared set of 8.

---

## 6. Output identity — exactly what changed

**11 of 12 byte-identical to Increment 6.1.5:**

| Output | vs 6.1.5 |
|---|---|
| `eligibility_interval_register.csv` | identical |
| `gr_endpoint_scenarios.csv` | identical |
| `gr_family_qc_summary.csv` | identical |
| `gr_proxy_sensitivity_summary.csv` | identical |
| `method_eligibility_summary.csv` | identical |
| `petrophysics_eligibility_issues.csv` | identical |
| `thickness_sensitivity_summary.csv` | identical |
| `figures/fig01…fig04` (4 PNGs) | identical |
| `petrophysics_eligibility_manifest.json` | **differs — see below** |

**Every differing JSON path, exhaustively:**

*Changed (1):* `/lithology_validation/derivation` — the stale 6.1.4 blacklist sentence replaced by the registered statement describing the enforced model.

*Added (21):* `/lithology_validation/model`, `/lithology_validation/scope_object_fields_checked`, `/lithology_validation/scope_object_violations`, and 18 under `/lithology_validation/emitted_field_coverage/` (`artifacts_inspected[0..6]`, `distinct_labels_used`, `distinct_statements_used`, `distinct_templates_used`, `n_controlled_occurrences`, `n_field_kind_mismatches`, `n_string_field_occurrences`, `n_structural_occurrences`, `n_unauthorized_controlled_fields`, `n_unclassified_fields`, `n_unguaranteed_occurrences`, `violations`).

*Removed (2):* `/lithology_validation/n_fields_checked` (was `143`), `/lithology_validation/n_violations` (was `0`).

**Paths outside `/lithology_validation` that differ: NONE.**

**On the removed metric.** `n_fields_checked = 143` was not wrong about what it counted; it was misleading about what it implied. It counted entries in a manually reconstructed scope object while 60,021 emitted occurrences went unchecked. It is **renamed, not deleted** — `scope_object_fields_checked = 143` retains the number under a name that says what it is — and the emission-boundary numbers now sit beside it. **Byte identity was not preserved at the cost of keeping a metric whose name asserted something untrue.** This manifest and the completion record explicitly supersede the 6.1.5 statement that "no assurance-only JSON field needed to change."

---

## 7. Scientific non-regression

| Quantity | Required | Measured |
|---|---|---|
| Boreas 1 ECGR median | ≈ 8.3968 API | **8.3968 API** |
| Boreas 1 negative / zero / above-seabed | 4 / 42 / 2,059 | **4 / 42 / 2,059** |
| Boreas 1 endpoints / proxies / lithology-dependent masks | 0 / 0 / 0 | **0 / 0 / 0** |
| Vp/Vs — Boreas 1 | 0 / 1 | **0 / 1** |
| Vp/Vs — Poseidon 2 | 0 / 22 | **0 / 22** |
| Vp/Vs — Poseidon North 1 | 4 / 3 | **4 / 3** |
| Vp/Vs — Proteus 1ST2 | 0 / 3 | **0 / 3** |
| Interval rows | 5,857 | **5,857** |
| Interrupted / gaps / bridged / ≥2 gaps / max | 327 / 443 / 666 / 85 / 5 | **327 / 443 / 666 / 85 / 5** |
| Poseidon 2 gross | 144.42–1,159.22 m, ×8.03 | **144.42–1,159.22 m, ×8.03** |
| Poseidon 2 strict-no-gap | 140.00–1,110.24 m, ×7.93 | **140.00–1,110.24 m, ×7.93** |
| Extrapolated samples, every well | 0 | **0** |
| `named_lithology_assigned` | `false` | **`false`** |

### 7.1 The assurance statement, restated for this increment

> Every string field written to any of the eight Increment 6 output artifacts is classified under a closed output-field policy and positively authorized before serialization, and the written bytes are re-authorized after serialization. Fields classified `typed_label`, `registered_statement` or `controlled_template` can carry only an approved typed value under its exact field kind, a registered statement matched to its exact text, or a reviewed template with strictly typed substitutions — **arbitrary free text cannot enter them.**

> Fields classified `structured_diagnostic` or `sanitized_diagnostic` are **excluded from that guarantee by name.** `structured_diagnostic` admits a machine grammar that cannot express a sentence. `sanitized_diagnostic` admits externally-originated text under a bounded-length, restricted-charset, no-newline / no-backslash / no-scheme safety contract only — it is a provenance and injection-safety guarantee, **not** an interpretation guarantee.

This remains **not** a claim that the software understands or exhaustively recognizes natural-language lithology. It does not, and no Increment 6 version did. Free-form notebook narrative and documentation lie outside the output artifacts and remain subject to ordinary manual scientific review.

---

## 8. Package delta

| | |
|---|---|
| Files added (1) | `p2mem/io/output_policy.py` |
| Files changed (9) | `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`, `README.md`, `outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json`, `p2mem/__init__.py`, `p2mem/io/petrophysics_inventory.py`, `p2mem/wellframe_models.py`, `pyproject.toml`, `tests/test_method_eligibility.py`, `tests/test_petrophysics.py` |
| Files removed | **none** |
| New package files | `INCREMENT_06_1_6_MANIFEST.md`, `INCREMENT_06_1_6_SHA256SUMS.txt` |
| Packaged files | 188 → **191** |
| Ledger entries | **190** (self-exclusion only) |

**Locked-file discipline vs Increment 5.1.2:** 150 files inherited from 5.1.2 are present; **147 are byte-identical**, and the only three that differ are the three permitted ones — `pyproject.toml`, `p2mem/__init__.py`, `README.md`. The **482-test locked subset** (the eleven test modules byte-identical to 5.1.2) was run in isolation: **482 passed.**

---

## 9. Notebook and completion gate

| Property | Value |
|---|---|
| Cells | **75** (39 code, 36 markdown) — was 73 (38 / 35) |
| `nbformat.validate()` | passes (v4.5) |
| Unique cell IDs / saved outputs | yes / **zero** |
| `%%writefile` parity | **15 / 15 byte-identical to the packaged source** |
| Code cells executed from a fresh root | **39 / 39** |
| Test cell | real `pytest` subprocess, return code inspected — **916 passed** |
| **Completion-gate checks** | **25 / 25 `[PASS]`** — measured, previously 21 |

Four gate checks are new; each **actually runs** in the notebook and none is a static inspection:

- *Every emitted output string field is classified (0 unclassified)*
- *Every emitted controlled field is authorized (0 unauthorized, 0 kind mismatch)*
- *Written bytes re-authorize identically (0 post-authorization mutations)*
- *An unauthorized emitted field would be refused (live negative probe)* — constructs an unauthorized record at run time and asserts `export_authorized_outputs` raises and writes nothing

The gate now reads `violations`, `scope_object_fields_checked` and `emitted_field_coverage` from the manifest; the superseded `n_violations` / `n_fields_checked` keys no longer exist and the gate no longer references them.

---

## 10. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** No calibration evidence was added, no physical quantity computed, no assurance level raised. This increment changed only where authorization is enforced.

## 11. Stop condition

Increment 6.1.6 is complete as of this manifest. **Increment 7 has not been started.**
