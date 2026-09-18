# INCREMENT 7 MANIFEST
## Density QC, Density-Coverage Qualification, and the Vertical Overburden-Stress Framework

**Package:** `p2mem 0.7.0`
**Project:** Poseidon 2 — 1D Mechanical Earth Model
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational
**Approved wells:** Poseidon 2, Boreas 1, Poseidon North 1, Proteus 1ST2
**Baseline:** Increment 6.1.7 (`p2mem 0.6.8`), verified and LOCKED
**Baseline ZIP SHA-256:** `02b9c07ee65004d335066554c076f1be1ccd68924ba95721b0193c68a55baf37` — **verified**
**Baseline suite re-run before any change:** **944 passed, 0 failed**
**Baseline checksum ledger re-verified:** `INCREMENT_06_1_7_SHA256SUMS.txt`, **192/192 files identical, 0 failures**

---

## 0. The headline result, stated first

**No approved well supports an absolute vertical overburden-stress curve.**

This is a *measured* conclusion, not a caution. All four wells carry a
contract-resolved `RHOB_kg_m3` curve; all four are 100% depth-mapped with zero
extrapolated samples; and **not one finite density value in any well falls outside the
configured 1000–3500 kg/m³ screening band.** The density data are, within their own
logged intervals, in excellent condition.

The problem is entirely one of *where* those intervals are. Every log begins kilometres
below its own seabed:

| well | seabed datum | first eligible RHOB (TVD) | UNMEASURED shallow column |
| --- | --- | --- | --- |
| Boreas 1 | 513.70 m MDRT (locked Increment 5) | 4,000.24 m | **3,486.54 m TVD** |
| Poseidon 2 | 518.40 m MDRT (locked Increment 5) | 4,085.54 m | **3,567.14 m TVD** |
| Poseidon North 1 | **not determinable** (no approved tops) | 3,781.41 m | not quantifiable |
| Proteus 1ST2 | **not determinable** (no approved tops) | 4,919.00 m | not quantifiable |

`σv(z) = ∫ρ(z)g dz` is an *absolute* stress only when the density column is known from
the datum or seabed to the evaluation depth. No amount of coverage *inside* the logged
interval can supply the 3.5 km above it, and this project holds no calibration — no core
density, no shallow-density control, no measured seawater density, no local gravity
survey — from which to model it.

Increment 7 therefore reports a **partial measured increment** for every well, and a
**transparent low/base/high screening bracket** for the two wells whose missing thickness
is at least *quantifiable*. It publishes no single absolute σv curve, and it fills nothing.

---

## 1. Scope

### Implemented

1. RHOB/bulk-density availability and coverage inventory.
2. Density-unit and source-provenance confirmation.
3. Density QC with twelve explicit, separately auditable validity masks.
4. Density-gap classification and interval qualification.
5. Measured-density vertical-stress increments, integrated in true vertical depth.
6. An auditable framework for total vertical overburden stress, with every contribution
   partitioned into measured, conditioned and assumed components.
7. Sensitivity and uncertainty reporting where the shallow density column is unmeasured.
8. Method-eligibility classification for future pore-pressure work.

### Deliberately NOT implemented

Pore-pressure prediction; sonic or resistivity NCT fitting; Eaton, Bowers,
equivalent-depth and drilling-exponent methods; effective-stress calculation; dynamic or
static elastic-property modelling; rock-strength modelling; horizontal-stress
calculation; stress calibration; mud-window calculation; breakout, tensile-fracture and
wellbore-stability analysis; named lithology assignment; mineralogical interpretation.
Each is enumerated in `config/overburden_stress.yml` under `not_implemented` and in the
emitted manifest's `methods_not_implemented`, so its absence is a recorded decision
rather than an omission. **Increment 8 has not been started.**

---

## 2. Mandatory pre-implementation real-data investigation

Measured independently, before any density treatment was selected. Nothing below is
hardcoded, and none of it is asserted from a prior increment.

