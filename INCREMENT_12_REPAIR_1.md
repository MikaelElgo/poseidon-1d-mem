# Increment 12 — Verification repair 1

## Reported failure

The user's Colab run passed all 1,929 historical tests and 60 of 61 Increment 12 tests. The failed assertion compared UCS values 59.3356598708641 and 59.33565987086411 for exact equality. Their difference is approximately 7.1e-15 MPa, a last-bit floating-point difference, not a different source sample or material scenario.

## Repair

Only verification, reproduction comparison, notebook explanatory text and release documentation change. The scientific functions, input configurations, packaged numerical results, pressure intervals and historical code are unchanged.

The three recomputed strength parameters use relative tolerance 1e-12 and absolute tolerance 1e-12. The test still requires exact original sample IDs, scenario IDs, inherited depth/stress strings and flags. A deliberate 1e-6 MPa strength change must fail.

Reproduce mode still validates strict SHA-256 hashes for all release inputs and each output set. It compares scientific table values using the declared numerical tolerance, while schema, row order, counts, categorical values and missing states must match. The original byte-match count remains in the run report; PNG rendering alone does not determine scientific equality. Figure format and dimensions must match.

Critical-angle ties may select symmetry-equivalent angles after last-bit changes. Comparison allows those angle choices only with matching normal/principal stresses, failure margins and shear magnitude. The independent checker then recomputes the full signed tensor at every exported angle and checks the regenerated pressure envelopes. A wrong tensor or changed stress state is not accepted.

## Validation

The regression tests cover the user's exact numerical pair, one-step recomputed-strength perturbations, meaningful strength changes, changed integer sample IDs, flags, missing values, equivalent critical-angle/shear representations and changed principal stresses. A full regeneration experiment deliberately shifts UCS and T0 upward by one floating-point step before computing all 3,822 scenarios, then compares results and independently verifies the generated wall tensors and intervals. Its evidence is under verification/increment_12_repair_1/.

The historical suite is unchanged and was not rerun for this repair: it passed in the user's supplied Colab log and in the original local qualification. Current Increment 12 tests are rerun on the repaired package. Hosted Colab execution of the repair is not claimed. The same release filename is retained so the existing ZIP_PATH works after replacing the old Drive ZIP.

## Install

Download the repaired complete ZIP, replace the earlier same-named ZIP in MyDrive/Poseidon_1D_MEM/, and rerun the notebook from the first cell. ZIP mode extracts a fresh verified folder. Leave PROJECT_ROOT empty to avoid reusing the earlier extracted release. Do not manually edit tests or regenerate checksums inside Colab.

Repair qualification completed: all 71 current tests passed; all five tables in the one-step rounding regeneration compared equal within tolerance and the independent checker passed. All 174 original scientific source/configuration/output files and every notebook code cell remain byte-identical.
