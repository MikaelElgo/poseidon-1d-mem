# Increment 7.0.4 Manifest — Final End-to-End Corrective Patch

## 1. Identity and approved scope

- **Project:** Poseidon 2 — 1D Mechanical Earth Model
- **Package version:** `p2mem 0.7.4`
- **Direct baseline:** `Poseidon_1D_MEM_Increment_07_v7.0.3.zip`
- **Verified baseline SHA-256:** `c9e06c89ce21eead1a8b571667ee0b773f70a7ea35761ab8bdb0b8233d2e756f`
- **Patch scope:** five end-to-end correctness and assurance findings only
- **Configuration schema:** remains `7.0.1`; no configured scientific value changed
- **Increment 8:** not started

The baseline archive was re-hashed before modification, all 233 archive paths were
checked, its 232 ledger-covered files were re-verified, and its complete test suite was
run before any corrective change. The locked 944-test pre-Increment-7 subset remains
byte-identical.

This patch changes no private input, density sample, depth mapping, validity mask,
approved threshold, gap disposition, stress equation, eligibility status, measured
stress increment, scenario total, or figure. It corrects the population provenance of
one scenario endpoint, closes public threshold validation, makes stress fractions
exhaustive, makes locked seabed ingestion fail closed, and makes JSON bytes independent
of the host newline convention.

## 2. Findings reproduced before correction

### 2.1 High-scenario population mismatch

The high shallow-column scenario was described as using density eligible for measured
integration but consumed `rhob_p05_kg_m3`, calculated across every finite RHOB sample.
A synthetic case with an ineligible finite value reproduced the mismatch: all-finite P05
was 1100 kg/m3 while eligible-population P05 was 2400 kg/m3, and the old scenario used
1100 kg/m3.

`DensityQcStats` now carries the separately named
`rhob_eligible_p05_kg_m3`, computed only where
`eligible_for_measured_integration` is true. The high scenario consumes that field. The
all-finite P05 remains exported as factual QC and is explicitly stated not to drive the
scenario. Constructor invariants require finite-population statistics exactly when
finite samples exist and eligible P05 exactly when eligible samples exist.

### 2.2 Invalid public gap-threshold overrides

The two public per-call threshold entry points accepted values through `float(...)`.
Booleans, numeric strings, NaN, positive/negative infinity and negative values could
therefore be accepted; positive infinity could reclassify and bridge a gap of arbitrary
length. Both public functions now accept only finite, non-negative real numeric scalars,
explicitly reject booleans, strings, bytes and complex values, and raise the typed
`OverburdenInputError`.

Every result record that carries a threshold now enforces the same finite/non-negative
contract. Boolean control flags are exact booleans. Thickness fields added to the
sensitivity record's invariant set are also finite and non-negative.

### 2.3 Incomplete scenario fractions

The scenario record exposed assumed and measured fractions but omitted the contribution
from explicitly bridged density. Where a bridged contribution was non-zero, the two
published fractions did not sum to one. Every scenario now carries three disjoint
fractions:

1. configured column assumptions: water plus unresolved shallow column;
2. conditioned density: explicitly bridged internal gaps; and
3. strictly measured density: the measured stress after removal of the bridged part.

All three values must be finite and lie in `[0, 1]`; their sum must equal one within
`1e-12`. Both CSV and JSON schemas export the three components, and the controlled
scenario prose reports all three percentages.

### 2.4 Locked seabed reader failed open

The previous reader returned an empty mapping for a missing table and silently skipped a
malformed matching row; a later matching row could overwrite an earlier one. The reader
now raises `SeabedMarkerError`, a typed `OverburdenInputError`, when the locked file is
missing or not a file, required headers are absent or duplicated, or a matching row is
malformed, non-finite, negative, empty-keyed or duplicated for one well. A valid
header-only table still returns an explicit empty mapping, preserving the factual
`NOT_AVAILABLE` representation.

During implementation, an additional exact `MDRT == TVD` invariant was tried and rejected
before release. It incorrectly rejected the locked Boreas 1 survey-corrected seabed
because its values differ by only 0.0000114393325 m from interpolation precision. The
unrequested exact-equality rule was removed, and a regression test preserves the locked
values without weakening the five approved corrections.

### 2.5 Platform-dependent JSON newlines

The default JSON writer used a text-mode convenience method whose newline translation
depends on the host platform. It now serializes the deterministic JSON string, appends
one newline, encodes explicit UTF-8, and writes bytes. The artifact contains LF only,
including when the text-writing method is monkeypatched to emulate a Windows path.

## 3. Test and notebook evidence

- **Combined suite:** 1,368 collected / 1,368 passed, zero failures, errors or skips.
- **Locked subset:** 944 / 944 passed from 14 byte-identical pre-Increment-7 test files.
- **Increment 7 tests:** 424 total: 244 density-QC, 98 overburden, 44 output-policy,
  and 38 inventory/workflow tests.
- **New regression cases:** 52 relative to the 1,316-test direct baseline.
- **Notebook:** 86 cells (41 code, 45 markdown), 86 unique IDs, zero saved outputs,
  valid notebook structure, and 17/17 `%%writefile` bodies byte-identical to their
  packaged targets.
- **Execution-semantics run:** 22 ordinary code cells executed in order; all 17
  `%%writefile` cells were applied with the notebook's exact LF bodies; two install cells
  were skipped only because the same declared dependencies were already installed.
- **Completion gate:** 44/44 live checks printed `[PASS]`.

