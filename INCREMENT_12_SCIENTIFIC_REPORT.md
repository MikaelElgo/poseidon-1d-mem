> **Verification repair 1:** The original exact-float strength assertion was not portable to the user's Colab runtime. The repaired verification uses explicit rounding tolerances and independently checked reproduction. See INCREMENT_12_REPAIR_1.md for current repair evidence. Original release qualification records below remain historical evidence, not proof of hosted Colab compatibility.

# Increment 12 — Benchmarked Mechanical Wellbore-Stability Envelopes

Mikael Elgo · 8 September 2026 · Package 0.12.0 · Tier C / uncalibrated educational screening

## Scope and provenance

This increment adds a circular elastic well-wall model to the complete Increment 11 release. It joins complete stress scenario tuples to Increment 10 analogue strength at the same original LAS sample index and checks MD, TVD and TVDSS agreement. There is no interpolation across missing strength, no inferred continuous profile and no substitution of reporting-node index for original sample index.

The strength hypothesis remains the unverified sandstone analogue from Increment 10. Its static modulus is additionally treated as a drained-equivalent property in inherited stress scenarios. WBS uses the matching assumed static Poisson ratio, UCS, friction angle and tensile strength; E itself is not required by the prescribed far-field-stress wall solution. Case identifiers remain intact. The upstream mechanics and stress reports contain the correlation provenance and its transfer limitations.

The inherited uncertainty is scenario-based, not a probability distribution. Fault-friction admissibility is a prerequisite, not validation of the assumed field stresses. No row is field eligible.

## Coverage

| Well | Stress rows audited | Exact strength nodes | Eligible tuples | Orientation cases | Conditional intervals | Empty intervals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Boreas 1 | 2,640 | 1 | 21 | 147 | 135 | 12 |
| Poseidon 2 | 4,026 | 25 | 525 | 3,675 | 3,356 | 319 |
| Poseidon North 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Proteus 1ST2 | 0 | 0 | 0 | 0 | 0 | 0 |
| Total | 6,666 | 26 | 546 | 3,822 | 3,491 | 331 |

North and Proteus remain blocked by upstream absolute-Sv scenario availability. All other excluded rows retain reasons in `wbs_input_eligibility.csv`; reasons can overlap. Alpha = 0.8 cases are explicitly unsupported by this boundary formulation. No stresses are clipped to pass fault bounds and no synthetic strength fills missing nodes.

## Mechanical formulation

Compression is positive; stresses and pressures are MPa. The medium is homogeneous, isotropic, infinitesimally elastic and infinite around a circular hole. The calculation is static and isothermal. Far-field vertical stress is assumed to be a principal stress. Axial wall stress follows the generalized plane-strain Kirsch perturbation; radial wall shears are zero. This is a mechanical wall-onset screen, without plastic redistribution, diffusion, chemistry, bedding weakness, thermal stress or time evolution.

