# Increment 6.1.5 Manifest — Positive Authorization for Every Persisted Controlled Field

**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational (unchanged)
**Package version:** `p2mem` 0.6.5 → **0.6.6**
**Baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.4.zip`, SHA-256 `ceec525de19ac8e9ddc247fcfb5cf7c2a6579e66ffef04d29a844d0fc372ff4b` — **independently recomputed from the uploaded archive before any change; exact match.** 186 entries scanned: no absolute paths, traversal, duplicates or symlinks. Extracted fresh into a new clean directory.

**Baseline suite re-run before any change: 795 passed.** Baseline `p2mem.__version__` = `0.6.5`.

**Scope:** the security model, not the recognizer. No scientific calculation, endpoint, threshold, mask, well disposition, depth mapping, GR result, Vp/Vs result, contiguity result, figure or scientific interpretation was changed. No runtime dependency added — **NumPy and PyYAML remain the only two.** **All 12 outputs and figures are byte-identical to Increment 6.1.4.**

**Increment 7 has NOT been started.**

---

## 1. Reproduction, performed before any edit

### 1.1 Unknown lithologies pass three of four scopes

| Assertion | label | interpretive | explanatory | method |
|---|---|---|---|---|
| The interval is chalk. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is halite. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is gypsum. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is conglomerate. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is chert. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is tuff. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is basalt. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is dolostone. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is lignite. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is calcareous. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is argillaceous. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is arenaceous. | **PASS** | **PASS** | **PASS** | FAIL |
| The interval is qxzite. *(fabricated)* | **PASS** | **PASS** | **PASS** | FAIL |

**Reported accurately: these examples did NOT pass in every scope.** They already failed in `method` scope, because method scope was the only one that then required registration. That contrast is not incidental — it is the clue this patch generalises: the one scope built on positive authorization was the one scope that held.

None of these words is in `PROHIBITED_LITHOLOGY_TERMS` (28 terms). The linter returns empty for every row above.

### 1.2 The deeper finding: innocent text passed too

| Text | label | interpretive | explanatory |
|---|---|---|---|
| Everything looks fine. | **PASS** | **PASS** | **PASS** |
| The operator was competent. | **PASS** | **PASS** | **PASS** |

Three of the four scopes accepted **arbitrary text**. The `chalk` case was not a vocabulary gap in an otherwise sound design; it was a visible symptom of acceptance-by-default.

---

## 2. Correction — the security model is inverted

Increments 6.1 through 6.1.4 all asked *"does this text contain a geological assertion?"* — 6.1.1 with sentence-wide cue lists, 6.1.2 with per-occurrence grammar, 6.1.3 with a prohibited-term scan, 6.1.4 with that scan plus an explanatory registry. All four shared one structural assumption: **content is acceptable by default and becomes unacceptable only when a recognizer fires.** That assumption cannot survive a word the recognizer has never seen, and a longer blacklist would have caught `chalk` and still missed `qxzite`.

**Nothing is acceptable by default. Every persisted controlled field must be positively authorized.**

| Scope | Authorization required |
|---|---|
| `SCOPE_LABEL` | value must be a member of `APPROVED_LABELS` — a typed, enumerated registry. Arbitrary caller-supplied label text is rejected **even with no recognizable lithology term**. |
| `SCOPE_INTERPRETIVE` | text must resolve to a registered `statement_id`, or a reviewed `template_id` whose substitutions are strictly typed. Unregistered free text rejected unconditionally. |
| `SCOPE_METHOD` | text must resolve to a registered `statement_id`; **id and exact rendered text validated together**. |
| `SCOPE_EXPLANATORY` | identical, for every non-empty statement, **whether or not any prohibited term is detected**. |

The early-pass behaviour equivalent to `if no prohibited term is found: accept` is **removed from every scope**. `test_no_scope_accepts_text_merely_because_no_rock_term_was_found` sweeps all four scopes with text the linter provably cannot fault and asserts every scope rejects it.

### 2.1 Provenance

Every registered entry carries a stable id, its scope, its exact text or controlled template, a scientific purpose, a provenance justification, and its permitted typed substitutions. Duplicate ids raise at import. The id or template binding is the **canonical persisted decision** — provenance is never inferred from wording.

### 2.2 The registries were measured, not designed

Captured from the actual persisted Increment 6 validation scope (143 entries):

| Registry | Size | Content |
|---|---|---|
| `APPROVED_LABELS` | **17** | every distinct non-empty label value the project persists, across 7 field kinds (`use_status`, `evidence_class`, `exclusion_reason`, `gr_family_canonical_name`, `gr_family_source_curve_name`, `mask_name`, `gr_proxy_confidence_class`) |
| `REGISTERED_STATEMENTS` | **17** | 11 interpretive, 5 method, 1 explanatory |
| `REGISTERED_TEMPLATES` | **1** | `gr_proxy_confidence_rationale`, covering the three per-well rationales |

The template's only variable parts are three substitution slots, each declared as type `decimal` — a predicate over the substituted string that admits any number and no words at all, so a template cannot become a channel for prose. `"high"`, `"very high"`, `"0.1.2"`, `"1e5"`, `"NaN"` and `""` are all rejected as substitutions.

An empty optional field (an absent `exclusion_reason`) persists no claim and is skipped before scope dispatch; every **non-empty** field requires authorization.

### 2.3 `PROHIBITED_LITHOLOGY_TERMS` is demoted to a linter

It remains only to annotate a violation with whatever rock words it happens to recognize, so a reader sees why a rejected string looked suspicious. Its docstring states that it **authorizes nothing** and that its vocabulary is **not exhaustive**, and a test asserts both phrases are present. It is never cited as evidence that all named lithologies have been detected — and every rejection in §3 below occurs with it returning **empty**.

---

## 3. Regression behaviour — all nine required properties

| # | Requirement | Where asserted |
|---|---|---|
| 1 | The twelve named assertions fail in label, interpretive **and** explanatory scope | `test_unknown_lithology_assertions_are_rejected_in_every_controlled_scope` (12 × 4 scopes) |
| 2 | A fabricated word (`qxzite`) is rejected because unregistered, not blacklisted | `test_fabricated_words_are_rejected_because_nothing_authorized_them`, with `test_the_linter_recognizes_nothing_in_any_of_these` proving the linter is empty for every one |
| 3 | Innocent but unregistered text is likewise rejected | `test_innocent_unregistered_text_is_rejected_too` — the decisive test, since there is nothing for a detector to detect |
| 4 | The two legitimate limitation sentences pass only through a registered id | `test_legitimate_sounding_limitations_still_need_a_registered_id` (rejected in all four scopes) and `test_the_projects_real_limitation_statement_passes_through_its_id` |
| 5 | Exact registered method and explanatory statements pass | `test_every_registered_statement_passes_under_its_own_id` |
| 6 | Near-miss, case change, added clause, changed punctuation, unknown id, duplicate id, id/text mismatch, undeclared template field all fail | `test_near_miss_text_fails_against_its_registered_id`, `test_every_method_statement_rejects_a_case_change`, `test_unknown_statement_id_fails`, `test_id_text_mismatch_fails`, `test_registry_ids_are_unique`, `test_undeclared_or_missing_template_fields_fail`, `test_unknown_template_id_fails`, `test_statement_cannot_authorize_a_different_scope`, `test_presenting_both_a_statement_id_and_a_template_id_fails` |
| 7 | Every actual persisted label, note, status, limitation and explanatory field is accounted for | `test_every_real_persisted_field_is_positively_authorized`, plus the real run: **143 fields checked, 0 violations** |
| 8 | No fallback path accepting arbitrary text on absence of a rock term | `test_no_scope_accepts_text_merely_because_no_rock_term_was_found` |
| 9 | Constructor protections intact | the 6.1.2–6.1.4 interval matrices, unchanged and still passing |

---

## 4. Source and documentation cleanup

- **Duplicate scope constants removed.** `SCOPE_LABEL` / `SCOPE_INTERPRETIVE` / `SCOPE_EXPLANATORY` / `VALID_VALIDATION_SCOPES` were defined **twice** in `p2mem/wellframe_models.py` (lines 402–408 and 454–460 of the 6.1.4 file). One definition now exists.
- **Stale 6.1.3 commentary removed**, along with the superseded `MethodStatement` / `METHOD_STATEMENTS` and `GenericExplanatoryStatement` / `GENERIC_EXPLANATORY_STATEMENTS` registries they described.
- **The validator docstring is corrected.** It described the superseded project-reference rule; it now describes authorization by id and template.
- **The claim that "no vocabulary gap can admit anything" is removed** wherever it rested on the blacklist. It is re-stated only where the positive-authorization architecture genuinely makes it true — because nothing is admitted by recognition at all.
- **Historical manifests are unchanged.** The inaccurate assurance wording in the Increment 6.1.3 and 6.1.4 manifests — which credited closure over a *prohibited vocabulary* — is explicitly superseded here and in the completion record, not silently rewritten.

### 4.1 The defensible assurance statement

> Every persisted project-specific classification and interpretive statement is generated from an approved typed value, a controlled template, or a registered statement. Arbitrary free text cannot enter these controlled fields.

This is **not** a claim that the software understands or exhaustively recognizes natural-language lithology. It does not, and no earlier Increment 6 version did. **Free-form notebook narrative and documentation lie outside these controlled fields** and remain subject to ordinary manual scientific review; they are not covered by any NLP-classification guarantee, because none is made.

---

## 5. Scientific non-regression

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
| Interrupted / gaps / bridged samples / ≥2 gaps / max | 327 / 443 / 666 / 85 / 5 | **327 / 443 / 666 / 85 / 5** |
| Poseidon 2 gross | 144.42–1,159.22 m, ×8.03 | **144.42–1,159.22 m, ×8.03** |
| Poseidon 2 strict-no-gap | 140.00–1,110.24 m, ×7.93 | **140.00–1,110.24 m, ×7.93** |
| Extrapolated samples, every well | 0 | **0** |

**All 12 outputs and figures are byte-identical to Increment 6.1.4** — including `petrophysics_eligibility_manifest.json`. No assurance-only JSON field needed to change: `n_fields_checked` remains **143** because the explanatory statement, previously injected as an unauthorized extra entry, is now emitted by the scope builder *with* its authorization rather than in addition to it. No figure was regenerated with different content.

---

## 6. Notebook and completion gate

| Property | Value |
|---|---|
| Cells | **73** (38 code, 35 markdown) |
| `nbformat.validate()` | passes |
| Unique cell IDs / saved outputs | yes / **zero** |
| `%%writefile` parity | **14 / 14 byte-identical** |
| Code cells executed from a fresh `/content`-style root | **38 / 38** |
| Test cell | real `pytest` subprocess, return code inspected |
| **Completion-gate checks** | **21 / 21 `[PASS]`** — measured, previously 20 |

Three gate checks are new or replaced. The probes are **generated novel tokens** — twelve pronounceable nonsense words produced from a seeded RNG, not drawn from any regression-test sentence — and each is verified invisible to the rock blacklist *before* it is used, so a pass proves the architecture rather than a finite example set:

- *Every controlled scope rejects unauthorized text (generated novel probes)*
- *Registered statements/templates authorize only themselves, exactly* — including a case change, an unknown id, a prose substitution and an arbitrary label value, all of which must fail
- *Every persisted controlled field in THIS run is positively authorized*

---

## 7. Assurance classification

Unchanged: **Tier C — screening-level, uncalibrated, educational.** No calibration evidence added, no physical quantity computed, no assurance level raised.

## 8. Stop condition

Increment 6.1.5 is complete as of this manifest. **Increment 7 has not been started.**
