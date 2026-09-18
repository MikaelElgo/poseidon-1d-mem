# Increment 10 - Scientific report and interpretation contract

Project owner: Mikael Elgo. Package: p2mem 0.10.0.
Assurance: Tier C - screening-level, uncalibrated educational study.

## 1. Result and scope

This release provides a reproducible **hypothetical sandstone-analogue mechanics
experiment**, an explicit field-method blocker matrix, independent calculations,
original-sample profiles, scenario summaries and stratigraphic marker context.
It does not produce a field-eligible or calibrated static/strength model.

The proposed Increment 10 allowed blocked field methods and separate synthetic
or assumed material scenarios. That branch is necessary here. The existing GR
proxy and formation labels do not establish sandstone or any other named
lithology. There is no accepted local static/strength calibration in the supplied
baseline. All field eligibility flags remain false. Those flags are scientific
stopping conditions, not failing software tests.

## 2. Chosen experiment

A single chained analogue is used, not a universal correlation ensemble:

1. Compute hypothetical static E from dynamic E using Mahdi & Alrazzaq (2024),
   Eq. 8, **Estatic[GPa] = 0.3655 Edyn[GPa]^1.0959**.
2. Withhold results outside the reported dynamic predictor span **17.90-43.45 GPa**.
   This is a numerical support restriction; a point inside it is not proven to
   belong to the source material or calibration population.
3. Use Chang et al. (2006), Table 1 Eq. 8, as an explicitly assumed sandstone
   strength law: **UCS[MPa] = 46.2 exp(0.027 Estatic[GPa])**. It consumes static E,
   never dynamic E directly. Its originating region/reference is unspecified in
   that source table. It is implemented only as an experiment, not accepted as a
   field correlation. Input support is further restricted to the selected static
   experiment's output span; that guard is not a validated empirical domain.
4. Derive G and K from static E and **assumed** static nu. Static nu is not copied
   from dynamic nu. Derive cohesion from UCS and assumed phi using Mohr-Coulomb;
   derive mu = tan(phi). Set the tensile cutoff from an explicit assumed ratio.

The combination of these two studies is itself unvalidated. It does not establish
material transferability, pressure/temperature/saturation equivalence, anisotropy,
strain-rate equivalence or a locally appropriate strength law. No parameter is
adjusted to make the output look more realistic.

The purpose is to test the computational path and quantify the response of a
specified hypothesis to assumed mechanics parameters. It is not a claim that
these numbers are the best available estimates of Poseidon mechanical properties.

## 3. Seven parameter cases

| Case | Static nu | phi (degrees) | T0/UCS |
|---|---:|---:|---:|
| reference_experiment | 0.25 | 30 | 0.05 |
| nu_020 | 0.20 | 30 | 0.05 |
| nu_030 | 0.30 | 30 | 0.05 |
| phi_020 | 0.25 | 20 | 0.05 |
| phi_040 | 0.25 | 40 | 0.05 |
| tensile_zero | 0.25 | 30 | 0.00 |
| tensile_010 | 0.25 | 30 | 0.10 |

These are **project-selected numerical experiment points**, not measurements,
probability levels or literature-derived lower/upper bounds. Reference means
comparison anchor, not most likely or calibrated. The cases vary one parameter
at a time, so dependencies are interpretable. G/K change with nu; c/mu change with
phi; the tensile cutoff changes with T0/UCS. E and UCS do not depend on those
three parameters in the selected chain and must remain unchanged across cases.

No static conversion-factor uncertainty band is invented. No claim is made that
the seven cases span all plausible rock behavior. A field uncertainty range for
nu, phi or tensile strength remains unavailable.

## 4. Physics and invariant checks

For stable isotropic equivalents, E > 0 and -1 < nu < 0.5:

- G = E/[2(1+nu)]
- K = E/[3(1-2nu)]
- E = 9KG/(3K+G)

Compression-positive Mohr-Coulomb convention:

- q = (1+sin(phi))/(1-sin(phi))
- c = UCS(1-sin(phi))/(2 cos(phi))
- mu = tan(phi)
- UCS = 2c cos(phi)/(1-sin(phi))

The tensile cutoff must be nonnegative and no larger than UCS/q in this model.
That keeps it consistent with the Mohr-Coulomb uniaxial tensile intercept.
This is a parameter-consistency check, not a WBS calculation. No stress tensor,
collapse pressure or tensile-initiation pressure is calculated here.

## 5. Actual packaged-data coverage

| Well | Original samples | Valid dynamic E | Analogue numeric support | Field eligible |
|---|---:|---:|---:|---:|
| Boreas 1 | 32,845 | 2,565 | 388 | 0 |
| Poseidon 2 | 31,897 | 3,855 | 1,739 | 0 |
| Poseidon North 1 | 31,310 | 7,388 | 3,428 | 0 |
| Proteus 1ST2 | 31,235 | 953 | 290 | 0 |

