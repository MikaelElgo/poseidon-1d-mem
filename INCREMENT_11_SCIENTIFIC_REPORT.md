# Increment 11 — In-Situ Stress Scenarios, Bounds and Depth Integration

Project owner: Mikael Elgo. Package p2mem 0.11.0. Tier C: uncalibrated educational screening.

## Result and scope

This increment completes the horizontal-stress scenario layer from the revised proposal. It produces compatible stress tuples at 202 existing reporting nodes: 122 in Poseidon 2 and 80 in Boreas 1. There are 33 scenarios per node (three inherited shallow-Sv cases crossed with eleven parameter experiments), giving 6,666 rows. Of these, 5,082 have calculable horizontal stresses, 1,584 require unavailable static E for imposed strain, and 3,175 pass the selected conditional fault-friction test. Field stress eligibility remains false for every row.

Poseidon North 1 and Proteus 1ST2 retain their existing measured density increments, but have no accepted absolute-Sv scenario profiles in Increment 8. They therefore remain blocked for this step. Boreas's GR exclusion does not prohibit a separate density-based stress experiment; no lithology is inferred from its GR or from its name.

## Constitutive experiment and conventions

All stresses are MPa; compression and shortening are positive. Depth is positive downward. TVDSS zero is mean sea level; the inherited hydrostatic reference is gauge-zero at mean sea level. The model assumes vertical and horizontal principal axes, isotropic small-strain poroelasticity and no shear traction in this local frame. It is not a regional stress inversion.

Biot effective stress for intact-rock deformation is S' = S - alpha Pp. Eliminating vertical strain from the isotropic compliance equations gives:

    Sh0 = nu/(1-nu) * (Sv-alpha Pp) + alpha Pp
    Sx = Sh0 + E/(1-nu^2) * (epsilon_x + nu epsilon_y)
    Sy = Sh0 + E/(1-nu^2) * (epsilon_y + nu epsilon_x)

E is converted explicitly from GPa to MPa. Shmin = min(Sx, Sy); SHmax = max(Sx, Sy). The relative principal-frame stress tensor is diag(Sx, Sy, Sv), with zero shear by assumption. Each exported tuple retains Sx, Sy, Sv, Pp, alpha, nu, E availability, strain, shallow-Sv case, pressure basis and fault-friction assumption. This is enough to construct a *conditional relative-frame* tensor; it is not a geographic tensor.

Zero horizontal strain yields equal horizontal stresses. Static E is mathematically unnecessary in that limit. Thus missing E does not suppress zero-strain cases. Static nu is an explicit assumption from the corresponding Increment 10 parameter case; it is not a measured static or dynamic Poisson ratio. Imposed-strain calculations require the Increment 10 analogue static E at the exact source node. Its additional use as an equivalent drained modulus is also an unverified assumption. No missing E is interpolated or copied from another well.

The constitutive derivation follows isotropic compliance and the Biot effective-stress decomposition reviewed in Merxhani (2016), Sections 2–4. The compression-positive form above is the project's algebraic specialization. These equations describe specified boundary conditions and are not a universal predictor of absolute in-situ stresses.

## Experiment matrix

Every case is evaluated for inherited Sv low/base/high separately. Base is the upstream arithmetic comparison point, not a best estimate. Reference uses nu=0.25, alpha=1, fluid density 1025 kg/m3, fault mu=0.6, and zero horizontal strain.

| Case | Change from reference | Purpose |
|---|---|---|
| reference | None | Comparison anchor |
| nu_020 / nu_030 | Static nu 0.20 / 0.30 | Boundary-condition sensitivity |
| alpha_080 | Biot alpha 0.8 | Intact effective-stress sensitivity |
| fluid_1020 / fluid_1030 | Reference density 1020 / 1030 kg/m3 | Inherited fluid assumptions |
| fault_mu_040 / fault_mu_080 | Fault friction 0.4 / 0.8 | Conditional friction test only |
| strain_x_0500 | x shortening +500 microstrain | Anisotropic loading experiment |
| strain_equal_0500 | x and y shortening +500 microstrain | Equal-strain symmetry |
| strain_x_minus0500 | x extension -500 microstrain | Sign and loading sensitivity |

These points do not define probability distributions or uncertainty percentiles. Fault friction is independent of Increment 10 intact-rock friction angle/cohesion. Changing fault friction changes the bound, not the poroelastic stress. The default matrix is locked and validated; new scenarios require a reviewed configuration/release. There is no hidden tuning to make scenarios pass.

## Frictional bounds and incompatible states

The friction screen assumes optimally oriented, cohesionless pre-existing discontinuities with a selected friction coefficient and effective normal traction S-Pp. This fault pressure coefficient is **one**, independent of intact-rock Biot alpha. It is not permissible to substitute alpha Pp silently into this fault criterion.

Let Q = (sqrt(1+mu^2)+mu)^2. Positive fault-effective principal stresses must satisfy max(Sv, SHmax)-Pp <= Q [min(Sv, Shmin)-Pp]. The implemented conditional polygons follow the ratio and regime-boundary construction in Miranda et al. (2023), Section 3.2, Equations 5 and 7. No site measurements, local parameters or Canadian stress regime from that study are transferred to Poseidon.