| quantity | Boreas 1 | Poseidon 2 | Poseidon North 1 | Proteus 1ST2 |
| --- | ---: | ---: | ---: | ---: |
| total LAS samples | 32,845 | 31,897 | 31,310 | 31,235 |
| finite RHOB | 7,693 | 7,946 | 7,543 | 2,113 |
| non-finite RHOB | 25,152 | 23,951 | 23,767 | 29,122 |
| non-positive RHOB | 0 | 0 | 0 | 0 |
| below screening min (1000 kg/m³) | 0 | 0 | 0 | 0 |
| above screening max (3500 kg/m³) | 0 | 0 | 0 | 0 |
| **screening-bound failures** | **0** | **0** | **0** | **0** |
| eligible for integration | 7,693 | 7,946 | 7,543 | 2,113 |
| depth-mapped / unmapped | 32,845 / 0 | 31,897 / 0 | 31,310 / 0 | 31,235 / 0 |
| samples outside survey coverage | 0 | 0 | 0 | 0 |
| samples extrapolated | 0 | 0 | 0 | 0 |
| first valid RHOB MD (m) | 4,000.5513 | 4,086.0305 | 3,782.0093 | 4,922.0542 |
| last valid RHOB MD (m) | 5,195.3672 | 5,296.8486 | 4,931.4102 | 5,243.9229 |
| first valid TVD (m) | 4,000.2436 | 4,085.5425 | 3,781.4089 | 4,919.0011 |
| last valid TVD (m) | 5,191.5119 | 5,294.5447 | 4,929.9108 | 5,239.4181 |
| first valid TVDSS (m) | 3,978.4436 | 4,063.7425 | 3,759.4089 | 4,897.2011 |
| last valid TVDSS (m) | 5,169.7119 | 5,272.7447 | 4,907.9108 | 5,217.6181 |
| gross coverage MD (m) | 1,194.8159 | 1,210.8181 | 1,149.4009 | 321.8687 |
| gross coverage TVD (m) | 1,191.2683 | 1,209.0022 | 1,148.5018 | 320.4170 |
| median MD step (m) | 0.15240 | 0.15240 | 0.15240 | 0.15240 |
| internal gap count | **2** | 0 | 0 | 0 |
| internal gap samples | 148 | 0 | 0 | 0 |
| seabed → first valid RHOB (TVD, m) | **3,486.5436** | **3,567.1424** | *not determinable* | *not determinable* |
| last valid → well bottom (TVD, m) | 9.9190 | 53.9356 | 347.3526 | 5.6138 |
| deviation-survey coverage | full | full | full | full |
| **absolute σv computable without an unmeasured shallow column?** | **NO** | **NO** | **NO** | **NO** |

Recorded density statistics (finite samples, as recorded, no correction applied):

| well | min | p05 | median | p95 | max | headroom to the 3500 bound |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Boreas 1 | 1681.90 | 2392.60 | 2559.50 | 2703.24 | 3020.30 | 479.70 |
| Poseidon 2 | 1527.20 | 2435.32 | 2580.90 | 2736.58 | 3114.30 | 385.70 |
| Poseidon North 1 | 1950.40 | 2439.40 | 2500.40 | 2647.89 | **3497.90** | **2.10** |
| Proteus 1ST2 | 2187.80 | 2337.70 | 2682.20 | 2816.36 | 3020.50 | 479.50 |

**Poseidon North 1's maximum recorded density sits 2.10 kg/m³ below the configured upper
screening bound.** The band admits that sample; a small change to the bound would not.
This is raised as an INFO issue (`MEASURED_MAXIMUM_NEAR_SCREENING_BOUND`) rather than
absorbed silently, because a screening bound that is nearly decisive should be visible.

**Boreas 1 was evaluated on density evidence alone.** The Increment 6 ECGR scale anomaly
is a gamma-ray finding and plays no part here; Boreas 1's density is fully eligible.

---

## 3. Scientific decisions, and why

### 3.1 Screening plausibility band: 1000–3500 kg/m³, inclusive

A **screening criterion**, not a geological limit. The lower bound is the density of
fresh water: a fully water-saturated porous medium cannot have a lower bulk density than
its own pore fluid, so a recorded value below it is a tool, hole-condition or processing
artefact. It requires no assumption about porosity, salinity or grain density. The upper
bound is above any common sedimentary mineral assemblage at any porosity and exists to
catch gross processing spikes; it is **not** a claim that a value just below it is
reasonable. Both bounds are **inclusive**, stated explicitly because an
inclusive/exclusive slip at a boundary is a silent scientific change, and tested at the
exact bound values and at `nextafter` on either side.

### 3.2 Gap-conditioning threshold: 10.0 m TVD

Expressed in **true vertical depth** — not a sample count (which would mean different
things in different logging runs) and not measured depth (which would mean different
things in a deviated well).

The choice is justified by a *bounded error*, not by convention. Bridging a gap of
thickness *h* with a linear density ramp instead of the true density introduces at most
`0.5·|Δρ|·h·g`. For the largest density contrast observed anywhere in these four wells
(order 1000 kg/m³) and *h* = 10 m, that bound is under 0.05 MPa against measured column
increments of 8–31 MPa. The **actual** bridged contribution is exported separately for
every well, so no reader has to take that bound on trust.

