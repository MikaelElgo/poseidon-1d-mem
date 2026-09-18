# Increment 6.1 Manifest — Corrective Patch to Increment 6

**Package version:** `p2mem` 0.6.0 → **0.6.1**
**Baseline:** `Poseidon_1D_MEM_Increment_06.zip`
**Baseline ZIP SHA-256 (stated and independently recomputed before any change — exact 64-character match):** `030582dc2894ac091ecb76074f08744c98ecf7b30fabd91e82160669655cf4f0`

A narrowly scoped corrective patch applied after an independent geomechanics, rock-physics and software audit. The Increment 6 architecture is preserved; only the four audited findings are corrected. **Increment 7 has NOT been started** — no pore pressure, NCT fitting, elastic-property calculation, rock strength, stress, or wellbore-stability work exists anywhere in this patch.

---

## 1. Finding 1 — Vp/Vs physical-domain terminology and boundaries (CONFIRMED, CORRECTED)

**The defect.** Increment 6 treated `Vp/Vs <= sqrt(2)` as "non-physical" and used a strictly **exclusive** lower bound. Both are scientifically wrong, and the error is not cosmetic: it mislabels a *policy* choice as a statement about physical possibility, and it rejects a value the policy should accept.

**Independently verified mathematics.** With *r* = Vp/Vs, for an isotropic elastic solid:

```
nu = (r^2 - 2) / (2 * (r^2 - 1))
K  = rho * (Vp^2 - (4/3) * Vs^2)
```

Evaluated directly in this patch:

| *r* | ν | K | Correct description |
|---|---|---|---|
| ≤ √(4/3) ≈ 1.1547005383792515 | — | **≤ 0** | **Genuinely outside the isotropic elastic model.** The only regime that warrants "non-physical". At *r* = √(4/3), K = 0 exactly. |
| √(4/3) < *r* < √2 | **< 0** | **> 0** | Positive bulk modulus, negative Poisson's ratio. Unusual, and outside this project's conservative policy — **but not physically impossible**. Verified at *r* = 1.30: K > 0, ν = −0.2246. |
| *r* = √2 ≈ 1.4142135623730951 | **= 0 exactly** | > 0 | **Must be ACCEPTED** by a non-negative-ν policy. Increment 6's exclusive bound wrongly rejected it. |
| *r* > 4 (configured) | ≈ **+0.4667** | > 0 | An entirely ordinary Poisson's ratio. A **configured plausibility limit**, not a Poisson-domain boundary. |

**The corrections, exactly as the least-disruptive honest policy requires.**

1. **Renamed** to a *CONFIGURED NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN* throughout code, config, exports, figures and notebook. The conservative requirement itself is preserved — only its description is corrected.
2. **The √2 bound is now INCLUSIVE** (`ratio >= sqrt(2)`).
3. **`ratio_max = 4` is retained solely as a configured plausibility limit**, named `vp_vs_ratio_plausibility_max`.
4. **Diagnostics are separated into four named counts**, plus the pass count, and are exported per well:
   `n_vp_not_greater_than_vs`, `n_ratio_nonpositive_bulk_modulus`,
   `n_ratio_positive_bulk_but_negative_poisson`, `n_ratio_above_configured_plausibility_max`,
   `n_passes_nonnegative_poisson_screen`.
5. **Nothing is aggregated as "genuinely non-physical Vp/Vs."** A test asserts that no diagnostic key contains "non_physical", and that the mask's own notes state the term does not apply to the policy exclusions.

**A numerical detail that matters at exactly the boundary.** The screen compares the **ratio** inclusively against the configured constant, never a floating-point evaluation of `nu >= 0`. Evaluating the ν expression at *r* = √2 in IEEE-754 returns ≈ 2.22 × 10⁻¹⁶, not exactly zero — a naive `nu >= 0` test would be decided by rounding noise precisely where the policy is defined.

**Config bound names** (the old conflating `vp_vs_ratio_min_exclusive` / `vp_vs_ratio_max` are gone, and a test asserts their absence):

```yaml
vp_vs_ratio_nonnegative_poisson_min_inclusive:  1.4142135623730951
vp_vs_ratio_positive_bulk_modulus_min_exclusive: 1.1547005383792515
vp_vs_ratio_plausibility_max:                    4.0
```

### 1.1 Real-data decomposition — independently reproduced, never hardcoded

Recomputed from the four approved LAS files and four approved surveys by this patch's own probe and again by the integration run:

