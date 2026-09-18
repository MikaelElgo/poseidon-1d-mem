# Increment 6 Manifest — Gamma-Ray QC, Shale-Proxy Sensitivity, Well-Frame Assembly, and Method-Eligibility Framework

**Package version:** `p2mem` 0.6.0
**Baseline:** `Poseidon_1D_MEM_Increment_05_v5.1.2.zip`
**Baseline ZIP SHA-256 (stated and independently recomputed before any change — exact 64-character match):** `081a9d19af7abaec6e8f37a4b43026278b19663d26085251572433bea0c68781`

Increment 6 adds an auditable per-well frame assembly, factual gamma-ray-family QC, an endpoint-sensitivity framework for a dimensionless screening proxy, and three method-eligibility masks with contiguous-interval registers, on top of the LOCKED Increment 1–5.1.2 foundation. **Increment 7 has NOT been started.** No pore-pressure, elastic-property, rock-strength, stress, or wellbore-stability work exists anywhere in this increment, and **no named lithology is assigned anywhere.**

---

## 1. Scientific purpose and the four questions

| Question | Answer, as measured |
|---|---|
| 1. Which curves and depth intervals are technically usable for later density, dynamic-elastic and sonic-NCT workflows? | Quantified per well and per mask in §6. Density and dynamic-elastic eligibility begin only at ~3,900–4,800 m TVDSS in all four wells. |
| 2. How sensitive is a dimensionless GR-derived proxy to endpoint and threshold selection? | Proxy median moves up to **0.1202** from endpoint choice alone; qualifying sonic-NCT-candidate thickness moves by a factor of **8.03** (Poseidon 2), **3.50** (Poseidon North 1), **2.34** (Proteus 1ST2) across the 9 endpoint × threshold cases. |
| 3. Which wells and intervals must be excluded, and why? | **Boreas 1**, formally, under `BOREAS_ECGR_SCALE_UNRESOLVED` — demonstrated from independently measured statistics in §4. |
| 4. Does the available dataset support named lithology interpretation? | **No** — demonstrated in §7 from data availability and the measured GR continuum, not hardcoded. |

---

## 2. Architecture added

| File | Role |
|---|---|
| `p2mem/wellframe_models.py` | **new** — `CurveSlot`, `WellFrame`, `WellFrameAssemblyFailure`; evidence/depth-status vocabularies; `PROHIBITED_LITHOLOGY_TERMS` and `assert_no_lithology_vocabulary` (the machine-checkable named-lithology boundary, placed at the earliest layer a rock name could leak into a persisted field). |
| `p2mem/wellframe.py` | **new** — well-frame assembly from a LOCKED `LasFileResult` + LOCKED `DeviationWellResult`; never opens a file, never recomputes minimum curvature, never modifies a sample, never extrapolates. |
| `p2mem/petrophysics_models.py` | **new** — `GrFamilyDisposition`, `GrFamilyQcStats`, `GrEndpointScenario`, `GrProxyResult`, `PetrophysicsIssue`, `PetrophysicsEligibilityConfig`; use-status and confidence-class vocabularies. |
| `p2mem/petrophysics.py` | **new** — config loading/validation, factual GR QC statistics, endpoint-scenario resolution, GR index (clipped **and** unclipped), the linear screening proxy, confidence classification, and `find_contiguous_blocks`. |
| `p2mem/method_eligibility.py` | **new** — the three eligibility masks, per-criterion counts, limiting-criterion identification, and MD/TVD/TVDSS interval registers. |
| `p2mem/io/petrophysics_inventory.py` | **new** — deterministic row/manifest builders; no per-sample array and no absolute path ever exported. |
| `config/petrophysics_eligibility.yml` | **new** — human-authored per-well dispositions, endpoint policy, physical bounds, contiguity tolerances, eligibility rules. |
| `tests/synthetic_inc6.py` | **new** — shared synthetic builders (constructing the LOCKED real dataclasses, not mocks). |
| `tests/test_wellframe.py` | **new** — 36 tests. |
| `tests/test_petrophysics.py` | **new** — 75 tests. |
| `tests/test_method_eligibility.py` | **new** — 42 tests. |
| `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb` | **new** — 73 cells, 38 code cells, 14 `%%writefile` cells. |
| `pyproject.toml` | **updated (permitted)** — version `0.5.2` → `0.6.0`. |
| `p2mem/__init__.py` | **updated (permitted)** — version bump; additive Increment 6 scope description. |
| `README.md` | **updated (permitted)** — additive Increment 6 documentation. |
| `INCREMENT_06_MANIFEST.md` / `INCREMENT_06_SHA256SUMS.txt` | **new** — this document and its checksum ledger. |