The full sensitivity (0 / 2 / 5 / 10 / 20 / 30 m TVD) is re-run end to end — conditioning,
integration and status derivation — and exported, so the effect of the approved choice is
visible rather than assumed.

### 3.3 The shallow-column bracket, justified without a lithology and without a trend

- **low** = the configured seawater density (1025 kg/m³). A physical floor: a saturated
  sediment column cannot have a lower depth-averaged bulk density than the pore fluid
  filling it. It assumes nothing about the sediment.
- **high** = the *same well's own* measured 5th-percentile eligible density, used as a
  **ceiling** because the unresolved column lies entirely *above* the measured one and
  mechanical compaction is monotonic with effective stress. This is a **bounding**
  argument. **No depth-dependent density function is constructed anywhere in this
  project.**
- **base** = the arithmetic midpoint. It has **no evidentiary support whatsoever** and
  exists only so the bracket has a labelled centre. `base_is_not_a_best_estimate: true` is
  enforced at configuration load.

The bracket is deliberately wide. A wide honest bracket is the correct reporting of a
3.5 km unmeasured column; a narrow one would require a calibrated shallow-density model
this project does not have.

### 3.4 Depth sign convention — verified, not assumed

The locked `p2mem.depth_mapping` documents and independently tests: TVD is zero at the
well datum and increases **downward**; datum elevation is referenced to MSL, positive
**upward**; `TVDSS = TVD − datum_elevation`, positive **downward** from MSL.

`verify_depth_sign_convention` re-derives this at run time from each well frame's own
arrays — TVD must increase with MD, `TVDSS` must equal `TVD − datum_elevation` to
tolerance, and `dTVD` must equal `dTVDSS` exactly — and raises rather than proceeding.
Measured on the real data: `max|TVD − TVDSS − datum|` ≤ 3.553×10⁻¹⁴ m and
`max|dTVD − dTVDSS|` = 0 for all four wells; minimum TVD increment 0.150186 m (Boreas 1),
0.151723 m (Poseidon 2), 0.151811 m (Poseidon North 1), 0.150810 m (Proteus 1ST2) — all
strictly positive. **Nothing in this increment reads a sign from a variable name.**

### 3.5 Why the FIRST integrable segment, not the longest

Vertical stress accumulates downward, so a segment is useful only if it can be tied to
the column above it. The segment beginning at the **shallowest** eligible sample is the
only one that could ever connect to the shallow column and therefore to an absolute
stress; a deeper segment below an unresolved gap is stress-disconnected from everything
above it. Selecting the longest segment would report a larger number that is no more
connectable — exactly the flattering-but-useless result this increment exists to avoid.

---

## 4. Measured results

### 4.1 Gap inventory and conditioning (approved threshold 10.0 m TVD)

| well | class | n samples | ΔMD (m) | ΔTVD (m) | disposition |
| --- | --- | ---: | ---: | ---: | --- |
| Boreas 1 | shallow seabed→first valid | 22,879 | — | 3,486.5436 | **unresolved, never bridged** |
| Boreas 1 | long internal | 102 | 15.6973 | **15.6441** | **unresolved, not bridged** |
| Boreas 1 | short internal | 46 | 7.1626 | 7.1224 | **bridged (linear in TVD)** |
| Boreas 1 | terminal | 66 | 10.0586 | 9.9190 | unresolved |
| Poseidon 2 | shallow seabed→first valid | 23,409 | — | 3,567.1424 | **unresolved, never bridged** |
| Poseidon 2 | terminal | 355 | 54.1021 | 53.9356 | unresolved |
| Poseidon North 1 | terminal | 2,284 | 348.0815 | 347.3526 | unresolved |
| Proteus 1ST2 | terminal | 37 | 5.6386 | 5.6138 | unresolved |

Bridged totals: Boreas 1 — 1 gap, 46 samples, 7.1626 m MD / 7.1224 m TVD. All other wells
— 0 gaps, 0 samples. Long-gap totals: Boreas 1 — 1 gap, 102 samples, 15.6441 m TVD. All
other wells — 0.

### 4.2 Measured vertical-stress increments and derived eligibility