| Well | both VP&VS valid | non-positive K (*r* ≤ √(4/3)) | positive K / negative ν | above plausibility max | VP ≤ VS | passes screen |
|---|---|---|---|---|---|---|
| Boreas 1 | 2,714 | **0** | **1** | 0 | 0 | 2,713 |
| Poseidon 2 | 4,147 | **0** | **22** | 0 | 0 | 4,125 |
| Poseidon North 1 | 9,472 | **4** | **3** | 0 | 0 | 9,465 |
| Proteus 1ST2 | 982 | **0** | **3** | 0 | 0 | 979 |

Every value matches the audit's stated counts exactly. The substantive consequence: **Increment 6's single aggregate of 7 for Poseidon North 1 was two different findings** — 4 samples genuinely outside the isotropic elastic model, and 3 with a positive bulk modulus and a negative Poisson's ratio. Only the first four deserve the description Increment 6 applied to all seven.

**Effect on eligible counts: none.** No sample in any of the four wells has *r* exactly equal to √2, so making the bound inclusive changes no real-data eligible count. The correction fixes the policy and its description, not the numbers — and that is stated plainly rather than presented as a numerical improvement.

---

## 2. Finding 2 — Poseidon North 1 depth-tied status (CONFIRMED, CORRECTED)

**The defect.** Poseidon North 1 has no approved formation tops, yet its machine-readable `use_status` was `screening_proxy_allowed` — contradicting the config's own status vocabulary (which defines `screening_proxy_allowed_depth_tied` for exactly this case) and the prose limitation stated elsewhere in the same file.

**The correction.** `use_status` is now `screening_proxy_allowed_depth_tied`, and a **config-load invariant** enforces the rule in both directions:

* a proxy-permitted well with `has_approved_formation_tops: false` **must** use `screening_proxy_allowed_depth_tied`;
* a well declaring the depth-tied status while it **does** have approved tops is equally a config/reality mismatch;
* either contradiction raises `PetrophysicsConfigError` at load time and stops the run. The invariant applies only to proxy-permitted wells, so an excluded well's `qc_only_excluded` status is unaffected.

**Propagation.** Regenerated everywhere it appears: `gr_family_qc_summary.csv`, `method_eligibility_summary.csv`, the JSON manifest's per-well block, Figure 1's and Figure 4's panel titles, the notebook's Step-11 disposition print, the completion gate (a new check asserts the depth-tied status), tests, and this documentation. **All numerical proxy values are unchanged** — the status is metadata, and byte-comparison confirms the endpoint, proxy-sensitivity and interval tables are unaffected except where the status string itself is printed.

---

## 3. Finding 3 — unsupported lithology/correlation claims and a circular gate (CONFIRMED, CORRECTED)

**Defect 3a — lithological assertions.** The config asserted that Poseidon 2's distribution was "consistent with a conventionally API-scaled gamma-ray log over a **clastic-dominated section**", followed by a disclaimer that it "asserts no lithology". The audit is right: a disclaimer does not undo the assertion — the claim is in the noun, not the caveat. Every such project-specific assertion is removed. The replacement describes the *scaling convention* and the *numeric distribution*, and nothing else.

**Defect 3b — the unsupported persistence claim.** "Regionally persistent low-GR intervals" asserts cross-well stratigraphic correlation. That cannot be established here: Poseidon North 1 and Proteus 1ST2 have **no approved formation tops**, so there is no stratigraphic framework in which to correlate anything. Replaced everywhere with the factual statement:

> Low-GR intervals occur **independently** in each of the three GR-eligible wells; cross-well stratigraphic persistence is **not established**, and cannot be, because two of those wells have no approved formation tops.

**Defect 3c — strengthened vocabulary.** `clastic`, `clastics`, `siliciclastic`, `carbonates`, `volcanic`, `igneous`, `metamorphic` and `basement` join `PROHIBITED_LITHOLOGY_TERMS`. Depositional-system and rock-class terms are prohibited for the same reason rock names are.

**Defect 3d — the circular gate.** `named_lithology_assigned = False` was a hardcoded manifest constant. A constant proves nothing: it would keep reporting "false" with a rock name sitting in a classification. It is now **DERIVED** from `validate_no_prohibited_interpretation()` run over the content actually persisted — every per-well label, config note, confidence class and rationale, mask name/note/purpose, and the manifest's own statement (138 fields in the real run). The manifest carries a `lithology_validation` block with the field count, violation count, the violations themselves, and the derivation statement; the completion gate reads all three.