**No locked file was modified.** A recursive `diff -rq` of a clean-room extraction of the Increment 5.1.2 baseline against this build tree confirms that **only** `pyproject.toml`, `p2mem/__init__.py` and `README.md` differ among pre-existing files — the exact three the governing instruction permits — and that every locked module, config, test, fixture, notebook, output and figure from Increments 1–5.1.2 is byte-identical.

### 2.1 The one design decision that required judgement: coverage without extrapolation

The LOCKED `map_las_md_to_tvd_tvdss` is deliberately all-or-nothing: any LAS MD sample outside the survey's station MD coverage raises `ExtrapolationRejectedError` for the whole array. That is correct for a mapping primitive and this increment does **not** weaken it. But a well frame must still be assemblable when a log runs past the last survey station, where the honest result is "these *N* samples have no defensible TVD" — not "the whole well is unusable", and emphatically not "hold the last TVD constant".

`p2mem.wellframe` therefore reads the trajectory's own MD coverage through the LOCKED `select_survey_trajectory_for_mapping`, builds an in-coverage mask, calls the **LOCKED** mapper on the in-coverage subset only (so every TVD/TVDSS number in a frame is produced by already-reviewed code, never by new arithmetic here), and writes results back into full-length arrays with NaN at out-of-coverage positions. `n_extrapolated` is therefore **0 by construction**, and the coverage gap is reported honestly as `n_depth_unmapped`. All four approved wells are fully in coverage, so in practice this reduces to a single call on the whole array; the partial and zero-overlap paths are exercised synthetically.

---

## 3. Non-negotiable data findings — how each is honoured in code

| Governing finding | Implementation |
|---|---|
| Boreas 1 ECGR anomaly → formal exclusion | `use_status: qc_only_excluded` + `exclusion_reason: BOREAS_ECGR_SCALE_UNRESOLVED` in config; `resolve_endpoint_scenarios` and `compute_gr_proxy` **raise** `PetrophysicsExclusionError`; `compute_sonic_nct_candidate_eligibility` **raises**; confidence class is forced to `GR_EXCLUDED_UNRESOLVED_SCALE` regardless of how good the coverage statistics look. Enforced as exceptions, not silent no-ops, so an empty result can never be mistaken for a computed one. Factual QC statistics **are** still computed and published. |
| Four distinct GR-family curves, never merged | Curve identity comes from the config per well, never inferred from data. Poseidon 2 and Proteus 1ST2 both canonicalize to `GR_api` but retain separate provenance (`source_filename`, `source_curve_name`); `cross_well_shared_endpoints_allowed: false` is enforced as a hard config-load error. |
| Low-GR intervals present but lithology unresolved | No rock name may enter any classification; enforced by `assert_no_lithology_vocabulary` over every generated string and tested directly. |
| Poseidon North 1 has no approved tops | `has_approved_formation_tops: false`; `n_samples_above_seabed` is `None` ("not determinable"), **never 0**; results are labelled depth-tied and unvalidated. |
| No pressure data (RFT/MDT/DST) | Recorded in the manifest's `calibration_data_available` block; no pore-pressure work is implemented. |
| No stress-calibration data (FIT/LOT/XLOT/DFIT) | Same; no stress work is implemented. |
| Vp/Vs file is sonic-derived, not independent calibration | Stated in the manifest; nothing in this increment treats it as calibration. |

---

## 4. Boreas 1 — the exclusion, demonstrated from measurement

Independently recomputed from the real files by the integration run (nothing copied from any prior review):