| well | derived status | eligible samples | integrated TVDSS span (m) | measured increment | of which conditioned |
| --- | --- | ---: | --- | ---: | ---: |
| Boreas 1 | `screening_sensitivity_only` | 7,693 | 3,978.444 → 4,767.009 | **19.9325 MPa** | 0.000000 MPa |
| Poseidon 2 | `screening_sensitivity_only` | 7,946 | 4,063.742 → 5,272.745 | **30.6159 MPa** | 0.000000 MPa |
| Poseidon North 1 | `partial_measured_increment_only` | 7,543 | 3,759.409 → 4,907.911 | **28.3422 MPa** | 0.000000 MPa |
| Proteus 1ST2 | `partial_measured_increment_only` | 2,113 | 4,897.201 → 5,217.618 | **8.2718 MPa** | 0.000000 MPa |

**Boreas 1's integrable column is TRUNCATED at its long internal gap.** The gap sits at
4,790–4,806 m MD, above the well's bridged short gap, so the integrable column stops
there: **2,511 eligible samples below the gap are excluded rather than integrated across
unknown density**, and the bridged gap — although correctly bridged under the approved
threshold — lies below the truncation and therefore contributes exactly 0.000000 MPa to
the reported increment. Both facts are exported
(`column_truncated_at_unresolved_gap`, `n_eligible_samples_below_truncation`,
`bridged_increment_pa`).

Limiting reasons, as enumerated codes:

- **Boreas 1** — `internal_gap_exceeds_limit`, `shallow_density_column_unresolved`,
  `terminal_density_column_unresolved`
- **Poseidon 2** — `shallow_density_column_unresolved`,
  `terminal_density_column_unresolved`
- **Poseidon North 1** — `seabed_datum_unresolved`, `terminal_density_column_unresolved`
- **Proteus 1ST2** — `seabed_datum_unresolved`, `terminal_density_column_unresolved`

### 4.3 The shallow-column screening bracket — SCENARIOS, not results

Published only for the two wells whose unmeasured thickness is quantifiable. Bracketing
an interval of unknown thickness would be arithmetic without content, so Poseidon North 1
and Proteus 1ST2 receive **no** scenario.

| well | scenario | assumed shallow ρ (kg/m³) | water (MPa) | unresolved shallow (MPa) | measured (MPa) | **TOTAL (MPa)** | assumed fraction |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Boreas 1 | low | 1025.00 | 4.944 | 35.046 | 19.933 | **59.923** | **66.74%** |
| Boreas 1 | base | 1708.80 | 4.944 | 58.426 | 19.933 | **83.303** | **76.07%** |
| Boreas 1 | high | 2392.60 | 4.944 | 81.806 | 19.933 | **106.683** | **81.32%** |
| Boreas 1 | base, seawater 1020 | 1708.80 | 4.920 | 58.426 | 19.933 | 83.279 | 76.07% |
| Boreas 1 | base, seawater 1030 | 1708.80 | 4.969 | 58.426 | 19.933 | 83.327 | 76.08% |
| Poseidon 2 | low | 1025.00 | 4.992 | 35.856 | 30.616 | **71.464** | **57.16%** |
| Poseidon 2 | base | 1730.16 | 4.992 | 60.524 | 30.616 | **96.132** | **68.15%** |
| Poseidon 2 | high | 2435.32 | 4.992 | 85.192 | 30.616 | **120.800** | **74.66%** |
| Poseidon 2 | base, seawater 1020 | 1730.16 | 4.967 | 60.524 | 30.616 | 96.107 | 68.14% |
| Poseidon 2 | base, seawater 1030 | 1730.16 | 5.016 | 60.524 | 30.616 | 96.156 | 68.16% |

**Bracket widths:** Boreas 1 — 46.760 MPa (59.923 → 106.683, a factor of 1.780).
Poseidon 2 — 49.336 MPa (71.464 → 120.800, a factor of 1.690).

**Between 57% and 81% of every scenario total originates in assumed rather than measured
density.** The ±5 kg/m³ seawater bracket moves the total by 0.048–0.049 MPa — three
orders of magnitude less than the shallow-sediment assumption. The uncertainty is
dominated, overwhelmingly, by the unmeasured sediment column, and no seawater refinement
would change that.

**These rows are scenarios. Read the bracket, never a single row. The base case is an
arithmetic midpoint with no evidentiary support and is never a result.**

### 4.4 Gap-threshold sensitivity

Only Boreas 1 has any internal gap, so it is the only well whose result the threshold can
move.

| threshold (m TVD) | bridged gaps / samples | long gaps | usable samples | measured increment | derived status |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0.0 | 0 / 0 | 2 | 7,693 | 19.9325 MPa | `screening_sensitivity_only` |
| 2.0 | 0 / 0 | 2 | 7,693 | 19.9325 MPa | `screening_sensitivity_only` |
| 5.0 | 0 / 0 | 2 | 7,693 | 19.9325 MPa | `screening_sensitivity_only` |
| **10.0 (approved)** | **1 / 46** | **1** | **7,739** | **19.9325 MPa** | `screening_sensitivity_only` |
| 20.0 | 2 / 148 | 0 | 7,841 | **29.8397 MPa** | `screening_sensitivity_only` |
| 30.0 | 2 / 148 | 0 | 7,841 | 29.8397 MPa | `screening_sensitivity_only` |