For fixed Sv and Pp, v=Sv-Pp must be positive. The polygon in (Shmin, SHmax) is bounded by vertices (Pp+v/Q,Pp+v/Q), (Pp+v/Q,Sv), (Sv,Pp+Qv), (Pp+Qv,Pp+Qv). For a specified h=Shmin-Pp, the conditional SHmax interval is Pp+[max(h,v/Q), Q min(h,v)], provided the lower limit does not exceed the upper limit and fault-effective stresses are compressive. These are compatible bounds, not independently selectable marginal endpoints.

Numerical stress outputs are retained when the chosen friction test rejects them. Status explains missing E, negative Biot effective vertical stress, nonpositive fault-effective stress, a violated friction bound, or conditional admissibility. Nonpositive fault-effective states never use a singular principal-stress ratio. No rejected state is clipped to the polygon. A numerical regime label describes the ordering of that particular tuple; equality cases receive explicit degenerate/boundary labels. No label establishes the field's actual faulting regime.

## Depth, partitions and sparse coverage

Increment 7 reports selected original density nodes; its node_index is **not** the LAS sample_index. The new join matches identical original MD and separately checks TVD and TVDSS within 1e-7 m absolute or 1e-10 relative tolerance. It preserves both indices, the `petrel_source_trace` basis and inherited `inferred_unverified` well identity. It does not map mechanics to a new grid, bridge gaps, extrapolate to TD, or create stress nodes below inherited density truncation.

At each accepted node, Sv is reconstructed as water-column assumption + unlogged-shallow-column assumption + measured cumulative density integral + conditioned contribution. The present profiles' conditioned contribution is zero; the workflow explicitly rejects a changed upstream conditioned-partition contract. Every reconstructed Sv agrees with Increment 8, and the reference effective stress agrees with its existing alpha=1, density=1025 profile. Pressure is reevaluated at the same TVDSS with the inherited gravity and stated reference fluid density.

Only one Boreas reporting node and 25 Poseidon 2 reporting nodes have analogue E. This is the sparse stress-node intersection, not a change to Increment 10's 5,845 analogue-supported LAS samples. A denser strain profile would require a separately reviewed alignment/integration implementation, not nearest-neighbor filling. QC figures use points to avoid suggesting full-depth continuity. Terminal polygons explicitly carry their node and depth in the polygon table.

Formation summaries use accepted Increment 5 marker pairs, top-inclusive/base-exclusive MD intervals, without extension to TD. Statistics are unweighted over selected reporting nodes and include flagged numerical cases. Counts, admissible counts and scenario IDs accompany each statistic; these are not thickness-weighted formation estimates. The marker context does not establish lithology.

## Claim and downstream contract

Allowed: conditional horizontal stresses, explicit relative-frame principal axes, bounds under assumed fault friction, and numerical regime labels. Unavailable: calibrated Shmin/SHmax, geographic SHmax azimuth, predicted formation pressure, local fault friction, operational mud weight and a validated drilling window.

Increment 12 must consume whole compatible tuples and their evidence flags, not mix separate case extrema. Fault-admissible is not field-eligible or proof of wellbore stability. Strength support, the assumed material model and relative borehole orientation require their own checks. Where geographic orientation is absent, a future relative-azimuth experiment may be defensible; an absolute azimuth is not supplied here. This increment performs no wellbore-wall failure calculation.

## Reproducibility and validation

The COMPLETE Increment 10 ZIP has SHA-256 `6b28114fe211b2d1d4c713fc1f90f74a415993a4755eb9028161d4de5cc9d296`. All 313 baseline ledger entries are retained; only README, package version metadata and __init__ version text change. Historical scientific modules, notebooks and outputs remain byte-identical. Use the Increment 11 runner for cumulative verification; historical release runners still describe their own versions.

The independent checker imports neither p2mem nor NumPy. It solves the horizontal compliance system with 50-digit Decimal arithmetic and checks fault admissibility using Mohr-circle tangent geometry, over all 5,082 numeric exported rows. It also checks all 1,584 missing-E rows. Software tests cover domains, known solutions, stress translation, E dependency, axis swaps, all stress orderings, malformed configuration, exact joins, changed source/output files and publication rollback.

The release builder adds the ledger itself to the ZIP, checks CRCs and exercises the notebook's actual extract_release and verify_tree functions. A regression test builds and extracts the real cumulative release, preventing the omitted-ledger defect from Increment 10. Notebook execution is verified locally; hosted Google Colab execution is not claimed. Reproduction uses packaged derived inputs, not private raw LAS regeneration. The cumulative test outcome and delivered archive hash are recorded separately.

## References

- Merxhani, A. (2016). An introduction to linear poroelasticity. https://arxiv.org/pdf/1607.04274
- Miranda et al. (2023). Estimating theoretical stress regime for engineered geothermal energy systems in an arctic community (Kuujjuaq, Canada). https://comptes-rendus.academie-sciences.fr/geoscience/articles/10.5802/crgeos.193/
- Increment 10 scientific report and correlation registry retain the analogue static-E source and its restrictions. Original paper PDFs are not redistributed.