| Measured quantity | Value |
|---|---|
| ECGR median | **8.3968 API** |
| Poseidon 2 / Proteus 1ST2 / Poseidon North 1 GR medians | 36.0643 / 36.3685 / 41.4120 API |
| Boreas 1 median lower than the others by | **4.3× – 4.9×** |
| ECGR range | **[−0.0001, 519.1813] API** |
| Samples at or below zero | 4 negative, 42 exactly zero |
| Samples above the well's own declared seabed (locked Increment 5 marker, MDRT 513.7 m) | **2,059** (6.27% of 32,845) |
| Valid coverage | 31,854 / 32,845 = 96.98% |

**A note on the prior review's figure.** An earlier design review recorded the Boreas 1 ECGR median as "approximately 9.3 API". This patch's independently recomputed **all-valid-samples** median is **8.3968 API**. The two are reconciled, not glossed over: restricting the calculation to samples **below** the declared seabed gives a median of **9.131 API**, which is what the prior figure appears to describe. Both are reported here; the exported `gr_family_qc_summary.csv` carries the all-valid-samples statistic, and its `statistics_basis` field states exactly what filtering was applied.

**Why excluded rather than corrected.** Three responses exist. *Rescaling* requires a calibration reference — and none exists: no tool header, no calibration record, no environmental-correction metadata, no core or spectral control, and no interval logged by two tools. A rescaling factor would be invented and would propagate silently into every shale proxy, every candidate interval, and every later NCT or pore-pressure result. *Using it as-is* would assert an equivalence the data actively contradict. *Excluding it from GR-derived work while retaining it for factual QC* states exactly what is known and exactly what is not, and adds no fabricated information. Only the third adds nothing false, so it is what this project does.

**Verified consequence:** Boreas 1 received **0** endpoint scenarios, **0** proxies, **0** lithology-dependent masks, and confidence class `GR_EXCLUDED_UNRESOLVED_SCALE`. It still appears in `gr_family_qc_summary.csv`, in the manifest, and in Figure 1 — visibly segregated and labelled QC-ONLY / EXCLUDED. Its lithology-**independent** density and dynamic-elastic masks *are* computed, because excluding a gamma-ray curve says nothing about whether that well's density or sonic samples are finite.

---

## 5. GR-family QC and endpoint sensitivity — measured results

### 5.1 Per-well GR-family statistics (all-valid samples, as recorded, no correction of any kind)

| Well | Curve (source) | Valid | Median | Min | Max | p05–p95 range | Above seabed | Confidence class |
|---|---|---|---|---|---|---|---|---|
| Poseidon 2 | `GR_api` (`GR`) | 99.88% | 36.0643 | 5.1299 | 162.4835 | 86.1890 | 187 | `GR_PROXY_INTERMEDIATE` |
| Poseidon North 1 | `GRD_api` (`GRD`) | 81.31% | 41.4120 | 4.5261 | 204.6799 | 135.7610 | not determinable | `GR_PROXY_INTERMEDIATE` |
| Proteus 1ST2 | `GR_api` (`GR`) | 98.10% | 36.3685 | 7.2501 | 172.2780 | 101.9445 | not determinable | `GR_PROXY_HIGH` |
| Boreas 1 | `ECGR_api` (`ECGR`) | 96.98% | 8.3968 | −0.0001 | 519.1813 | 58.5636 | 2,059 | `GR_EXCLUDED_UNRESOLVED_SCALE` |

Longest missing runs: Poseidon 2 — 29 samples (MD 2426.85–2431.12 m); Poseidon North 1 — **5,768 samples** (MD 1562.30–2441.19 m, the reason its valid fraction is 81.31%); Proteus 1ST2 — 453 samples; Boreas 1 — 991 samples.

### 5.2 MEASURED endpoint values (ASSUMED percentile rule — never calibrated, never shared across wells)