The approved 10 m threshold changes Boreas 1's reported increment by **nothing at all**
(19.9325 MPa at every threshold from 0 to 10 m), because the gap it bridges lies below
the truncation caused by the gap it does not bridge. A 20 m threshold would bridge the
15.64 m gap as well, restore the whole column, and raise the increment to 29.8397 MPa —
a **49.7% increase** attributable entirely to a configuration choice. That is precisely
why the sensitivity is published and why the conservative threshold is the approved one:
the larger number depends on interpolating 15.6 m of unmeasured density, and the
threshold does not change any well's derived status.

The other three wells are completely insensitive to the threshold at every value tested.

---

## 5. What changed, exactly

Recursive comparison against the extracted Increment 6.1.7 baseline, excluding only the
private `data/` inputs and Python/pytest build caches, and **never collapsing a directory
into one item**:

```
BASELINE files : 193
INCREMENT 7    : 221
  identical    : 190
  changed      :   3
  added        :  28
  removed      :   0
  total path differences: 31
```

### Changed (3) — exactly the expected set

| file | why |
| --- | --- |
| `pyproject.toml` | version `0.6.8` → `0.7.0`. **No dependency added or removed.** |
| `p2mem/__init__.py` | version `0.7.0`; Increment 7 narrative appended; Increment 6.1.7 declared LOCKED. No executable behaviour changes. |
| `README.md` | Increment 7 implementation-status paragraph, Increment 7 scientific-limitations bullet, and a directory tree brought back up to date (it had not been refreshed since Increment 5, so the Increment 6 modules were added alongside the Increment 7 ones). |

**No other pre-existing file changed.** Verified independently against two packaged
ledgers:

- `INCREMENT_06_1_7_SHA256SUMS.txt` — **189 identical, 3 changed (the three above), 0
  missing**, out of 192 entries.
- `INCREMENT_05_1_2_SHA256SUMS.txt` — **146 identical, 3 changed (the three above), 0
  missing**, out of 149 entries. The locked Increment 5.1.2 foundation is byte-identical
  apart from the three version/narrative files.

### Added (28) — each listed individually

**Notebook (1)**
- `07_Density_QC_and_Overburden_Stress_Framework.ipynb`

**Configuration (1)**
- `config/overburden_stress.yml`

**Package modules (7)**
- `p2mem/overburden_models.py`
- `p2mem/density_qc.py`
- `p2mem/overburden.py`
- `p2mem/io/overburden_policy.py`
- `p2mem/io/overburden_registry.py`
- `p2mem/io/overburden_inventory.py`
- `p2mem/io/overburden_workflow.py`

**Tests (6)**
- `tests/synthetic_inc7.py`
- `tests/helpers_inc7.py`
- `tests/test_density_qc.py`
- `tests/test_overburden.py`
- `tests/test_overburden_policy.py`
- `tests/test_overburden_inventory.py`

**Outputs (9)**
- `outputs/07_density_overburden/density_availability_inventory.csv`
- `outputs/07_density_overburden/density_qc_summary.csv`
- `outputs/07_density_overburden/density_gap_inventory.csv`
- `outputs/07_density_overburden/overburden_eligibility_summary.csv`
- `outputs/07_density_overburden/vertical_stress_profile.csv`
- `outputs/07_density_overburden/shallow_column_scenarios.csv`
- `outputs/07_density_overburden/gap_threshold_sensitivity.csv`
- `outputs/07_density_overburden/density_overburden_issues.csv`
- `outputs/07_density_overburden/density_overburden_manifest.json`

**Figures (4)**
- `outputs/07_density_overburden/figures/fig01_density_coverage_and_unmeasured_column.png`
- `outputs/07_density_overburden/figures/fig02_density_qc_and_screening_band.png`
- `outputs/07_density_overburden/figures/fig03_measured_vertical_stress_increment.png`
- `outputs/07_density_overburden/figures/fig04_shallow_column_sensitivity_and_eligibility.png`

Plus this manifest, the Increment 7 checksum ledger, and the completion record.

### Removed (0)

---

## 6. Architecture

### 6.1 The twelve explicit masks

