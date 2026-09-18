# Increment 7.0.1 Manifest — Corrective Density-Gap Integration and Validation Hardening

## 1. Scope and baseline

This is a narrowly scoped corrective patch to Increment 7.0.0. It does not begin
Increment 8 and does not add pore-pressure, NCT, effective-stress, elastic,
rock-strength, horizontal-stress, mud-window, or wellbore-stability modelling.

The direct baseline is `Poseidon_1D_MEM_Increment_07.zip`, independently hashed
before modification as:

`29ac378168987ab8cd7dd902c1d7bd654c206a80799c86b1de5c78a73d15aad4`

The baseline ZIP contains 224 safe, unique entries. Its 223-entry Increment 7
ledger was independently rechecked before this patch. Package version changes
from `p2mem 0.7.0` to `p2mem 0.7.1`.

## 2. Confirmed findings and corrections

### 2.1 Any unresolved internal gap must stop the integral

Increment 7.0.0 truncated the stress profile only when the gap class was
`long_internal_gap`. A short internal gap could remain unresolved when bridging
was disabled or a bridge precondition failed; an unmapped-depth internal gap was
also unresolved. In those cases the old profile builder could select valid nodes
on both sides and integrate one trapezoid across unknown density.

Increment 7.0.1 makes truncation disposition-driven. The first gap whose
disposition is `unresolved_not_bridged` and whose class is internal stops the
profile, irrespective of whether it is short, long, isolated, or caused by
missing depth mapping. Shallow and terminal gaps remain outside the bracketed
measured column and are handled separately.

The eligibility record now exposes `n_unresolved_internal_gaps` in addition to
the narrower historical `n_unresolved_long_gaps`. Constructor invariants require
the long-gap count not to exceed the internal count and require
`column_uninterrupted == (n_unresolved_internal_gaps == 0)`. A new limiting code,
`internal_gap_unresolved`, distinguishes a non-long unresolved internal gap from
`internal_gap_exceeds_limit`.

Direct synthetic regression: a 3-sample short gap in a constant 2,000 kg/m3
column, with bridging disabled, truncates at the last node above the gap. The
computed increment is the analytical `2000 × 9.80665 × 9 = 176,519.7 Pa`; eight
eligible samples below the truncation are excluded. A separate missing-depth-
mapping case also truncates at the gap.

### 2.2 The former endpoint-only bridge-error formula is withdrawn

The original documentation described
`0.5 × |rho_right − rho_left| × gap_thickness × g` as a rigorous maximum bridge
error. It is not a bound on an unknown interior density profile without an
additional interior-behaviour constraint; equal endpoints make the formula zero
even though the missing interval can contain a non-zero excursion.

The 10 m TVD threshold is now described only as a transparent project heuristic.
Its effect remains published through the existing 0/2/5/10/20/30 m sensitivity.
No replacement numerical error bound is asserted.

### 2.3 Shallow-column endpoints are scenarios, not physical bounds

The configured seawater-density endpoint is now explicitly a conditional low
scenario requiring a fully saturated-column assumption. The well's measured P05
is an illustrative upper scenario motivated by monotonic-compaction reasoning,
not a physical ceiling or rigorous uncertainty bound. The arithmetic midpoint
still has no evidentiary support. The code, config, registry, CSV and JSON use the
closed basis tokens:

- `configured_seawater_density_conditional_low_scenario`
- `arithmetic_midpoint_of_low_and_high_no_evidentiary_support`
- `own_well_measured_p05_illustrative_upper_scenario`

### 2.4 Configuration and scalar inputs now fail closed

- `schema_version` must equal `7.0.1` exactly.
- The four eligibility status codes and their order are closed.
- `min_eligible_samples_for_increment` must be a genuine integer; booleans,
  strings, floats and nulls are rejected rather than coerced or truncated.
- `not_implemented` entries must be unique, non-empty strings.
- Scenario-basis tokens are exact closed values.
- The stress scalar helpers reject booleans, strings, bytes, complex values and
  containers instead of passing them through `float()`.