| Well | Scenario | Rule | GR_low (API) | GR_high (API) | Separation (API) |
|---|---|---|---|---|---|
| Poseidon 2 | low | p10/p85 | 13.2992 | 78.7816 | 65.4824 |
| Poseidon 2 | base | p5/p95 | 10.9650 | 97.1540 | 86.1890 |
| Poseidon 2 | high | p1/p99 | 8.4145 | 129.9889 | 121.5744 |
| Poseidon North 1 | low | p10/p85 | 13.4853 | 97.4887 | 84.0034 |
| Poseidon North 1 | base | p5/p95 | 11.5683 | 147.3293 | 135.7610 |
| Poseidon North 1 | high | p1/p99 | 9.2526 | 159.4860 | 150.2334 |
| Proteus 1ST2 | low | p10/p85 | 18.3935 | 94.7630 | 76.3694 |
| Proteus 1ST2 | base | p5/p95 | 15.8517 | 117.7962 | 101.9445 |
| Proteus 1ST2 | high | p1/p99 | 12.6977 | 141.2679 | 128.5702 |

Every scenario carries `evidence_class = "assumed_configured"` and `calibration_status = "uncalibrated_assumed_no_calibration_data_exists"`. No code path can promote one to calibrated.

### 5.3 Screening-proxy sensitivity to endpoint choice

| Well | low | base | high | **Median spread from endpoint choice alone** |
|---|---|---|---|---|
| Poseidon 2 | 0.3477 (25.00% clipped) | 0.2912 (10.00%) | 0.2274 (2.00%) | **0.1202** |
| Poseidon North 1 | 0.3324 (25.00%) | 0.2198 (10.00%) | 0.2141 (2.00%) | **0.1184** |
| Proteus 1ST2 | 0.2354 (25.00%) | 0.2013 (10.00%) | 0.1841 (2.00%) | **0.0513** |

Clipped and unclipped indices are computed and retained together in memory; the clipped counts above quantify exactly how much real data fell outside each assumed bracket — information the clipped index alone would silently discard.

---

## 6. Method-eligibility results