Every mask is a full-length, read-only boolean array aligned sample-for-sample with the
well's canonical `MD_m`, in original file order. **No mask holds or replaces a density
value.**

`source_value_present`, `finite_numeric_density`, `unit_resolved`,
`screening_range_plausible`, `below_seabed_sample`, `depth_mapping_valid`,
`within_survey_coverage`, `eligible_for_measured_integration`, `bridged_short_gap`,
`unresolved_long_gap`, `unresolved_shallow_column`, `unresolved_terminal_column`.

`eligible_for_measured_integration` is an explicit **conjunction**, enforced at
construction: it can never be true where a constituent is false, never true above a
resolved seabed, never true where a sample is simultaneously declared unresolved, and it
deliberately **excludes** bridged samples — a bridged value is conditioned, not measured,
and travels in its own mask.

`below_seabed_sample` is `None` — **not determinable** — for a well with no approved
formation-top file. An all-False array would assert that every sample is above the
seabed; an all-True array would assert the opposite. Both are claims this project cannot
make, and the eligibility conjunction would silently absorb either.

Measured mask counts:

| mask | Boreas 1 | Poseidon 2 | Poseidon North 1 | Proteus 1ST2 |
| --- | ---: | ---: | ---: | ---: |
| `source_value_present` | 32,845 | 31,897 | 31,310 | 31,235 |
| `finite_numeric_density` | 7,693 | 7,946 | 7,543 | 2,113 |
| `unit_resolved` | 32,845 | 31,897 | 31,310 | 31,235 |
| `screening_range_plausible` | 7,693 | 7,946 | 7,543 | 2,113 |
| `below_seabed_sample` | 30,786 | 31,710 | *not determinable* | *not determinable* |
| `depth_mapping_valid` | 32,845 | 31,897 | 31,310 | 31,235 |
| `within_survey_coverage` | 32,845 | 31,897 | 31,310 | 31,235 |
| `eligible_for_measured_integration` | 7,693 | 7,946 | 7,543 | 2,113 |
| `bridged_short_gap` | 46 | 0 | 0 | 0 |
| `unresolved_long_gap` | 102 | 0 | 0 | 0 |
| `unresolved_shallow_column` | 22,879 | 23,409 | 0 | 0 |
| `unresolved_terminal_column` | 66 | 355 | 2,284 | 37 |

`unresolved_shallow_column` counts the LAS samples *inside* the shallow unmeasured
column. It is necessarily smaller than the column's thickness implies, because a log that
starts below the seabed has no LAS row at all over the interval above its first sample —
and no mask can represent a sample that does not exist. The **thickness** is the operative
quantity and is reported separately; the two are deliberately not conflated.

### 6.2 Density preservation

`density_source.original_values_immutable: true` is enforced at configuration load.
The locked well frame's resolved RHOB array is read and never written; it remains
read-only, and the completion gate re-compares it byte-for-byte against the locked
loader's own `canonical_data` array. The conditioned representation lives in a
**separately named, separately read-only** `conditioned_density_kg_m3` array with its own
`bridged_mask`, so a caller holding both can diff them and see exactly which samples were
conditioned. **Nothing is clipped, rescaled, smoothed, despiked, replaced or
extrapolated, anywhere.**

### 6.3 Integration

Trapezoidal quadrature of `ρ·g·dz` against **TVDSS** — exact for a piecewise-linear
density profile, deterministic, no fitted parameter. Preconditions are checked in order
and never silently repaired: 1-D numeric arrays of equal length ≥ 2; boolean, string,
complex and object dtypes rejected with `TypeError`; every density finite and strictly
positive; every vertical depth finite; every vertical increment non-negative. A **zero**
increment contributes exactly zero, is counted, and is returned for disclosure. A
**negative** increment is rejected with a typed error rather than sorted away — it is
either a data-ordering defect or the wrong coordinate (measured depth in a deviated well),
and sorting would hide both. Measured-depth integration is not merely discouraged; the
integrator accepts a vertical-depth array and `VerticalStressProfile` refuses any
`integration_coordinate` other than `tvdss_m`.

Zero-thickness intervals encountered on the real data: **0** in every well.

### 6.4 Output policy — the Increment 6.1.7 architecture, generalized

`p2mem.io.output_policy` is locked, and its registries are module globals. Adding
Increment 7's artifacts to them would modify a locked file **and** make every Increment 6
export fail closed for not presenting Increment 7 artifacts.