**Three-tier validation scope**, because three genuinely different rules apply:

| Scope | Applies to | Rule |
|---|---|---|
| `label` | classification values, statuses, mask names, curve identities, exclusion reasons | **No prohibited term at all.** A label is a verdict; `SHALE_PROXY_HIGH` is rejected. |
| `interpretive` | per-well prose (config notes, confidence rationale, mask notes) | Compound **method-category** names in `ALLOWED_METHOD_TERM_PHRASES` (`shale proxy`, `shale volume`, …) are permitted — a project that could not write them could not state its own boundary — but a **bare** rock name or rock class is rejected. Tested that the allowlist is not a loophole. |
| `explanatory` | scientific text explaining why GR is not uniquely diagnostic | A rock name may appear as a **generic example**, but never in a sentence that also names one of this project's wells. |

**Verified behavior.** With clean content: 138 fields checked, 0 violations, `named_lithology_assigned: false`, gate passes. Injecting `"clastic-dominated section"` into a per-well note, or naming a class `SHALE_PROXY_HIGH`/`LIMESTONE_PROXY_HIGH`, makes the validation report the violation, flips `named_lithology_assigned` to **true**, and **fails the completion gate** — all three together, as the audit requires. Six tests cover this, including one asserting that the clean and injected manifests disagree, which a constant could not satisfy.

**Scientific text.** The notebook's theory section still uses "sandstone", "limestone" and "shale" as generic examples of GR non-uniqueness — permitted, and now enforced as permitted only while no project well is named in the same sentence.

---

## 4. Finding 4 — gross versus net/strict interval thickness (CONFIRMED, CORRECTED)

**The defect.** The reported "qualifying thickness" summed block **endpoint spans**. Under the configured contiguity policy such a span may contain explicitly bridged ineligible samples, and bridging may merge sub-blocks that would individually fail the minimum-block rules. Calling that "eligible thickness" overstates it.

**The corrections.** The contiguity policy itself is preserved; only the reporting is made unambiguous.

1. **Renamed and explicitly labelled.** `EligibilityInterval` now exposes `gross_thickness_{md,tvd,tvdss}_m` (endpoint span, bridging-inclusive) and `net_thickness_{md,tvd,tvdss}_m` (that span with bridged gaps removed). No unqualified `thickness_*` field survives anywhere — a test asserts every exported thickness column starts with `gross_` or `net_`.
2. **Bridging is reported in every sensitivity case.** `n_bridged_samples`, `n_interrupted_subruns`, `n_interruptions`, and per-case `n_bridged_samples_in_qualifying_blocks` / `n_interrupted_qualifying_blocks`.
3. **A strict decomposition is reported alongside.** Every mask is additionally decomposed under `contiguity_policy = "strict_no_gap"`, where nothing is bridged and gross equals net by construction. A new export, `thickness_sensitivity_summary.csv`, carries both policies with an explicit `population_statement` per row.
4. **Net is rigorously defined.** For sub-runs `[s, p−1]` and `[p+g, e]` around a gap of length *g* starting at *p*, `gross − net = y[p+g] − y[p−1]` — the depth span from the last eligible sample before the gap to the first after it. This identity is asserted numerically by a test.

### 4.1 Independently reproduced sensitivity (never hardcoded)

Qualifying sonic-NCT-candidate thickness across the 9 endpoint × threshold cases, TVDSS:

| Well | configured **gross** | factor | **strict-no-gap** | factor |
|---|---|---|---|---|
| **Poseidon 2** | **144.42 – 1,159.22 m** | **8.03** | **140.00 – 1,110.24 m** | **7.93** |
| Poseidon North 1 | 347.62 – 1,215.80 m | 3.50 | 341.54 – 1,198.16 m | 3.51 |
| Proteus 1ST2 | 374.42 – 877.86 m | 2.34 | 350.19 – 861.89 m | 2.46 |

Poseidon 2 reproduces the audit's stated observation exactly (gross 144.4–1,159.2 m, factor 8.03; strict ≈ 140.0–1,110.2 m, factor 7.93).

### 4.2 Figure 4