Eligible fractions (of each well's full sample count):

| Well | `eligible_density_for_sv` | `eligible_dynamic_elastic` | limiting criterion (elastic) | samples excluded by non-physical Vp/Vs |
|---|---|---|---|---|
| Boreas 1 | 23.42% | 7.81% | `vs_finite_positive_in_bounds` | 1 of 2,714 both-valid |
| Poseidon 2 | 24.91% | 12.09% | `vs_finite_positive_in_bounds` | 22 of 4,147 both-valid |
| Poseidon North 1 | 24.09% | 23.60% | `rhob_finite_in_bounds` | 7 of 9,472 both-valid |
| Proteus 1ST2 | 6.76% | 3.05% | `vs_finite_positive_in_bounds` | 3 of 982 both-valid |

**A reporting subtlety that was corrected during development, because the first version was misleading.** The Vp/Vs criteria (`vp_greater_than_vs`, `vp_vs_ratio_in_poisson_domain`) are only *meaningful* where both velocities exist, so their raw pass counts are structurally bounded by VS availability — VS being by far the scarcest curve in these wells (3.14%–30.25% valid). Selecting the "limiting criterion" from those bounded counts made three of the four wells report `vp_vs_ratio_in_poisson_domain`, which reads as a *physics* problem when the actual cause is *data coverage*. The Vp/Vs conditions are therefore now reported as explicit **failure counts within the both-velocities-valid subset** (the rightmost column above, and the `diagnostic_counts` field in `method_eligibility_summary.csv`), and are excluded from the limiting-criterion comparison. The corrected result is unambiguous: VS sparsity limits three wells and density limits Poseidon North 1, while genuinely non-physical Vp/Vs affects only 1–22 samples per well. Zero samples in any well have VP ≤ VS.

Sonic-NCT **candidate** eligibility spans 8.28%–27.77% depending on well, endpoint scenario and threshold (full grid in `method_eligibility_summary.csv`).

**Qualifying candidate thickness across the 9 endpoint × threshold cases** (blocks meeting the configured 20-sample / 5 m minimums):

| Well | Minimum | Maximum | Factor |
|---|---|---|---|
| Poseidon 2 | 144.4 m | 1,159.2 m | **8.03×** |
| Poseidon North 1 | 347.6 m | 1,215.8 m | **3.50×** |
| Proteus 1ST2 | 374.4 m | 877.9 m | **2.34×** |

This spread is the measured cost of two uncalibrated choices. It is reported, not reduced by preferring one case — and it is the single most important number for any later NCT or pore-pressure work, because a result built on one endpoint/threshold pair would inherit this entire range as unquantified uncertainty.

**Poseidon 2's best-covered deep interval:** density-eligible over TVDSS 4,063.74–5,272.74 m (7,946 samples); dynamic-elastic-eligible over 4,682.94–5,272.74 m (3,855 samples); both simultaneously over 4,682.94–5,272.74 m (3,855 samples).

**Eligibility is not validity.** Density eligibility begins only at ~4,064 m TVDSS in the best-covered well, so these logs cannot support an overburden integration from surface regardless of how many individual samples are eligible. That limitation is a property of the data, is visible on Figure 3's depth axis, and is restated in every exported table's `limitations` field.

---

## 7. Named lithology — why the answer is no, demonstrated rather than asserted

**Independent lithological evidence available in this project:** core description — none; cuttings description — none; image log — none; spectral GR (Th/U/K separation) — none; calibrated multi-mineral solution — none; XRD/mineralogy — none.

**Why GR alone cannot close the gap.** The mapping from mineralogy to gamma-ray response is many-to-one, so its inverse is not unique: a clean quartz sandstone and a clean limestone both read low and are indistinguishable on GR alone; an arkosic or glauconitic sand reads 60–100+ API on ⁴⁰K while being good reservoir rock; an organic-rich shale reads high largely on uranium while a kaolinite-dominated shale reads modestly; uranium salts precipitated in fractures produce high GR in rock that is not clay-rich at all. The measured distributions confirm the practical consequence — each well's GR spans a continuum (Poseidon 2 p05→p95: 10.97→97.15 API; Poseidon North 1: 11.57→147.33; Proteus 1ST2: 15.85→117.80) with **no independent tie point at any value**.

**Conclusion:** the regionally persistent low-GR intervals in Poseidon 2, Poseidon North 1 and Proteus 1ST2 are real and are reported, but their lithology is **UNRESOLVED**. Naming them would require evidence this project does not have.

**Enforcement:** every classification string generated anywhere in this increment is checked against `PROHIBITED_LITHOLOGY_TERMS` (shale, sand, sandstone, carbonate, limestone, dolomite, marl, claystone, siltstone, mudstone, coal, salt, anhydrite, evaporite, reservoir rock, non-reservoir rock, pay, net pay). The five permitted classes — `GR_PROXY_HIGH`, `GR_PROXY_INTERMEDIATE`, `GR_PROXY_LOW`, `GR_NOT_AVAILABLE`, `GR_EXCLUDED_UNRESOLVED_SCALE` — describe **data and proxy confidence only**. The manifest records `named_lithology_assigned: false`.

**Nonlinear Vsh transforms are DEFERRED,** not overlooked: Larionov, Clavier, Stieber and every other nonlinear transform would require a retrieved, verified primary-source method record and a closed method-register entry, none of which exists in this project. `nonlinear_vsh_transforms_enabled: true` is rejected as a hard config-load error.

---

## 8. Test suite — actual results

- Increment 5.1.2 baseline, re-verified before any change: `pytest -q` → **482 passed**.
- After this increment: `pytest -q` → **635 passed**, zero failures, zero errors, zero skips (482 locked + **153 new**).
- New tests: `tests/test_wellframe.py` (36), `tests/test_petrophysics.py` (75), `tests/test_method_eligibility.py` (42).
- **All 482 locked tests pass unchanged**, and every locked test file is byte-identical to the baseline.

Coverage of the required categories:

| Required category | Covering test(s) |
|---|---|
| well-frame sample/order preservation | `test_well_frame_preserves_sample_count_and_order`, `test_well_frame_arrays_are_read_only` |
| no MD→TVD/TVDSS extrapolation | `test_no_extrapolation_all_samples_within_coverage`, `test_samples_beyond_survey_coverage_are_unmapped_never_extrapolated`, `test_sample_below_survey_start_is_unmapped`, `test_zero_coverage_overlap_reports_none_status`, `test_tvdss_equals_tvd_minus_datum_elevation` |
| per-file GR identity preservation | `test_gr_family_identity_is_recorded_never_guessed`, `test_two_wells_sharing_canonical_gr_name_stay_distinct`, `test_absent_gr_family_curve_is_flagged_never_substituted` |
| Boreas exclusion | `test_excluded_well_gets_no_endpoint_scenarios`, `test_excluded_well_gets_no_proxy`, `test_excluded_well_still_gets_factual_qc_statistics`, `test_excluded_well_classified_as_excluded_not_by_coverage`, `test_nct_candidate_forbidden_for_gr_excluded_well`, `test_qc_only_disposition_requires_machine_readable_reason` |
| endpoint order validation | `test_reversed_endpoints_rejected` |
| identical endpoint rejection | `test_identical_endpoints_rejected` |
| low/base/high scenario calculation | `test_low_base_high_scenarios_all_computed_with_measured_endpoints`, `test_endpoint_scenario_is_never_calibrated` |
| clipped and unclipped IGR behavior | `test_gr_index_basic_arithmetic`, `test_clipped_and_unclipped_differ_outside_endpoints`, `test_proxy_equals_clipped_igr_under_linear_identity`, `test_proxy_clipping_counts_are_reported` |
| NaN-mask preservation | `test_nan_input_stays_masked_and_nan_in_both_outputs`, `test_well_frame_never_deletes_failed_samples` |
| infinite-value handling | `test_infinite_input_is_explicitly_invalidated` (±∞) |
| boolean/string/complex rejection | `test_boolean_array_input_rejected_with_typeerror`, `test_string_array_input_rejected_with_typeerror`, `test_bytes_array_input_rejected_with_typeerror`, `test_complex_array_input_rejected_with_typeerror`, `test_object_array_input_rejected_with_typeerror`, `test_endpoint_type_class_defects_raise_typeerror` |
| multidimensional-array rejection | `test_multidimensional_array_rejected` (2-D and 3-D) |
| length mismatch | `test_length_mismatch_between_values_and_mask_rejected`, `test_well_frame_length_mismatch_rejected_with_typed_error`, `test_contiguous_blocks_rejects_depth_shape_mismatch` |
| zero-valid-coverage behavior | `test_zero_valid_coverage_rejected_for_endpoints`, `test_qc_stats_zero_valid_coverage`, `test_confidence_not_available_when_no_valid_samples`, `test_contiguous_blocks_empty_mask` |
| physical VP/VS mask behavior | `test_dynamic_elastic_rejects_vp_not_greater_than_vs`, `test_dynamic_elastic_rejects_vp_vs_ratio_at_or_below_sqrt2`, `test_dynamic_elastic_rejects_nan_in_any_of_the_three_inputs` |
| invalid-density mask behavior | `test_density_mask_rejects_nan_density`, `test_density_mask_rejects_non_physical_density` (6 parametrized cases) |
| non-deletion of failed samples | `test_well_frame_never_deletes_failed_samples`, `test_dynamic_elastic_does_not_compute_any_elastic_property` |
| contiguous-block detection | `test_contiguous_blocks_no_bridging_by_default`, `test_contiguous_blocks_all_true`, `test_intervals_report_md_tvd_and_tvdss`, `test_intervals_split_on_large_gap` |
| gap-tolerance boundary cases | `test_contiguous_blocks_bridges_small_gap_when_both_rules_permit`, `test_contiguous_blocks_does_not_bridge_large_physical_gap`, `test_contiguous_blocks_gap_exactly_at_sample_tolerance_is_bridged`, `test_contiguous_blocks_gap_one_beyond_sample_tolerance_is_not_bridged`, `test_contiguous_blocks_depth_exactly_at_tolerance_is_bridged`, `test_intervals_bridge_small_gap_and_disclose_it` |
| threshold sensitivity | `test_threshold_sensitivity_is_monotonic`, `test_nct_candidate_threshold_sensitivity_is_monotonic`, `test_wider_endpoints_damp_the_proxy` |
| deterministic result ordering | `test_batch_results_are_deterministically_ordered`, `test_export_rows_are_deterministically_ordered` |
| JSON serializability | `test_manifest_is_json_serializable_and_has_no_numpy_scalars`, `test_interval_rows_are_json_safe_and_sorted` |
| exported path sanitization | `test_export_rows_contain_no_absolute_paths`, `test_failure_message_is_sanitized_against_both_candidate_paths` |
| batch failure isolation | `test_batch_failure_isolation_missing_survey`, `test_batch_failure_isolation_missing_las`, `test_batch_failure_isolation_bad_curve_length` |
| no named-lithology vocabulary in classifications | `test_lithology_vocabulary_guard_rejects_rock_names` (8 cases), `test_lithology_vocabulary_guard_accepts_confidence_and_proxy_names` (8 cases), `test_confidence_class_never_contains_lithology_vocabulary`, `test_no_export_row_contains_named_lithology_vocabulary`, `test_manifest_declares_no_named_lithology`, `test_real_project_config_declares_no_named_lithology` |
| no per-sample real-data array exported | `test_export_never_contains_per_sample_arrays` |
| limiting criterion not confounded by curve sparsity | `test_dynamic_elastic_limiting_criterion_is_not_confounded_by_vs_sparsity`, `test_dynamic_elastic_reports_non_physical_ratio_as_an_explicit_failure_count`, `test_diagnostic_counts_are_exported_and_json_safe` |

**All tests are synthetic.** Every LAS result, deviation result, curve array, disposition and config in the new test files is fabricated in memory; no real or private project file is read, referenced, or packaged as a fixture. No new fixture file was added.

---

## 9. Outputs

`outputs/06_petrophysics_eligibility/` — 7 deterministic tables and 4 figures:

| File | Rows | Content |
|---|---|---|
| `gr_family_qc_summary.csv` | 4 | factual per-well GR statistics, for every well including the excluded one |
| `gr_endpoint_scenarios.csv` | 9 | the MEASURED endpoint values each configured rule produced |
| `gr_proxy_sensitivity_summary.csv` | 9 | IGR/proxy summary and clipping counts |
| `method_eligibility_summary.csv` | 35 | per-well, per-mask, per-scenario eligible counts and limiting criterion |
| `eligibility_interval_register.csv` | 2,707 | contiguous eligible blocks on MD, TVD and TVDSS |
| `petrophysics_eligibility_issues.csv` | 1 | the Boreas 1 exclusion issue |
| `petrophysics_eligibility_manifest.json` | — | complete run metadata, exclusions, and limitations |
| `figures/fig01_gr_family_raw_qc.png` | — | each raw GR curve on its OWN scale; Boreas visibly segregated and marked QC-only/excluded |
| `figures/fig02_gr_endpoint_and_proxy_sensitivity.png` | — | low/base/high endpoints; clipped-vs-unclipped IGR with clipped regions shaded |
| `figures/fig03_method_eligibility_coverage_panel.png` | — | three mask lanes per well on a labelled TVDSS basis; tops only where locked Increment 5 tops exist |
| `figures/fig04_sonic_nct_candidate_interval_sensitivity.png` | — | candidate blocks across all 9 endpoint × threshold cases, labelled "candidate data only — no NCT fitted" |

Every table carries well, depth basis, units, scenario, evidence class, exclusion reason, Tier C classification, and limitations. **No per-sample real-data array is exported** — that would effectively reproduce the private source logs — and **no absolute path appears anywhere**: `grep -rl "/home/\|/root/\|/content/"` across the output tree returns zero matches.

---

## 10. Clean-room verification (performed against the final `Poseidon_1D_MEM_Increment_06.zip`)

1. **Baseline hash** — `Poseidon_1D_MEM_Increment_05_v5.1.2.zip` independently re-hashed before any change: matches `081a9d19…c68781` exactly.
2. **Extraction safety** — every ZIP entry scanned for absolute paths, `..` traversal and symlinks: none found; extracted into a new empty directory.
3. **Checksums** — every entry in `INCREMENT_06_SHA256SUMS.txt` verified against the extracted files: **all match**.
4. **Offline editable install** — `pip install -e . --no-build-isolation --no-index --no-deps -q`: succeeds, `p2mem.__version__ == "0.6.0"`.
5. **Full combined test suite** — `pytest -q` from the clean-room extraction: **635 passed**, zero failures/errors/skips.
6. **Locked-test isolation** — the 11 locked test files run alone: **482 passed**, and all 11 are byte-identical to the baseline.
7. **Notebook structure/parity** — 73 cells, all unique IDs, every code cell `execution_count: null` / `outputs: []`; all 14 `%%writefile` bodies byte-identical to their packaged targets: **zero mismatches**.
8. **Notebook execution semantics** — all 38 code cells executed in order from a fresh `/content`-style working directory against a sandbox pre-populated from the **5.1.2 baseline package** (so the three updated files exist at their old versions and must be overwritten, and every new file must be created by the notebook): **all 38 executed successfully**, the notebook's own `pytest -v` subprocess reported **635 passed**, all **14** completion-gate checks printed `[PASS]`, and the final working directory equalled `PROJECT_ROOT`.
9. **Real-data integration** — all four LAS files and all four deviation surveys loaded with zero failures; four well frames assembled with zero failures; **zero samples extrapolated**.
10. **Output reproducibility** — all 7 tables and all 4 figures produced by the notebook execution path are **byte-identical** to those produced by the independent integration script.
11. **Absolute-path scan** — zero matches across the output tree.
12. **No real raw file packaged** — the extraction contains no real LAS (`*_logs.las`), no real deviation survey (`*_dev.txt`), no checkshot and no formation-top source file; `dev_scratch_inc4_1/`, `dev_scratch_inc5/` and `dev_scratch_inc6/` are absent entirely. Small synthetic fixtures remain under `tests/fixtures/` (unchanged from the baseline; Increment 6 added none).
13. **Locked-file byte comparison** — every file other than the three permitted updates and the new Increment 6 additions is byte-identical to the Increment 5.1.2 baseline.

---

## 11. Assurance classification

Unchanged: **Tier C — Screening-Level / Uncalibrated Educational**. Increment 6 adds no calibration and no interpretation. It classifies data and proxy confidence, and records eligibility — nothing in it raises the assurance level, and no calibration event has occurred.

---

## 12. Known limitations

- Tier C, screening-level, uncalibrated. No RFT, MDT, DST, FIT, LOT, XLOT or DFIT data exist; the supplied Vp/Vs file is sonic-derived and is not independent calibration data.
- No named lithology is assigned, and the data do not support assigning one (§7).
- The screening proxy is not a shale volume; its median moves by up to 0.12 across endpoint scenarios, and qualifying candidate thickness by up to 8.03× across the endpoint × threshold grid (§5.3, §6).
- Eligibility is not validity. No gated method is implemented, fitted, or validated. Density and dynamic-elastic eligibility begin only at ~3,900–4,800 m TVDSS in all four wells, so an overburden integration from surface is not supportable from these logs regardless of per-sample eligibility.
- Boreas 1 is excluded, not corrected, and remains available for factual QC display only.
- Poseidon North 1 and Proteus 1ST2 have no approved formation tops: their above-seabed counts are *not determinable* (never 0) and all their results are depth-tied and stratigraphically unvalidated.
- Poseidon North 1's GR-family curve has a 5,768-sample missing run (MD 1562.30–2441.19 m); its 81.31% valid coverage is the direct consequence.
- No nonlinear Vsh transform is implemented; all are deferred pending a closed primary-source method record.
- The `"correlation_derived"` and `"mapping"`-origin vocabulary entries are reserved for architectural completeness and are not currently produced by any Increment 6 code path. This is documented, not silently assumed.

---

## 13. Stop condition

Increment 6 is complete. It answers the four phase questions from measured evidence, adds 153 synthetic regression tests (635 total, all passing), produces 7 deterministic outputs and 4 figures, and modifies only the three files the governing instruction permits. **Increment 7 (or any pore-pressure, elastic-property, rock-strength, stress, or wellbore-stability work) has NOT been started.** Per the governing instruction, this increment stops here to await independent audit.