`p2mem.io.overburden_policy` therefore lifts the same algorithm so its registries arrive
as an explicit `PolicyBundle`: same closed-schema-first ordering, same categories, same
schema-driven (never value-driven) field discovery, same isolated-staging → re-read →
re-validate → canonical-compare → failure-atomic publication. One category is **added**:
`enumerated_code_list`, used only by `limiting_reasons`, which is strictly *stronger* than
a structured diagnostic because every element is checked against a closed vocabulary
rather than a grammar, and the list must be sorted and duplicate-free.

**The generalization is checkable, not asserted.** `test_overburden_policy.py` builds a
`PolicyBundle` from the LOCKED Increment 6.1.7 registries and runs the generalized engine
over the **real, packaged Increment 6 output artifacts**, requiring the identical
decision on every one of the eleven reported metrics, an identical canonical
representation, and identical rejection behaviour on four adversarial mutations.

Increment 7 declares **nine** artifacts with exact closed schemas, and every schema
string field is classified exactly once — enforced in the `PolicyBundle` constructor, so
a future schema/policy drift cannot weaken the gate silently.

Measured on the real export: **3,486 string field occurrences** across 9 artifacts —
1,636 controlled, 1,786 structural, 64 outside the guarantee; **0 schema violations, 0
unclassified, 0 unauthorized, 0 field-kind mismatches**, before *and* after
serialization. 22 distinct registered statements, 2 templates, 17 typed labels used.
`named_lithology_assigned` = **false**, derived from those emitted records.

The export gate pins `serialization_stage` explicitly (`pre` before writing, `post` after
re-reading). `"auto"` is never used in the production path, and a test demonstrates
behaviourally why: a payload whose typed values are all strings is accepted by `auto` and
correctly rejected by the pinned `pre` stage.

---

## 7. Tests

**1,160 collected, 1,160 passed, 0 failed** in the complete combined suite.

| suite | tests |
| --- | ---: |
| Locked Increment 1–6.1.7 (unchanged) | **944** |
| `tests/test_density_qc.py` | 67 |
| `tests/test_overburden.py` | 78 |
| `tests/test_overburden_policy.py` | 41 |
| `tests/test_overburden_inventory.py` | 30 |
| **New in Increment 7** | **216** |
| **Total** | **1,160** |

The locked 944 also pass **in isolation**, confirming the Increment 7 additions changed no
locked test's outcome by side effect.

Coverage includes: constant-density and two-layer analytical integration (exact, not
approximate); water column plus formation; a numerical demonstration that MD integration
overstates by exactly `1/cos(inclination)`; repeated, equal, decreasing and fully
reversed vertical coordinates; zero-thickness intervals; screening bounds at the **exact**
configured values and at `nextafter` on either side; NaN and ±Inf in density and in depth;
boolean, string, bytes, complex and object dtypes; missing RHOB; all-invalid RHOB; a
single valid sample; short, multiple, long, shallow and terminal gaps; survey-coverage
truncation; no extrapolation; unit rejection; every constructor invariant; status
derivation from evidence under two different well keys; determinism across repeated runs
and independent destinations; and input arrays proven unmutated.

**All Increment 7 test fixtures are small, fictional and synthetic**, built from the REAL
locked dataclasses rather than mocks. No real or private project LAS, deviation,
checkshot or formation-top file is read, referenced, copied or packaged by any test.

---

## 8. Verification record

| # | check | result |
| --- | --- | --- |
| 1 | Baseline ZIP SHA-256 | **match** |
| 2 | Baseline checksum ledger | **192/192 identical** |
| 3 | Baseline suite before any change | **944 passed** |
| 4 | Safe ZIP paths, no symlinks, no absolute/`..` entries | **pass** |
| 5 | Increment 7 checksum ledger | **223/223 identical** |
| 6 | Offline editable install | **pass** |
| 7 | Exact package version | **`p2mem 0.7.0`** |
| 8 | Complete combined suite | **1,160 passed, 0 failed** |
| 9 | Locked Increment 1–6.1.7 subset in isolation | **944 passed** |
| 10 | `nbformat.validate()` | **pass** |
| 11 | Unique, valid cell IDs | **86/86 unique** |
| 12 | Zero saved notebook outputs | **0** |
| 13 | `%%writefile` byte parity | **17/17 exact** |
| 14 | Fresh-directory notebook execution | **pass, 35/35 gate** |
| 15 | Real four-well integration | **4/4 wells** |
| 16 | Deterministic regeneration from two independent roots | **9/9 artifacts byte-identical** |
| 17 | No absolute-path leakage | **pass** |
| 18 | No private raw data packaged | **pass** |
| 19 | Recursive delta vs Increment 6.1.7 | **3 changed, 28 added, 0 removed** |
| 20 | Common-file identity vs Increment 5.1.2 ledger | **146 identical, 3 changed, 0 missing** |
| 21 | Completion gate | **35/35** |
| 22 | Increment 8 not started | **confirmed** |

