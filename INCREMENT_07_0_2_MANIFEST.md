# Increment 7.0.2 Manifest — Notebook-Gate and Public-Constructor Assurance Patch

## 1. Identity and scope

- **Project:** Poseidon 2 — 1D Mechanical Earth Model
- **Package version:** `p2mem 0.7.2`
- **Direct baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.1.zip`
- **Verified baseline SHA-256:** `ee8e8771a8a04726f396946d01783710cb1a56ab335e9ad1553809503144265b`
- **Patch scope:** assurance-only correction to Increment 7.0.1
- **Configuration schema:** remains `7.0.1`; the YAML format and every configured value are unchanged
- **Increment 8:** not started

This patch changes no private input, density value, mapping, mask, gap disposition,
threshold, equation, eligibility status, stress result, CSV/JSON scientific output, or
figure. It corrects two independently reproduced assurance defects: a field-name typo in
the notebook completion gate and a weaker validation path in the public frozen
`OverburdenConfig` constructor.

## 2. Finding 1 — notebook completion-gate schema drift

Increment 7.0.1's final gate evaluated:

```python
row["assumption_basis"]
```

The emitted `shallow_column_scenarios.csv` schema and its real rows use:

```python
row["assumed_density_basis"]
```

The mismatch was reproduced directly against the packaged schema. If the gate reached
that expression during a real-data notebook run it would raise `KeyError` rather than
print a truthful completion result. `nbformat.validate()` and `%%writefile` parity could
not detect the defect because it was in a later notebook-only gate cell.

The gate now reads the schema-declared field. A packaged regression test loads the actual
notebook, identifies the one non-`%%writefile` completion-gate cell, and requires its
literal lookup to match the real CSV schema. The repaired expression was also evaluated
directly over all 10 packaged scenario rows; it returns exactly the three closed basis
tokens and raises no exception.

## 3. Finding 2 — public constructor bypassed loader validation

`load_overburden_config()` already rejected malformed YAML values, but
`OverburdenConfig` is public and tests and sensitivity workflows legitimately use
`dataclasses.replace()` on it. Because the dataclass constructor previously checked only
selected numerical relationships, the following malformed replacements were
constructible:

- `schema_version="anything"`
- `min_eligible_samples_for_increment=2.9`
- `not_implemented=(1,)`
- `bridge_short_internal_gaps="false"`

The constructor now enforces the canonical post-loader representation:

- non-empty string fields and the exact `schema_version == "7.0.1"`;
- the genuine integer `increment == 7` and a genuine integer minimum sample count;
- strict booleans, rejecting integers, strings and NumPy booleans;
- finite real numerical fields, rejecting booleans, strings, complex values, `NaN`, and
  infinities;
- a non-empty, finite, non-negative, unique, strictly increasing threshold tuple;
- the exact `("low", "base", "high")` scenario-name tuple;
- a non-empty, unique tuple of non-empty string `not_implemented` entries;
- the pre-existing scientific relationships for bounds, gap thresholds, gravity,
  profile step, seawater bracket, percentile, and minimum trapezoid sample count.

Valid frozen variants remain supported. In particular,
`dataclasses.replace(config, bridge_short_internal_gaps=False)` still succeeds and leaves
the original configuration unchanged.

## 4. Files changed relative to Increment 7.0.1

Exactly **7 existing files changed**:

1. `07_Density_QC_and_Overburden_Stress_Framework.ipynb`
2. `README.md`
3. `p2mem/__init__.py`
4. `p2mem/overburden_models.py`
5. `pyproject.toml`
6. `tests/test_density_qc.py`
7. `tests/test_overburden_policy.py`

Exactly **3 files were added**:

1. `INCREMENT_07_0_2_MANIFEST.md`
2. `INCREMENT_07_0_2_COMPLETION_RECORD.md`
3. `INCREMENT_07_0_2_SHA256SUMS.txt`

No file was removed. Every other baseline file is byte-identical.

## 5. Tests and notebook

- Baseline suite before this patch: **1,182 passed**.
- Final combined suite: **1,306 collected / 1,306 passed**.
- Locked pre-Increment-7 subset: **944 passed**; all 14 locked test files are
  byte-identical to Increment 6.1.7.
- Increment 7/7.0.1/7.0.2 subset: **362 passed**.
- New regression cases: **124**, including direct-constructor matrices for every held
  scalar type, all closed tuple fields, non-finite numbers, and the notebook/schema
  binding.
- Notebook: **86 cells**, 86 unique IDs, zero saved outputs,
  `nbformat.validate()` passes, and **17/17 `%%writefile` bodies** are byte-identical to
  their packaged targets.
- Completion gate: **39 declared checks** (38 retained, one constructor-path check added).

The private raw LAS, deviation, checkshot, and formation-top inputs are intentionally not
packaged and were unavailable in this environment, so a full real-data notebook execution
is not claimed. The changed gate expression was executed directly against the packaged
real-data scenario rows, while its constructor probe and every generated source/test file
were exercised through the test suite. This distinguishes verified coverage from an
unperformed Colab run.

## 6. Scientific-output non-regression

All **13/13 files** under `outputs/07_density_overburden/` are byte-identical to the
verified Increment 7.0.1 baseline, including all nine CSV/JSON artifacts and all four PNG
figures. Therefore all previously measured scientific values and limitations remain
unchanged, including:

- no approved well supports an absolute overburden curve;
- measured increments remain 19.9325 MPa (Boreas 1), 30.6159 MPa (Poseidon 2),
  28.3422 MPa (Poseidon North 1), and 8.2718 MPa (Proteus 1ST2);
- Boreas 1's unresolved 15.64 m gap still truncates the column and excludes 2,511 deeper
  eligible samples;
- the 10 m bridge threshold remains a screening heuristic, not a rigorous error bound;
- shallow-column low/base/high values remain conditional or illustrative scenarios, not
  calibrated results or physical bounds.

## 7. Clean-room and packaging checks

The final ZIP was extracted into a new empty directory and checked for safe relative paths,
duplicate names, symlinks, checksum consistency, package version, full and partitioned
test runs, notebook validity, unique IDs, saved-output absence, `%%writefile` parity,
completion-gate schema binding, exact baseline delta, locked-test identity, scientific
output identity, absolute build-path leakage, private-input exclusion, and absence of any
Increment 8 implementation. The checksum ledger covers every packaged file except itself.

## 8. Stop condition

Increment 7.0.2 stops here. No pore-pressure/NCT, effective-stress, elastic-property,
rock-strength, horizontal-stress, mud-window, or wellbore-stability implementation was
started. **Increment 8 has not been started.**
