# Increment 7.0.1 Completion Record

**Project:** Poseidon 2 — 1D Mechanical Earth Model (Tier C — Screening-Level /
Uncalibrated Educational)

**Package version:** `p2mem 0.7.1`

**Baseline:** `Poseidon_1D_MEM_Increment_07.zip`, SHA-256
`29ac378168987ab8cd7dd902c1d7bd654c206a80799c86b1de5c78a73d15aad4`,
independently re-hashed before modification.

## Outcome

Increment 7.0.1 corrects one genuine fail-open numerical defect and four related
validation/documentation weaknesses:

- Every unresolved internal gap now truncates the vertical-stress integral. A
  short unresolved gap or missing-depth-mapping gap can no longer be crossed by
  a trapezoid merely because it was not classified as `long_internal_gap`.
- Eligibility exports and constructors now track all unresolved internal gaps,
  not only long gaps.
- The invalid endpoint-only bridge-error “bound” is withdrawn; 10 m is explicitly
  a sensitivity-tested heuristic.
- Shallow-column low/high values are explicitly conditional and illustrative
  scenarios, not a physical floor/ceiling or rigorous uncertainty interval.
- Configuration vocabularies, integer counts, schema version, and stress scalar
  inputs fail closed without silent coercion.
- Current README/notebook wording correctly distinguishes the two wells with
  resolved seabeds from the two whose seabed is not determinable.

## Verification observed

- Full test suite: **1,182 passed, 0 failed**.
- Locked pre–Increment 7 subset: **944 passed**.
- Increment 7/7.0.1 subset: **238 passed**.
- Direct analytical regression: the unresolved short-gap case returns exactly
  **176,519.7 Pa**, truncates before the gap, and excludes the eight eligible
  samples below it.
- Notebook: **86 cells**, **86 unique IDs**, zero saved outputs,
  `nbformat.validate()` passes, **17/17 `%%writefile` parity**.
- Outputs: **10/13 byte-identical** to 7.0.0, including all four figures. The
  three changed assurance records preserve every scientific numeric value.
- Package delta: **15 changed, 3 added, 0 removed**.
- No Increment 8 module or result was added.

The notebook was not executed against private real inputs in this environment,
because those inputs are intentionally absent from the package. No Colab run is
claimed. This limitation is explicit rather than replaced by a simulated claim.

The final ZIP SHA-256 is computed after packaging and reported alongside the
delivered file. It is intentionally not embedded here: a file contained inside
an archive cannot truthfully contain the final hash of that same archive without
creating a circular self-reference.

## Scientific non-regression

The approved real-data run does not exercise the corrected short-unresolved-gap
path. All measured increments, status assignments, sensitivity values, density
coverage statistics, gap statistics and four figures remain unchanged. The
three output differences are limited to the new internal-gap count and corrected
assumption wording/tokens.

## Stop condition

Increment 7.0.1 is complete. Increment 8 has **not** been started.