### Adversarial mutation checks beyond the packaged unit tests

Executed live inside the completion gate against the records this run **actually
serialized**, not a reconstruction:

- unauthorized prose in a registered-statement column
- a one-character near-miss on a registered statement
- an unapproved value in a typed-label column
- an unsorted `limiting_reasons` list
- a deleted column; an added column; a renamed column; **reordered columns**
- `"2000"`, `None`, `True`, `NaN` and `3.0` where a typed value is declared
- an unknown well identifier in a row and in the manifest `wells` map
- an unknown artifact in the payload set; a missing declared artifact
- an unknown manifest key; a missing manifest key
- a writer that substitutes one **authorized** statement for another (caught only by the
  canonical comparison)
- a writer that reverses row order
- a writer that raises mid-export
- a writer that omits an artifact entirely
- a stale undeclared artifact already present in the destination

Every one fails closed. The official destination is left byte-unchanged, and **no staging
or backup residue remains** after any handled failure.

---

## 9. Limitations, stated plainly

**Measured facts.** All four wells have contract-resolved bulk density in kg/m³, converted
by the locked `gcc_to_kgm3` factor. All are 100% depth-mapped with zero extrapolation and
zero screening-bound failures. Every log begins 3.3–4.4 km below its own seabed, or below
a seabed that cannot be determined at all. Measured increments over the supported columns
are 19.93, 30.62, 28.34 and 8.27 MPa.

**Assumptions.** Standard gravity (9.80665 m/s², CGPM exact by definition, but *assumed*
here — no local gravity survey exists). Seawater density (1025 kg/m³, bracketed
1020–1030 — no measured seawater density, salinity or temperature profile exists). The
1000–3500 kg/m³ screening band. The 10 m TVD gap-bridging threshold. The shallow-column
bracket bounds. Every one is declared in a reviewable configuration file and re-exported
in the manifest's assumption register.

**Interpretations.** That the shallow column's depth-averaged bulk density cannot exceed
the same well's measured 5th percentile is a *bounding screening argument* resting on
monotonic mechanical compaction. It is the weakest link in the bracket and is labelled as
such. The classification of Boreas 1 and Poseidon 2 as `screening_sensitivity_only` rather
than `not_eligible` reflects a judgement that a *quantifiable* unmeasured thickness can be
honestly bracketed; a reader who disagrees can read the partial measured increment alone,
which is unaffected.

**Unresolved.** The shallow density column in all four wells. The seabed datum, water
column and shallow-gap thickness in Poseidon North 1 and Proteus 1ST2. Boreas 1's 15.64 m
internal gap and the 2,511 eligible samples beneath it. The terminal columns below every
well's last valid sample. Whether Poseidon North 1's 3,497.90 kg/m³ maximum is a real
formation density or a processing artefact — the screening band admits it, and no
evidence in this project adjudicates it.

**Nothing here is calibrated.** No RFT/MDT/DST pressure, no LOT/XLOT/DFIT stress fit, no
core or log-calibrated density control, no measured seawater density, no local gravity
survey. **No result in this increment may be described as calibrated truth.**

---

## 10. Execution environment

The delivered notebook was executed to completion with **nbclient 0.11.0 + ipykernel on
CPython 3.12.10, Windows 11**, from a fresh working directory containing only the package
and the approved private inputs. **It was NOT run in Google Colab**, and no Colab
execution is claimed. The notebook detects Colab and mounts Google Drive when present,
and otherwise uses the current working directory as the project root; both paths were
exercised, the second end to end.

**One environment-specific caveat, disclosed:** IPython's `%%writefile` opens its target
in text mode, so on Windows it translates `\n` to `\r\n`. Re-executing the notebook
**on Windows** therefore rewrites the packaged source files with CRLF line endings, which
breaks byte parity against the LF-packaged originals even though the content is
identical. On Linux — including Google Colab, the delivery target — `%%writefile`
round-trips byte-exactly. This is a property of the tool and the packaging convention
inherited from every prior increment, not of Increment 7's code, and it affects no
scientific result: the fresh-directory Windows execution reported above passed 35/35 gate
checks and produced all nine artifacts byte-identical to the packaged ones.

Determinism claims cover the **nine CSV/JSON artifacts**. Rendered PNG figures are
excluded on purpose: their bytes depend on the installed matplotlib version, so
bit-identity across environments is not a claim this project can honestly make.