For the vertical benchmark, effective wall components are radial `Pw-Pp`, circumferential `SHmax+Shmin-2(SHmax-Shmin) cos(2 theta)-Pw-Pp`, and axial `Sv-2 nu(SHmax-Shmin) cos(2 theta)-Pp`. These are the classical effective-stress wall equations with unit pressure coefficient. [John Foster, UT Austin, Lecture 15, wall simplification on slide 9](https://johnfoster.pge.utexas.edu/PGE334-ResGeomechanics/slides/Lecture15-CompressiveAndTensileFailureInVerticalWells.slides.pdf).

For hypothetical inclination `i` and azimuth `a` measured from the assumed SHmax axis, the borehole basis vectors in the principal frame are:

- x = (cos i cos a, cos i sin a, -sin i)
- y = (-sin a, cos a, 0)
- z = (sin i cos a, sin i sin a, cos i)

Stack these vectors as rows of R and compute total stress `S = R diag(SHmax, Shmin, Sv) R.T`. Let `A=(Sxx-Syy) cos(2 theta)+2 Sxy sin(2 theta)`. At the wall, effective circumferential stress is `Sxx+Syy-2A-Pw-Pp`, axial stress is `Szz-2 nu A-Pp`, and circumferential–axial shear is `2(Syz cos theta-Sxz sin theta)`. Effective radial stress remains `Pw-Pp`. The radial component and the eigenvalues of the complete circumferential–axial block are sorted together. This retains shear and axial effects for inclined cases. [D. Nicolas Espinoza, Wellbore Stability, sections 6.6.1–6.6.4](https://dnicolasespinoza.github.io/node8.html).

The implementation deliberately restricts the effective-pressure coefficient to one. It applies total radial traction `Pw`, then subtracts fixed formation pressure `Pp` from all normal components. It does not apply `alpha Pp` a second time, and it does not set formation wall pressure to `Pw`. The prescribed seal is an ideal boundary even for underbalanced candidates; a physical mudcake is not asserted to form there. The classic total-traction Kirsch benchmark provides an additional check on this elastic boundary. [GEOS official Kirsch wellbore validation](https://geosx-geosx.readthedocs-hosted.com/en/latest/docs/sphinx/advancedExamples/validationStudies/wellboreProblems/kirschWellbore/Example.html).

Orientations are vertical, and inclinations 30°/60° at relative azimuths 0°/45°/90°. They are experiments at supported source depths, not reconstructed well trajectories. Geographic SHmax and well azimuth remain absent. Equal horizontal stresses make the horizontal reference axis arbitrary; the response is azimuth-invariant. These orientation sweeps do not establish a preferred drilling direction.

## Failure criteria and intervals

Sort effective wall principal stresses as sigma1 >= sigma2 >= sigma3. The Mohr–Coulomb margin is `UCS + q sigma3 - sigma1`, with `q=(1+sin phi)/(1-sin phi)`. The tensile margin is `sigma3+T0`. Both must be nonnegative. The MC and tensile critical angles are exported separately. A radial, hoop or axial principal stress can control either boundary; lower/upper labels are not automatically synonymous with collapse/fracture. The tensile criterion denotes local onset, not breakdown, propagation, leak-off or loss circulation.

At any fixed angle the wall tensor is affine in Pw. Its largest eigenvalue is convex and smallest is concave, so each failure margin and their minimum over angles are concave. Therefore the stable set under these frozen assumptions is one interval, a point, or empty. The solver first maximizes the minimum margin by golden-section search; it then brackets each edge and bisects to a pressure tolerance of 1e-5 MPa. This avoids skipping narrow intervals between pressure samples. A maximum within 1e-6 MPa of zero is classified `tangent_or_unresolved` with no reported interval.

The search begins at zero gauge pressure and ends at an explicit large bound derived from the input stress/strength scale. The upper endpoint is tested for failure. A failure to bracket becomes `upper_unbracketed`, never a supported physical upper limit. Domain-zero boundaries are separately identified. The release cases contain only `interval` or `empty` statuses.

Angular sampling starts at 2°, refines to 1°, and can continue to 0.5° and 0.25°. Acceptance requires the two interval endpoints to change by at most 0.02 MPa between grids; for empty sets, the maximum margin and classification must agree within 0.02 MPa. All 3,822 release rows passed this check. This is sampled-angle convergence, not a proof of the exact continuous-angle boundary. The independent 0.25° check found a worst boundary margin of approximately -0.00668 MPa, consistent with the declared discretization tolerance. Interpret near-endpoint failure classifications accordingly. The much smaller bisection tolerance does not remove angular uncertainty.

Density columns are available only for supported intervals at positive TVDSS. They use `rho_eq = 1e6 Pw / (9.80665 TVDSS)`, a hypothetical uniform column from mean sea level. They exclude rig datum, riser fluid, surface backpressure, circulation and transient pressure effects. They are not recommended mud weights. There is no imposition of Pw >= Pp, so underbalanced mathematical candidates can appear.

## Verification and outputs

The core tests cover rotation invariants, complete principal-stress ordering, radial traction, analytical vertical components, narrow/empty/tangent pressure sets, angular convergence and invalid boundary/material inputs. For the isotropic benchmark `S=60 MPa, Pp=20 MPa, UCS=40 MPa, phi=30°, T0=2 MPa`, the combined exact interval is [30,90] MPa and both ends are MC-controlled. With UCS increased to 1000 MPa the interval is [18,102] MPa and both ends are tensile-controlled.

The independent checker imports no p2mem functions. It intersects linear inequalities for all principal-stress pairs at the two extrema of cos(2 theta) for vertical cases, giving exact continuous-angle vertical intervals without pressure search or assumed stress ordering. It checks all 546 vertical cases, all 28,590 critical-wall records with full 3×3 eigensolves, and all 3,491 supported intervals on a separate 0.25° grid. The maximum principal-stress discrepancy is below 1e-12 MPa. It also checks both sides of each supported boundary and equivalent-density inversion.

Historical release self-tests are version-specific. The runner reconstructs the exact Increment 11 tree from its ledger, restoring only its archived README/version metadata, then runs its 1,929 historical tests. New Increment 12 tests run on a separate current release copy. Existing science, tests, configurations, outputs and notebooks are unchanged. Use `scripts/run_increment_12.py`, not a flat all-version pytest invocation that asks old packagers to verify new metadata against old ledgers.

| Artifact under outputs/12_wellbore_stability | Content |
| --- | --- |
| wbs_input_eligibility.csv | All 6,666 stress inputs, exact strength matches, inherited provenance and explicit gates |
| pressure_envelopes.csv | 3,822 orientation cases, status, boundaries, limiting criteria, residuals and angular history |
| critical_wall_states.csv | 28,590 critical-angle records at reference pressure and, when supported, lower/mid/upper pressure |
| coverage.csv | Four-well coverage and blockers |
| analytical_benchmark.csv | Synthetic analytical reference states |
| wbs_qc.png | Base/reference intervals at discrete nodes, two selected hypothetical orientations |
| wbs_manifest.json | Input/output hashes, row counts and declared limitations |

The notebook runs checks, optionally reproduces outputs, displays QC and exports a separate results bundle. Validation in this environment uses local execution of its unmodified code cells; hosted Colab execution is not claimed. See the completion record for final test evidence.

## Increment 13 handoff

Integrate scenario uncertainty, evidence levels, traceability and final independent verification. Preserve whole compatible tuples and the blocked/empty states. Field trajectory/orientation data, transferable rock-strength calibration and pressure/stress calibration remain prerequisites for any field application. No operational drilling result is established by this release.
