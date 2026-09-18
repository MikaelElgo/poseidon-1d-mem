# INCREMENT 7 COMPLETION RECORD

**Package:** `p2mem 0.7.0`
**Title:** Density QC, Density-Coverage Qualification, and the Vertical Overburden-Stress Framework
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational
**Baseline:** Increment 6.1.7 (`p2mem 0.6.8`), LOCKED
**Baseline ZIP SHA-256 verified:** `02b9c07ee65004d335066554c076f1be1ccd68924ba95721b0193c68a55baf37`

---

## 1. Completion gate — 35 of 35 conditions PASSED

Every condition below was printed by the live gate in the delivered notebook, executed to
completion from a fresh working directory.

| # | condition | result |
| ---: | --- | --- |
| 1 | Complete combined test suite passed with zero failures | **PASS** |
| 2 | Locked Increment 1–6.1.7 test subset passes in isolation | **PASS** |
| 3 | All 4 approved LAS files loaded (0 failures) | **PASS** |
| 4 | All 4 approved deviation surveys loaded (0 failures) | **PASS** |
| 5 | All 4 well frames assembled (0 failures) | **PASS** |
| 6 | ZERO samples extrapolated in any well | **PASS** |
| 7 | Depth SIGN CONVENTION verified against every frame's own arrays | **PASS** |
| 8 | Integration performed in TVDSS, never in measured depth | **PASS** |
| 9 | All 12 explicit density masks built for every well | **PASS** |
| 10 | `below_seabed` mask is NOT DETERMINABLE where no approved tops exist | **PASS** |
| 11 | Original resolved RHOB arrays are unmodified and read-only | **PASS** |
| 12 | Conditioned density lives in a SEPARATELY NAMED array with its own mask | **PASS** |
| 13 | No shallow or terminal gap was bridged, at any threshold | **PASS** |
| 14 | No long internal gap was bridged | **PASS** |
| 15 | Gap counts and sample counts satisfy the constructor invariants | **PASS** |
| 16 | Every eligibility status is one of the four declared codes | **PASS** |
| 17 | Every limiting reason is an enumerated code, sorted and deduplicated | **PASS** |
| 18 | Status derivation contains NO well name anywhere in code or config | **PASS** |
| 19 | Gap-threshold sensitivity reported for every well at every threshold | **PASS** |
| 20 | Scenarios published ONLY where the unmeasured thickness is quantifiable | **PASS** |
| 21 | Every scenario discloses its assumed fraction and separates the components | **PASS** |
| 22 | No absolute σv is claimed for a well whose shallow column is unmeasured | **PASS** |
| 23 | Every emitted output string field is classified (0 unclassified) | **PASS** |
| 24 | Every emitted controlled field is authorized (0 unauthorized, 0 kind mismatch) | **PASS** |
| 25 | Exact artifact schemas pass before AND after serialization | **PASS** |
| 26 | Every typed field and row survives serialization unchanged | **PASS** |
| 27 | Missing, unknown, reordered, empty and type-mutated fields fail closed | **PASS** |
| 28 | Writer mutation, row reordering, omission and failure are failure-atomic | **PASS** |
| 29 | A stale undeclared artifact in the destination is refused | **PASS** |
| 30 | ZERO named lithology assigned (DERIVED from the emitted records) | **PASS** |
| 31 | No absolute path leaks into any emitted artifact | **PASS** |
| 32 | 9 deterministic output artifacts declared and present | **PASS** |
| 33 | 4 QC figures present | **PASS** |
| 34 | Regeneration from an independent second root is byte-identical | **PASS** |
| 35 | Increment 8 is NOT started (no later-phase module is importable) | **PASS** |

**35 / 35 passed.**

---

## 2. Test counts — observed, not expected

| suite | collected | passed | failed |
| --- | ---: | ---: | ---: |
| Complete combined suite (`pytest tests`) | 1,160 | **1,160** | **0** |
| Locked Increment 1–6.1.7 subset, in isolation | 944 | **944** | **0** |
| `tests/test_density_qc.py` | 67 | 67 | 0 |
| `tests/test_overburden.py` | 78 | 78 | 0 |
| `tests/test_overburden_policy.py` | 41 | 41 | 0 |
| `tests/test_overburden_inventory.py` | 30 | 30 | 0 |
| **New in Increment 7** | **216** | **216** | **0** |

---

## 3. Notebook

| property | value |
| --- | --- |
| filename | `07_Density_QC_and_Overburden_Stress_Framework.ipynb` |
| total cells | **86** |
| unique cell IDs | **86 / 86** |
| saved outputs in the delivered notebook | **0** |
| `execution_count` values set | **0** |
| `nbformat.validate()` | **PASS** |
| nbformat version | 4.5 |
| `%%writefile` cells | **17** |
| `%%writefile` byte parity against packaged files | **17 / 17 exact** |
| fresh-directory execution | **completed, gate 35/35** |
| line endings | LF, matching every prior increment |

---

## 4. File delta against Increment 6.1.7

```
BASELINE files : 193
INCREMENT 7    : 221        (before this record, its manifest and its ledger)
  identical    : 190
  changed      :   3
  added        :  28
  removed      :   0
  total path differences: 31
```

**Changed (3):** `pyproject.toml`, `p2mem/__init__.py`, `README.md` — exactly the
expected set; version and narrative only.