### 2.5 Seabed wording corrected

Only Boreas 1 and Poseidon 2 have approved formation-top files and resolved
seabeds. Poseidon North 1 and Proteus 1ST2 have unresolved seabed, water-column
and shallow-gap thicknesses. The current README and notebook no longer say that
every well's density log begins a quantified distance below its own seabed.

## 3. Real-data non-regression

The confirmed defect is real but is not exercised by the approved Increment 7
run: short-gap bridging is enabled, and Boreas 1's bridged short gap lies below an
earlier unresolved long gap. Therefore no published scientific value changes.

Of the 13 files under `outputs/07_density_overburden/`, ten are byte-identical to
Increment 7.0.0, including all four PNG figures. Exactly three assurance records
change:

1. `overburden_eligibility_summary.csv` adds
   `n_unresolved_internal_gaps`; every pre-existing field and row is identical.
2. `shallow_column_scenarios.csv` changes only the assumed-density basis tokens
   and limitation wording; every numeric value and all other fields are identical.
3. `density_overburden_manifest.json` changes only ten paths: one assumption
   statement, `config_schema_version`, four per-well internal-gap counts, and the
   low/high basis tokens for Boreas 1 and Poseidon 2.

The measured increments remain 19.9325 MPa (Boreas 1), 30.6159 MPa (Poseidon 2),
28.3422 MPa (Poseidon North 1), and 8.2718 MPa (Proteus 1ST2). No well is promoted
to absolute overburden support.

## 4. Tests and notebook

- Full suite: **1,182 collected / 1,182 passed**.
- Locked pre–Increment 7 subset: **944 passed**.
- Increment 7/7.0.1 subset: **238 passed**.
- New regression cases in this patch: **22** (21 initially added plus one exact
  schema-version closure case).
- Notebook: 86 cells, 86 unique IDs, zero saved outputs,
  `nbformat.validate()` passes, and all 17 `%%writefile` bodies are byte-identical
  to their packaged targets.
- The notebook completion gate now declares 38 checks (35 retained plus 3 new), including a live
  synthetic unresolved-short-gap integration regression and explicit checks for
  the new internal-gap invariant and scenario basis vocabulary.

This environment did not contain the private raw project inputs, so the notebook's
real-data cells and completion gate were not re-executed here. No Colab execution
is claimed for this corrective patch. The existing real-data artifacts were
instead checked structurally, policy-validated, and compared field-for-field
against the verified 7.0.0 outputs as described in Section 3.

## 5. Package delta

Against Increment 7.0.0, the final package has 15 changed files, 3 added files,
and 0 removed files.

Changed:

1. `07_Density_QC_and_Overburden_Stress_Framework.ipynb`
2. `README.md`
3. `config/overburden_stress.yml`
4. `outputs/07_density_overburden/density_overburden_manifest.json`
5. `outputs/07_density_overburden/overburden_eligibility_summary.csv`
6. `outputs/07_density_overburden/shallow_column_scenarios.csv`
7. `p2mem/__init__.py`
8. `p2mem/density_qc.py`
9. `p2mem/io/overburden_inventory.py`
10. `p2mem/io/overburden_registry.py`
11. `p2mem/overburden.py`
12. `p2mem/overburden_models.py`
13. `pyproject.toml`
14. `tests/test_density_qc.py`
15. `tests/test_overburden.py`

Added:

1. `INCREMENT_07_0_1_MANIFEST.md`
2. `INCREMENT_07_0_1_COMPLETION_RECORD.md`
3. `INCREMENT_07_0_1_SHA256SUMS.txt`

The first 14 locked baseline test files remain byte-identical to Increment 6.1.7.
No private raw LAS, deviation, checkshot, or formation-top file is packaged.

## 6. Stop condition

Increment 7.0.1 stops here. Increment 8 has not been started.