Increment 6 drew **all** candidate blocks while annotating **qualifying-only** totals — the picture and the number described different populations. Corrected: qualifying blocks are drawn thick and coloured, rejected sub-threshold blocks thin, grey and offset, with a legend naming both. Every annotation states GROSS and NET separately plus `N qual / M rej` and the bridged-sample count, and the figure title states that totals are gross qualifying span under the configured policy. A test asserts the figure's annotated totals equal the exported sensitivity table's qualifying totals for the same population, and that the all-block total is strictly larger.

---

## 5. Changed-file list (exhaustive, diffed against a clean-room extraction of the Increment 6 baseline)

| File | Change |
|---|---|
| `p2mem/method_eligibility.py` | Finding 1 (screen rename, inclusive √2, three named bounds, four-way regime diagnostics); Finding 4 (`EligibilityInterval` gross/net fields, `contiguity_policy`, `meets_configured_minimums`, `_net_span`, strict policy) |
| `p2mem/wellframe_models.py` | Finding 3 (vocabulary extension; `find_prohibited_lithology_terms`; `validate_no_prohibited_interpretation`; three-tier scopes; `ALLOWED_METHOD_TERM_PHRASES`) |
| `p2mem/petrophysics.py` | Finding 2 (bidirectional has-tops/use-status config invariant) |
| `p2mem/io/petrophysics_inventory.py` | Finding 3 (`build_lithology_validation_scope`, derived manifest flag, `lithology_validation` block); Finding 4 (renamed thickness columns, `build_thickness_sensitivity_rows`) |
| `config/petrophysics_eligibility.yml` | Findings 1, 2, 3 (bound names + documentation; PN1 status; lithology assertions removed) |
| `tests/test_method_eligibility.py` | 61 tests (was 42) |
| `tests/test_petrophysics.py` | 91 tests (was 75) |
| `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb` | regenerated: two new theory sections, dual-policy intervals, corrected Figure 4, derived gate, four new gate checks |
| `pyproject.toml` | version `0.6.0` → `0.6.1` |
| `p2mem/__init__.py` | version bump; Increment 6.1 changelog |
| `README.md` | Increment 6.1 documentation; lithology/persistence claims corrected |
| `outputs/06_petrophysics_eligibility/*` | regenerated deterministically; `thickness_sensitivity_summary.csv` **new**; fig01 and fig04 regenerated |
| `INCREMENT_06_1_MANIFEST.md` / `INCREMENT_06_1_SHA256SUMS.txt` | **new** |

`p2mem/wellframe.py`, `p2mem/petrophysics_models.py`, `tests/test_wellframe.py`, `tests/synthetic_inc6.py` and every locked Increment 1–5.1.2 file are **unchanged**. `INCREMENT_06_MANIFEST.md` and `INCREMENT_06_SHA256SUMS.txt` are locked historical records and are **not rewritten**.

---

## 6. Test suite — actual results

- Increment 6 baseline, re-verified before any change: **635 passed**.
- After this patch: **670 passed**, zero failures, zero errors, zero skips (**+35**).
- Breakdown: `test_wellframe.py` 36 (unchanged), `test_petrophysics.py` 91 (+16), `test_method_eligibility.py` 61 (+19).
- **All 482 locked baseline tests pass and all 11 locked test files are byte-identical** to the Increment 5.1.2 baseline.

Required regression coverage:

| Required test | Covering test(s) |
|---|---|
| Vp/Vs exactly √2 → ν = 0, passes the screen | `test_poisson_ratio_is_exactly_zero_at_sqrt2`, `test_vp_vs_exactly_sqrt2_passes_nonnegative_poisson_screen` |
| √(4/3) < *r* < √2 → K > 0, ν < 0, separately diagnosed, not called non-physical | `test_positive_bulk_modulus_with_negative_poisson_is_diagnosed_separately`, `test_no_diagnostic_or_note_aggregates_regimes_as_non_physical` |
| *r* ≤ √(4/3) → non-positive-bulk-modulus diagnostic | `test_nonpositive_bulk_modulus_is_diagnosed_separately` |
| *r* > 4 → configured plausibility-limit diagnostic | `test_ratio_above_configured_plausibility_max_is_diagnosed_separately` |
| (added) regimes mutually exclusive and exhaustive | `test_vp_vs_regime_diagnostics_are_mutually_exclusive_and_exhaustive` |
| PN1 no-tops/depth-tied invariant | `test_config_rejects_proxy_allowed_without_approved_tops`, `test_real_project_config_poseidon_north_1_is_depth_tied` |
| Contradictory has-tops/use-status rejected | `test_config_rejects_depth_tied_when_tops_actually_exist`, `test_config_accepts_the_two_consistent_combinations`, `test_excluded_well_without_tops_is_not_forced_to_depth_tied` |
| Prohibited "clastic" in persisted classification/notes | `test_clastic_and_rock_class_terms_are_prohibited`, `test_clastic_style_assertions_rejected_in_interpretive_prose` (4 cases), `test_real_config_notes_pass_the_interpretive_scope` |
| Gate fails when prohibited vocabulary is injected | `test_injected_prohibited_term_in_a_per_well_note_fails_gate`, `test_injected_prohibited_term_in_a_persisted_classification_fails_gate`, `test_gate_cannot_be_satisfied_by_a_constant`, `test_manifest_lithology_flag_is_derived_from_a_real_validation_pass`, `test_validation_scope_covers_labels_notes_and_manifest_statement` |
| Gross vs strict/net thickness arithmetic | `test_gross_exceeds_net_by_exactly_the_bridged_gap_span`, `test_strict_policy_produces_no_bridged_samples_and_gross_equals_net`, `test_strict_total_never_exceeds_configured_gross_total`, `test_interval_rows_never_export_an_unqualified_thickness_field` |
| Figure 4 totals match their stated population | `test_figure4_totals_match_the_qualifying_population_they_state`, `test_sensitivity_rows_state_their_population_and_bridging`, `test_sensitivity_rows_separate_qualifying_from_rejected_blocks` |
| (added) method-name allowlist is not a loophole | `test_method_category_name_is_permitted_in_prose_but_not_in_a_label`, `test_bare_rock_name_still_caught_alongside_an_allowed_method_phrase`, `test_explanatory_text_may_use_generic_rock_names_but_not_about_these_wells` |

All tests are synthetic; no real or private project file is read, referenced, or packaged as a fixture.

---

## 7. Clean-room verification (performed against the final `Poseidon_1D_MEM_Increment_06_v6.1.zip`)

1. **Baseline hash** — `Poseidon_1D_MEM_Increment_06.zip` independently recomputed: matches `030582dc…5cf4f0` exactly.
2. **Extraction safety** — every ZIP entry scanned for absolute paths, `..` traversal and symlinks: none found; extracted into a new empty directory. **Checksums** — every entry in `INCREMENT_06_1_SHA256SUMS.txt` verified: all match.
3. **Locked-file byte identity** — all 11 locked test files and every locked Increment 1–5.1.2 module, config, fixture, notebook, output and figure byte-identical to the 5.1.2 baseline; locked suite **482 passed** in isolation.
4. **Offline editable install** — succeeds, `p2mem.__version__ == "0.6.1"`.
5. **Complete test suite** — **670 passed**, zero failures/errors/skips.
6. **Notebook validation and fresh execution-order smoke test** — 73 cells, unique IDs, zero saved outputs/execution counts; all **38 code cells** executed in order from a fresh `/content`-style cwd against a sandbox pre-populated from the 5.1.2 baseline; the notebook's own `pytest -v` reported **670 passed**; all **17** completion-gate checks `[PASS]`; final cwd equalled `PROJECT_ROOT`.
7. **`%%writefile` parity** — all 14 cell bodies byte-identical to their packaged targets.
8. **Fresh four-LAS / four-survey integration** — all eight approved files loaded, four frames assembled, zero failures, zero samples extrapolated.
9. **Deterministic output reproduction across two roots** — all 12 outputs and figures byte-identical between the notebook execution root and the independent integration root.
10. **Absolute-path and private-raw-file scans** — zero absolute paths in any output; no real LAS, deviation, checkshot or formation-top file packaged; all 11 packaged `*.las` files are synthetic `tests/fixtures/` files unchanged from the baseline; no `dev_scratch_*` directory in the ZIP.
11. **Final ZIP SHA-256** — recorded in the completion record.

---

## 8. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational**. This patch corrects terminology, a metadata contradiction, unsupported claims, and reporting ambiguity. It adds no calibration, no interpretation, and no scientific method.

---

## 9. Stop condition

Increment 6.1 is complete. It corrects exactly the four audited findings, adds 35 synthetic regression tests (670 total, all passing), regenerates every affected output deterministically, and preserves the Increment 6 architecture and all 482 locked baseline tests byte-identically. **Increment 7 has NOT been started.** Per the governing instruction, this patch stops here to await independent audit.