The notebook execution loaded all four approved LAS files and all four deviation
surveys, assembled all four well frames, ran both the complete and locked test suites,
performed the real-data workflow, wrote all artifacts, produced all four figures, and
regenerated the nine deterministic artifacts from an independent second root.

## 4. Real-data non-regression and scientific results

The finite and eligible RHOB populations coincide in every approved well, so correcting
the P05 population changes no real-data endpoint:

| Well | Finite / eligible samples | All-finite P05 | Eligible P05 | Status | Measured increment |
|---|---:|---:|---:|---|---:|
| Boreas 1 | 7,693 / 7,693 | 2392.6000 kg/m3 | 2392.6000 kg/m3 | `screening_sensitivity_only` | 19.932529 MPa |
| Poseidon 2 | 7,946 / 7,946 | 2435.3250 kg/m3 | 2435.3250 kg/m3 | `screening_sensitivity_only` | 30.615932 MPa |
| Poseidon North 1 | 7,543 / 7,543 | 2439.4000 kg/m3 | 2439.4000 kg/m3 | `partial_measured_increment_only` | 28.342232 MPa |
| Proteus 1ST2 | 2,113 / 2,113 | 2337.7000 kg/m3 | 2337.7000 kg/m3 | `partial_measured_increment_only` | 8.271841 MPa |

The two wells with published shallow-column scenarios have zero bridged stress in those
scenarios, so their new conditioned fraction is exactly zero and all previous totals and
assumed/measured fractions are preserved. The other two wells remain ineligible for
shallow-column scenarios because their seabed datum is not determinable. No approved well
supports an absolute vertical-stress curve.

All previously reported coverage, gap and sensitivity findings remain unchanged,
including Boreas 1's 7.12 m bridged gap, 15.64 m unresolved gap, truncation before 2,511
deeper eligible samples, and unchanged 10 m approved threshold.

## 5. Output delta

There are 13 Increment 7 outputs: nine deterministic CSV/JSON artifacts and four PNG
figures. Exactly 10/13 are byte-identical to 7.0.3. The four figures and six deterministic
artifacts are unchanged. Three assurance-bearing artifacts change:

1. `density_qc_summary.csv` adds `rhob_eligible_p05_kg_m3`.
2. `shallow_column_scenarios.csv` adds `conditioned_fraction_of_total`; its controlled
   scenario basis now reports assumed, conditioned and measured percentages; its
   limitations text identifies eligible-population P05.
3. `density_overburden_manifest.json` adds eligible P05 for each well and conditioned
   plus measured fractions for each scenario, and is serialized as explicit UTF-8 LF.

No existing numeric result changes in any of the three files. All nine deterministic
artifacts regenerated byte-identically from two independent roots. PNG files are excluded
from the cross-environment byte-determinism claim because renderer versions can change
PNG encoding; the packaged PNGs themselves are byte-identical to the direct baseline.

## 6. Exact package delta from 7.0.3

Exactly **18 existing files changed**:

1. `07_Density_QC_and_Overburden_Stress_Framework.ipynb`
2. `README.md`
3. `outputs/07_density_overburden/density_overburden_manifest.json`
4. `outputs/07_density_overburden/density_qc_summary.csv`
5. `outputs/07_density_overburden/shallow_column_scenarios.csv`
6. `p2mem/__init__.py`
7. `p2mem/density_qc.py`
8. `p2mem/overburden.py`
9. `p2mem/overburden_models.py`
10. `p2mem/io/overburden_inventory.py`
11. `p2mem/io/overburden_policy.py`
12. `p2mem/io/overburden_registry.py`
13. `p2mem/io/overburden_workflow.py`
14. `pyproject.toml`
15. `tests/test_density_qc.py`
16. `tests/test_overburden.py`
17. `tests/test_overburden_inventory.py`
18. `tests/test_overburden_policy.py`

Exactly **3 files are added**:

1. `INCREMENT_07_0_4_COMPLETION_RECORD.md`
2. `INCREMENT_07_0_4_MANIFEST.md`
3. `INCREMENT_07_0_4_SHA256SUMS.txt`

No file is removed. Every other baseline file is byte-identical.

## 7. Assumptions, interpretations and unresolved limitations

This corrective patch introduces no new scientific assumption. Existing Increment 7
assumptions remain explicit: gravity 9.80665 m/s2, seawater density 1025 kg/m3 and its
1020-1030 kg/m3 sensitivity, the 1000-3500 kg/m3 screening band, the reviewable 10 m
gap-bridging heuristic, and conditional low/base/high shallow-column scenarios.

The monotonic-compaction argument motivating eligible-population P05 as an illustrative
high endpoint remains an interpretation, not a measured physical bound. The shallow
density column remains unresolved in every well; seabed depth remains unavailable for
Poseidon North 1 and Proteus 1ST2; Boreas 1's long internal gap and terminal columns
remain unresolved. No calibration data were added.

## 8. Verification boundary and stop condition

Verification covers archive safety, checksum integrity, source/test delta, full and
locked tests, notebook validity and source parity, faithful execution order, real-data
integration, deterministic artifact regeneration, exact output comparison, version,
private-data exclusion, build-path scans, and absence of later-phase modules.

This is still a screening-level, uncalibrated educational workflow. It is not suitable
for operational drilling or well design. Increment 8—pore pressure, effective stress,
elastic or strength modelling, horizontal stress, mud window and wellbore stability—has
not been started.

The final ZIP SHA-256 is reported externally with the delivered archive because embedding
an archive's own hash inside one of its members would be self-referential.