Total original rows: 127,287. Analogue numeric rows: 5,845.
Coverage refers to original LAS samples, not reservoir thickness. No missing
interval is interpolated, resampled, clipped, bridged or extrapolated.

Full reference profiles preserve well ID, original sample index, MD/TVD/TVDSS,
upstream dynamic E and validity, scenario support, field eligibility, evidence
class and calibration status. Every mechanics quantity is blank where the
required dynamic input or numerical support is absent.

Boreas GR exclusion does not prevent its independent dynamic/analogue numerical
experiment. That does not make Boreas lithology known.

## 6. Formation context

Only accepted, mapped pairs from the locked Increment 5 top register are used.
Intervals are half-open in MD: top inclusive, base exclusive. Samples at a base
marker belong to the following interval, if one exists; TD is not extended.
The output preserves `petrel_source_trace` and the inherited
`inferred_unverified` well-identity status. A marker pair is a contextual bin,
not a new lithology interpretation. No approved pairs exist for North 1 or
Proteus, so no invented formation summaries are supplied for them.

Statistics are unweighted sample min/median/max on each property's own support.
They are not thickness-weighted or formation-wide property estimates. Counts and
support fractions travel with every summary. A minimum or maximum here is a
sample statistic, not an uncertainty percentile.

## 7. Rejected or blocked alternatives

- Universal dynamic-to-static ratios: no universal conversion is justified.
- Horsrud field UCS: material applicability is unproven; absolute Vp is not
  exported in the elastic CSV; the originating full text was not inspected.
- Bradford field relationship: originating equation text was not inspected;
  copying a secondary table is not sufficient for field activation.
- GR-derived named lithology: prohibited by the existing evidence limits.
- Calibrated static, strength, pressure or stress outputs: no new independent
  calibration measurements were supplied.

The field gate cannot be enabled by changing one boolean in this release. New
material/laboratory evidence requires a new version, evidence review and new
applicability tests. A hypothetical value cannot be promoted merely because it
is finite or numerically plausible.

## 8. Verification boundary

Baseline 9 passed 1,754 tests before implementation. All its 282 ledger-covered
files were verified. New tests address equations, units/domains, missingness,
parameter dependencies, schema/claim mutations, source hashes, interval counts,
publication rollback and notebook extraction. The runner uses JUnit failures,
errors and skips, not a substring such as `1754 passed`.

A separate package-free checker uses 60-digit Decimal exp/ln for 80 exported
reference rows and Mohr-circle tangency geometry. Four fixed Decimal examples
are also in the unit tests. This is independent numerical verification, not
laboratory validation. Independent Excel end-to-end verification remains part
of the final assurance increment.

Reproduction here reads **packaged derived Increment 9 data**. It does not
re-read private LAS or deviation inputs. A local notebook execution is not a
hosted Google Colab execution. Final observed test/environment details are in
the completion record. Checksums prove file identity, not geological validity.

## 9. Handoff to Increment 11

Eligible field mechanics remain unavailable. Increment 11 may use the published
quantities only in an explicitly conditional stress experiment carrying the
same material and parameter assumptions. Use `evaluate_mechanics` with the
specific configured case for a full non-reference profile. Never combine a
reference UCS/nu profile with a different case's label or inferred uncertainty.

Static nu affects a uniaxial-strain stress scenario; static E is required only
for stress models with the relevant strain/boundary-condition dependency.
These assumptions must be kept separate from the already uncalibrated Sv/Pp
scenarios. No Increment 11 module is included.

## 10. References

- Mahdi, D.S. and Alrazzaq, A.A.A. (2024). A New Correlation for Estimating Static
  Elastic Properties of Sandstone Formations: Case Study from Rumaila Oilfield.
  Iraqi Geological Journal 57(2B), 77-88. Eq. 8 and Table 2.
  https://doi.org/10.46717/igj.57.2B.5ms-2024-8-15
- Chang, C., Zoback, M.D. and Khaksar, A. (2006). Empirical relations between rock
  strength and physical properties in sedimentary rocks. JPSE 51, 223-237.
  Table 1 Eq. 8 and static-modulus discussion, p.227.
  https://doi.org/10.1016/j.petrol.2006.01.003
- Labuz, J.F. and Zang, A. (2012). Mohr-Coulomb Failure Criterion.
  Rock Mechanics and Rock Engineering. https://doi.org/10.1007/s00603-012-0281-7
- Isotropic elasticity: MIT Structural Mechanics Note L.4, the constitutive
  identities referenced by Increment 9. URL retained in the correlation registry.

Exact source locations, reviewed restrictions and experiment assumptions are
machine-readable in `config/mechanics_correlations.json`. Source equations were
checked, not their original laboratory data. No copyrighted paper PDFs are
redistributed in this package.