**Added (28):** 1 notebook, 1 configuration file, 7 package modules, 6 test modules,
9 output artifacts, 4 figures. Each is listed individually in
`INCREMENT_07_MANIFEST.md` §5. No output directory is collapsed into a single item.

**Removed (0).**

Independently cross-checked against two packaged ledgers:

- `INCREMENT_06_1_7_SHA256SUMS.txt` — 189 identical, 3 changed, 0 missing (192 entries).
- `INCREMENT_05_1_2_SHA256SUMS.txt` — 146 identical, 3 changed, 0 missing (149 entries).

---

## 5. Real-data findings, per well

| well | RHOB present | finite | screening failures | depth-mapped | eligible | unmeasured shallow column | derived status | measured increment |
| --- | :-: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Boreas 1 | yes | 7,693 | **0** | 32,845 / 32,845 | 7,693 | **3,486.54 m TVD** | `screening_sensitivity_only` | **19.9325 MPa** |
| Poseidon 2 | yes | 7,946 | **0** | 31,897 / 31,897 | 7,946 | **3,567.14 m TVD** | `screening_sensitivity_only` | **30.6159 MPa** |
| Poseidon North 1 | yes | 7,543 | **0** | 31,310 / 31,310 | 7,543 | *not quantifiable — no seabed datum* | `partial_measured_increment_only` | **28.3422 MPa** |
| Proteus 1ST2 | yes | 2,113 | **0** | 31,235 / 31,235 | 2,113 | *not quantifiable — no seabed datum* | `partial_measured_increment_only` | **8.2718 MPa** |

**Wells supporting an absolute overburden curve: 0 of 4.**
**Wells supporting a screening sensitivity bracket: 2 of 4** (Boreas 1, Poseidon 2).
**Wells supporting a partial measured increment only: 2 of 4** (Poseidon North 1,
Proteus 1ST2).
**Wells not eligible: 0 of 4.**

### Gap conditioning

| well | short gaps bridged | samples bridged | bridged ΔTVD | long gaps (not bridged) | long ΔTVD |
| --- | ---: | ---: | ---: | ---: | ---: |
| Boreas 1 | **1** | **46** | 7.1224 m | **1** | 15.6441 m |
| Poseidon 2 | 0 | 0 | 0 m | 0 | 0 m |
| Poseidon North 1 | 0 | 0 | 0 m | 0 | 0 m |
| Proteus 1ST2 | 0 | 0 | 0 m | 0 | 0 m |

No shallow gap and no terminal gap was bridged in any well, at any threshold tested.
Boreas 1's integrable column is truncated at its long gap; **2,511 eligible samples below
it are excluded rather than integrated across unknown density**, and the bridged gap —
lying below that truncation — contributes exactly 0.000000 MPa.

### Scenario brackets (SCENARIOS, not results)

| well | low (MPa) | base (MPa) | high (MPa) | width (MPa) | factor | assumed fraction |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Boreas 1 | 59.923 | 83.303 | 106.683 | 46.760 | 1.780 | 66.74 % – 81.32 % |
| Poseidon 2 | 71.464 | 96.132 | 120.800 | 49.336 | 1.690 | 57.16 % – 74.66 % |

The ±5 kg/m³ seawater bracket moves each total by 0.048–0.049 MPa — three orders of
magnitude below the shallow-sediment assumption.

---

## 6. Output-policy metrics, from the actual export

| metric | value |
| --- | ---: |
| declared artifacts | **9** |
| string field occurrences inspected | **3,486** |
| controlled occurrences | 1,636 |
| structural occurrences | 1,786 |
| occurrences outside the guarantee | 64 |
| schema violations (pre / post) | **0 / 0** |
| unclassified fields (pre / post) | **0 / 0** |
| unauthorized controlled fields (pre / post) | **0 / 0** |
| field-kind mismatches (pre / post) | **0 / 0** |
| distinct registered statements used | 22 |
| distinct controlled templates used | 2 |
| distinct typed labels used | 17 |
| `named_lithology_assigned` (DERIVED) | **false** |
| lithology-validation violations | **0** |

---

## 7. Scope boundary

Increment 7 implements **no** pore-pressure prediction, sonic or resistivity NCT fitting,
Eaton, Bowers, equivalent-depth or drilling-exponent method, effective-stress calculation,
dynamic or static elastic-property modelling, rock-strength modelling, horizontal-stress
calculation, stress calibration, mud-window calculation, breakout, tensile-fracture or
wellbore-stability analysis, named lithology assignment, or mineralogical interpretation.

Verified live: no `p2mem.pore_pressure`, `p2mem.effective_stress`, `p2mem.eaton`,
`p2mem.bowers`, `p2mem.nct`, `p2mem.elastic`, `p2mem.rock_strength`,
`p2mem.horizontal_stress`, `p2mem.mud_window` or `p2mem.wellbore_stability` module is
importable.

**Increment 8 has NOT been started.**

---

## 8. Honest reporting

- Nothing in this increment is calibrated, and no result may be described as calibrated
  truth.
- **No absolute vertical overburden-stress curve is published for any well**, because the
  measured density coverage does not support one.
- Every reported stress separates its measured, conditioned and assumed contributions,
  and no total is reported while any component is unresolved.
- The delivered notebook was executed with nbclient + ipykernel on CPython 3.12.10,
  Windows 11 — **not** in Google Colab. No Colab execution is claimed.
