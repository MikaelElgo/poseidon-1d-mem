# Increment 7.0.2 Completion Record — Assurance-Only Corrective Patch

**Baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.1.zip`, SHA-256
`ee8e8771a8a04726f396946d01783710cb1a56ab335e9ad1553809503144265b`,
recomputed and matched exactly before modification. **Version:** `p2mem 0.7.2`.
**Scope:** notebook completion-gate correctness and public configuration-constructor
validation only. **Increment 8 has not been started.**

## Corrected findings

1. The Increment 7.0.1 notebook gate looked up `assumption_basis`, while the declared and
   emitted field is `assumed_density_basis`. The defect was reproduced and would have
   raised `KeyError` in a real-data gate run. The lookup is corrected, tied to the actual
   schema by a regression test, and executed successfully over all 10 packaged scenario
   rows.
2. The public frozen `OverburdenConfig` constructor was weaker than the YAML loader, so
   direct construction and `dataclasses.replace()` could admit malformed values. It now
   rejects non-finite or ambiguously typed numbers, non-boolean flags, fractional/bool
   counts, malformed threshold/scenario/not-implemented tuples, the wrong schema version,
   and inconsistent numerical relationships. A valid `replace(...,
   bridge_short_internal_gaps=False)` remains supported.

## Verification results

- **1,306/1,306 tests passed**: 944 locked pre-Increment-7 tests plus 362 Increment 7
  tests. This patch adds 124 regression cases over the verified 1,182-test baseline.
- Notebook: 86 cells, 86 unique IDs, zero saved outputs, valid nbformat, 17/17
  `%%writefile` parity, and 39 declared gate checks.
- Package delta: 7 changed, 3 added, 0 removed; every other baseline file is
  byte-identical.
- Scientific outputs: **13/13 byte-identical** to Increment 7.0.1. No value, threshold,
  status, scenario, CSV/JSON result, or figure changed.
- Clean-room ZIP checks, checksum verification, offline editable install, full and
  partitioned test runs, notebook/schema checks, path/private-data scans, and locked
  baseline comparisons all passed.

The full real-data notebook was not re-executed because private raw project inputs are not
part of the package and were unavailable here; no Colab execution is claimed. The repaired
gate lookup itself was executed against the packaged real-data scenario rows, and the new
constructor check was executed through both direct probes and the test suite.

The final ZIP hash is reported externally with the delivered package because embedding a
ZIP's own hash inside one of its members would be self-referential.
