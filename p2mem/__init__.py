"""
p2mem - Poseidon 2 1D Mechanical Earth Model workflow package.

Project classification: Tier C - Screening-Level / Uncalibrated Educational
1D Mechanical Earth Model (see project design review, Rev 1). Nothing in
this package should be presented as a calibrated, operational, or
field-validated result unless an explicit independent calibration record
is attached to that specific output.

This package is under incremental, gated construction.

* Increment 1 / 1.1 delivered the project skeleton and the unit-control
  system (``p2mem.units``).
* Increment 2 added an auditable LAS-ingestion layer with explicit
  per-file curve contracts (``p2mem.io.las``, ``p2mem.io.inventory``,
  ``p2mem.models``) for the four approved wells (Poseidon 2, Boreas 1,
  Poseidon North 1, Proteus 1ST2). It performs LAS parsing, curve-identity
  resolution, NULL-sentinel handling, and factual inventory generation
  ONLY - no deviation-survey processing, MD-to-TVD/TVDSS transformation,
  checkshot processing, formation-top correction, petrophysical
  interpretation, or any later-phase geomechanical calculation.
* Increment 2.1 / 2.1.1 are corrective patches to Increment 2, applied
  after independent technical audits, WITHOUT changing scope or the
  underlying LAS-parsing/curve-resolution architecture (which both audits
  found sound). 2.1 corrected: canonical array naming (every array is now
  explicitly unit-suffixed, e.g. ``VP_m_s`` rather than ``DTCO``, so a
  name can never be mistaken for the wrong physical quantity or unit);
  the measured-depth curve is now located via an explicit contract role
  rather than by matching a canonical name spelled "DEPT"; several
  file-identity checks (filename, SHA-256, WELL, VERS, WRAP, NULL) that
  were not previously blocking now are; curve-coverage statistics now
  report raw AND canonical values with explicit units; and per-well
  batch failures are now typed (``p2mem.models.IngestionFailure``)
  instead of bare caught exceptions. 2.1.1 corrected a packaging-only gap
  (three notebook ``%%writefile`` cells that had drifted from their
  packaged source files). See ``INCREMENT_02_v2.1_MANIFEST.md`` and
  ``INCREMENT_02_v2.1.1_MANIFEST.md`` for the full audits and
  corrected-file checksums.
* Increment 3 adds Petrel deviation-survey ingestion with explicit
  per-file contracts (``p2mem.io.deviation``), a standard minimum-
  curvature trajectory engine with a numerically stable ratio-factor
  limit (``p2mem.trajectory``), an explicit MD-referenced/TVD-referenced/
  TVDSS depth-reference framework and MD-to-TVD/TVDSS interpolation with
  no silent extrapolation (``p2mem.depth_mapping``), and typed dataclasses
  for all of the above (``p2mem.deviation_models``) - for the same four
  approved wells. It independently reproduces the Petrel-supplied
  trajectory to millimetre scale for three of the four wells and
  discloses (rather than resolves) a real, larger trajectory-
  reconstruction discrepancy found in Proteus 1ST2's deeper section - see
  ``INCREMENT_03_MANIFEST.md``. It performs deviation-survey ingestion,
  trajectory validation, and depth mapping ONLY - no checkshot
  processing, formation-top correction, petrophysical interpretation, or
  any later-phase geomechanical calculation.
* Increment 3.1 is a corrective patch to Increment 3, applied after an
  independent technical audit, WITHOUT changing scope, equations, real
  well data, or the locked LAS/Increment-2.1.1 foundation. It corrected
  four defects: (1) the four deviation-survey source filenames are the
  exact, literal names as they exist in Google Drive, which contain
  spaces (e.g. ``"Poseidon 2_dev.txt"``) - Increment 3 had incorrectly
  substituted underscores in the contract keys, notebook mapping, and
  tests, which would have failed to resolve against the real files;
  internal well keys (e.g. ``Poseidon_2``) remain underscored and are
  unaffected; (2) every exported CSV/JSON/manifest field is now
  guaranteed to carry a basename only, never a full environment-dependent
  build path (runtime-only diagnostic objects may still retain one);
  (3) the previously undisclosed inference that the supplied ``DLS``
  column is normalized as degrees per 30 metres is now explicitly flagged
  with a new, independently per-file-verified
  ``DLS_NORMALIZATION_INFERRED_AS_DEG_PER_30M`` WARNING (mirroring the
  pre-existing MD-unit-inference warning); (4) the dogleg angle between
  successive stations is now computed with a numerically stable
  ``arctan2(||cross||, dot)`` vector formulation (``p2mem.trajectory``)
  instead of ``arccos``, which was ill-conditioned near a zero dogleg and
  previously reported a spurious ~1e-6-degree value for two stations with
  identical inclination/azimuth. The real four-well data, station counts,
  tolerances, and the unresolved Proteus 1ST2 trajectory discrepancy are
  all unchanged by this patch. See ``INCREMENT_03_1_MANIFEST.md`` for the
  full audit and re-verification record.

* Increment 4 adds checkshot (velocity survey) ingestion with explicit
  per-file contracts (``p2mem.io.checkshot``, ``config/checkshot_
  contracts.yml``), typed checkshot dataclasses (``p2mem.checkshot_
  models``), deterministic checkshot inventory/QC-table builders
  (``p2mem.io.checkshot_inventory``), and a numerical time-depth layer
  (``p2mem.time_depth``): duplicate-tie detection/conditioning, average/
  interval velocity diagnostics, checkshot-vs-locked-survey depth-
  reference comparison, forward/inverse piecewise-linear time-depth
  interpolation with explicit coverage masking (no extrapolation), LAS
  MD-to-checkshot-time mapping within validated checkshot coverage only,
  and a Poseidon-2-only sonic-checkshot drift diagnostic (trapezoidal
  integration of sonic slowness vs. the checkshot-interpolated OWT
  increment over the same MD/Depth interval). Three checkshot files are
  admitted: ``Poseidon2-Checkshot.txt`` (Poseidon 2 - the ONLY checkshot
  approved to define a primary time-depth relationship),
  ``Boreas1-Checkshot.txt`` and ``Proteus1-Checkshot.txt`` (Boreas 1 and
  Proteus 1ST2 - supporting QC data only, newly admitted in this
  increment, never transferred into Poseidon 2 as a substitute time-depth
  model). Proteus 1ST2's association with ``Proteus1-Checkshot.txt`` is
  explicitly disclosed as inferred/unverified (no embedded well
  identifier). Poseidon North 1 has no approved checkshot file
  (``checkshot_availability: NOT_AVAILABLE`` - a factual data gap, not an
  ingestion failure). This increment reuses the LOCKED Increment 1
  ``owt_to_twt``/``twt_to_owt`` unit functions and the LOCKED Increment
  3/3.1.1 ``petrel_source_trace`` survey trajectory unchanged; it performs
  checkshot QC and time-depth framework work ONLY - no formation-top
  correction, lithology interpretation, density modelling, pore-pressure
  prediction, elastic properties, rock strength, stress modelling, or
  wellbore-stability analysis. See ``INCREMENT_04_MANIFEST.md`` for the
  full technical detail and independently recomputed statistics. NOTE:
  ``INCREMENT_04_MANIFEST.md`` contained one identified defect, corrected
  by Increment 4.1 below - do not rely on its original, uncorrected
  statement that TVDSS is strictly increasing after Depth-tie conditioning
  for all three wells.

* Increment 4.1 is a narrowly scoped corrective patch to Increment 4,
  applied after an independent technical/numerical-method audit, WITHOUT
  beginning Increment 5 or any formation-top/petrophysics/pore-pressure/
  mechanical-properties/stress/wellbore-stability work. It corrected two
  defects and hardened two numerical contracts: (1) ``tvdss_to_owt``/
  ``owt_to_tvdss`` (and their TWT equivalents) previously resolved a
  repeated (tied) value on the axis being inverted by silently keeping
  whichever tied row appeared first in the Depth-conditioned table and
  discarding the other (``p2mem.time_depth._build_strictly_increasing_
  table``, REMOVED) - an ORDER-DEPENDENT tie-break with no audit trail
  beyond a bare count. This is replaced by ``build_axis_conditioned_
  lookup_table``/``build_axis_conditioned_tables_for_well``: an explicit,
  ORDER-INVARIANT policy that groups every tied value by exact equality
  regardless of parse order, registers every tied row in a new typed
  audit register (``AxisTimeDepthTieRegisterEntry`` /
  ``checkshot_time_axis_tie_register.csv`` - separate from, and never
  confused with, the pre-existing Depth-axis ``DuplicateTieRegisterEntry``
  register), and uses the tied group's dependent-value MEDIAN as the
  conditioned representative (order-invariant; disclosed as reducing to
  the arithmetic mean for the size-2 groups observed in this project's
  real data). A genuine reversal (not a tie) in the axis being inverted
  raises ``TimeDepthError`` rather than being sorted, discarded, or forced
  monotonic. (2) ``INCREMENT_04_MANIFEST.md``'s statement that TVDSS is
  strictly increasing after Depth-tie conditioning for all three wells was
  INCORRECT - independently reproduced counts (Poseidon 2: two TVDSS-axis
  and two OWT-axis ties; Boreas 1: one TVDSS-axis tie, zero OWT-axis ties;
  Proteus 1ST2: none of either) are now documented in
  ``INCREMENT_04_1_MANIFEST.md`` and reflected in this module's own
  docstrings. (3) ``trapezoidal_integrate`` and (4) ``compute_sonic_
  checkshot_drift`` are hardened to validate their numerical
  preconditions (finite, one-dimensional, equal-length, strictly
  increasing MD/x where required) rather than silently integrating
  invalid input - most notably, a decreasing or duplicate MD run can no
  longer silently produce a physically invalid NEGATIVE transit time; it
  now raises ``TimeDepthError``. None of this hardening changes the
  already-verified real Poseidon 2 sonic-drift result, which is
  bit-for-bit unchanged. See ``INCREMENT_04_1_MANIFEST.md`` for the full
  audit, corrected statistics, and re-verification record.

* Increment 4.1.1 is a narrowly scoped numerical-validation corrective
  patch to Increment 4.1, applied after an independent numerical-method/
  software-QA audit, WITHOUT beginning Increment 5 or any formation-top/
  petrophysics/pore-pressure/mechanical-properties/stress/wellbore-
  stability work. It corrected four blocking defects and one input-safety
  gap, none of which altered any previously verified REAL Poseidon
  2/Boreas 1/Proteus 1ST2 result: (1) ``build_axis_conditioned_lookup_
  table`` grouped ALL occurrences of an identical axis value together
  GLOBALLY before checking for a reversal, so a reversal that returned to
  an already-seen value (e.g. ``[100.0, 200.0, 100.0]``) was silently
  hidden rather than raising ``TimeDepthError`` - it now evaluates the
  ORIGINAL, ungrouped sequence's successive differences for negativity
  BEFORE any grouping is attempted, which is provably equivalent to the
  4.1 behavior for every legitimate adjacent tie and strictly stronger
  against a non-adjacent reversal. (2) ``compute_sonic_checkshot_drift``/
  ``find_longest_finite_positive_run`` validated MD monotonicity only
  within the selected finite-positive-VP run, so a decreasing or
  duplicate MD value outside that run (e.g. at a NaN-VP station) could
  pass silently - the COMPLETE canonical ``md_m`` array is now required
  finite and strictly increasing before run-selection (the real Poseidon
  2 MD array, 31,897 samples, was independently re-verified to already
  satisfy this). (3) ``compare_checkshot_to_survey`` reached an untyped
  NumPy ``ValueError`` ("zero-size array to reduction operation") if
  every checkshot Depth row fell outside the locked survey's own MD
  coverage - it now raises a typed ``TimeDepthError`` naming the well,
  the checkshot Depth range, and the survey MD coverage. (4)
  ``p2mem.io.checkshot.load_checkshot_surveys`` did not catch
  ``TimeDepthError`` raised during numerical conditioning, so a defect in
  one well's data could stop the entire batch - it is now caught per well
  (never via a blanket ``except Exception``) and recorded as a typed
  ``CheckshotIngestionFailure(error_type="numerical_conditioning_
  failure")``, isolated exactly like every other expected per-well
  failure. (5) ``seconds_to_milliseconds``/``milliseconds_to_seconds``
  coerced their input directly, unlike ``p2mem.units``'s Increment-1
  input-safety policy, so a boolean, numeric-looking string, or complex
  value would be silently reinterpreted rather than rejected - both now
  reject such input with ``TypeError`` via a local, documented copy of
  ``p2mem.units``'s identical private dtype check (``p2mem/units.py``
  itself remains LOCKED and unmodified). See
  ``INCREMENT_04_1_1_MANIFEST.md`` for the full audit, the regression-test
  list, and the re-verification record.

* Increment 5 adds contract-driven formation-top ingestion, HRS-versus-
  selected-readable source RECONCILIATION, and survey-corrected
  stratigraphic depth mapping (``p2mem.top_models``, ``p2mem.io.tops``,
  ``p2mem.io.tops_inventory``) for the two approved wells with formation-
  top data (Poseidon 2, Boreas 1). Each well has TWO independently
  supplied top files - an "HRS" file (``Top_Name``/``MDRT_m`` only, no
  well name in the file body) and a "selected readable" file
  (``TOP_NAME``/``MDRT_M``/``TVDSS_M``/``NOTE``, with ``#``-comment
  headers and a dashed separator line, deliberately parsed rather than
  treated as data) - and neither is silently preferred: markers are
  matched by exact/normalized name or an explicit human-authored alias
  contract (never fuzzy matching), and MDRT is cross-checked between the
  two sources within a documented 0.005 m tolerance; a marker on which
  the two sources disagree beyond that tolerance is excluded from depth
  mapping (``mapping_status == "not_mapped_mdrt_unresolved"``) rather
  than resolved by picking one file. Reconciled MDRT is mapped through
  the LOCKED Increment 3.1.1 ``petrel_source_trace`` survey trajectory
  using the existing, unmodified ``p2mem.depth_mapping.
  map_las_md_to_tvd_tvdss`` (per marker, so one out-of-coverage marker
  never blocks the rest of the well; extrapolation is never performed),
  producing ``TVD_survey_m``/``TVDSS_survey_corrected_m`` alongside an
  explicit, unambiguous ``TVDSS_residual_source_minus_survey_m =
  TVDSS_source_m - TVDSS_survey_corrected_m`` residual field. Both file
  representations for both wells are classified
  ``well_identity_evidence_status = "inferred_unverified"`` (filename-only
  or in-file-comment association, never independently content-verified -
  a more conservative classification than Increment 4's checkshot files).
  Poseidon North 1 and Proteus 1ST2 have no approved formation-top file
  and are recorded as ``FormationTopAvailabilityRecord(..., "NOT_
  AVAILABLE")`` - never substituted or depth-correlated from another
  well. Independently recomputing (never hardcoding) this increment's two
  required regression findings against the real approved files confirmed:
  Poseidon 2's "selected readable" file's supplied TVDSS equals
  ``MDRT - 21.8 m`` EXACTLY for every one of its 9 markers (21.8 m is the
  well's own rotary-table elevation) - a literal vertical-well-assumption
  depth-reference defect, corrected in the derived
  ``TVDSS_survey_corrected_m`` representation while the raw
  ``TVDSS_source_m`` column is preserved unmodified; survey-corrected
  residuals reproduce Sea Bed at ~0 m, Plover Fm (Top Reservoir) at
  +1.68 m, and TD at +2.49 m, exactly as the approved Rev 1 design
  anticipated. Boreas 1's supplied TVDSS does NOT follow that pattern and
  its maximum absolute source-versus-survey residual is 0.0416 m, below
  the approved 0.05 m tolerance - confirming it was generated from the
  well's real surveyed trajectory, not a vertical-well shortcut, and it is
  therefore NOT "corrected" the way Poseidon 2 is. See
  ``INCREMENT_05_MANIFEST.md`` for the full audit, the per-file contracts,
  and the complete reconciliation/mapping results.

* Increment 5.1 is a narrowly scoped corrective patch to Increment 5,
  applied after an independent technical/software-QA audit, WITHOUT
  beginning Increment 6 or any petrophysics/pore-pressure/mechanical-
  properties/stress/wellbore-stability work, and WITHOUT changing any
  previously verified real Poseidon 2/Boreas 1 formation-top result. It
  corrected three defects and one documentation-accuracy gap: (1)
  ``reconcile_formation_top_sources`` documented "zero canonical markers
  in common between the two sources" as a fatal ``NO_COMMON_MARKERS``
  ERROR, but actually tested the emptiness of the UNION of both sources'
  canonical names - so two entirely DISJOINT, non-empty marker sets (e.g.
  HRS names sharing nothing with the readable file's names) were silently
  accepted as one-sided ``NOT_COMPARABLE`` entries instead of being
  rejected; the check now explicitly evaluates the INTERSECTION of the two
  sources' canonical names and raises the documented ERROR (and
  ``load_formation_top_well`` consequently raises
  ``TopSourceReconciliationError``) whenever both sources are non-empty but
  share nothing, while a legitimate one-sided marker (with at least one
  marker genuinely shared) remains the pre-existing, non-fatal
  ``NOT_COMPARABLE`` case. (2) ``load_formation_top_surveys`` recorded only
  the HRS file's path in every ``TopIngestionFailure.source_path``,
  regardless of which file/stage actually failed - so a failure originating
  from the "selected readable" file (missing file, malformed content, or a
  contract mismatch) could leak that file's own absolute path, unsanitized,
  into exported issues/availability/manifest rows (the sanitizer only ever
  stripped the recorded, and in that case WRONG, HRS path).
  ``TopIngestionFailure`` now carries an explicit ``failure_origin``
  ("hrs"/"readable"/"reconciliation"/"mapping"/"unknown") and both
  ``hrs_path``/``readable_path`` fields, ``load_formation_top_well`` tags
  each raised exception with the stage that actually failed, and every
  exporting function in ``p2mem.io.tops_inventory`` now sanitizes BOTH
  candidate paths (literal substring replacement only, never a regex) and
  reports the correctly identified failing file's basename as context. (3)
  ``reconcile_formation_top_sources`` - the public in-memory API, as
  distinct from the file parsers, which already enforced this - did not
  validate its own documented contract before any numerical comparison:
  non-finite (NaN/Inf) or negative MDRT/TVDSS values, a shorter
  ``NOTE_source`` tuple (previously reaching an untyped ``IndexError``), a
  non-1-dimensional array, and an unvalidated ``mdrt_agreement_tolerance_m``
  keyword (previously accepting ``NaN``, a negative value, or a boolean,
  reaching an incidental ``TypeError`` only for a string) were all silently
  accepted or reached an undocumented incidental error. All of these are
  now rejected before any comparison, with deliberate, documented
  exceptions (``TopParsingError`` for a value/structural defect,
  ``TypeError`` for a type-class defect - matching this module's existing
  split), while valid Python ``int``/``float`` and NumPy integer/floating
  scalars (including 0-d/size-1 arrays) continue to work. (4)
  ``INCREMENT_05_MANIFEST.md`` stated that no ``/home/``, ``/root/``,
  ``/content/``, or absolute path exists ANYWHERE in the package - this was
  inaccurate, since existing synthetic tests and historical documentation
  intentionally contain fake absolute-path strings as test inputs; the
  precise, narrowly scoped claim ("no environment-dependent build path
  appears in exported CSV/JSON outputs") is now stated explicitly in
  ``INCREMENT_05_1_MANIFEST.md``, which also acknowledges the prior
  wording was overbroad. ``INCREMENT_05_MANIFEST.md`` itself is a locked
  historical record and is NOT rewritten. See ``INCREMENT_05_1_MANIFEST.md``
  for the full audit, the regression-test list, and the real-data
  non-regression verification record.

* Increment 5.1.1 is a further narrowly scoped corrective patch to
  Increment 5.1, applied after an independent technical/software-QA audit,
  WITHOUT beginning Increment 6 and WITHOUT changing any scientific result,
  tolerance, depth-mapping method, or formation-top contract. It corrected
  one remaining reconciliation edge case and three documentation-accuracy
  gaps. (1) Increment 5.1 correctly rejected two non-empty, disjoint
  marker sets as a fatal ``NO_COMMON_MARKERS`` ERROR, but its condition
  (``both sources non-empty AND intersection empty``, plus a separate
  both-empty case) still silently accepted the remaining zero-common-
  markers configuration: exactly ONE source entirely empty and the other
  non-empty - the intersection of an empty set with anything is itself
  empty, so this was still a zero-common-markers condition, but the
  ``hrs_by_canon and readable_by_canon`` non-empty guard skipped it.
  ``reconcile_formation_top_sources`` now uses the single, strictly
  correct check ``if not common_markers`` (the intersection of the two
  sources' canonical names), which is empty in every zero-common-markers
  configuration - both empty, either side alone empty, or both non-empty
  and disjoint - and is never empty whenever at least one canonical marker
  is genuinely shared, so a legitimate one-sided marker alongside at least
  one shared marker remains the pre-existing, non-fatal ``NOT_COMPARABLE``
  case. (2) ``INCREMENT_05_1_MANIFEST.md`` stated that the real Increment
  5 baseline ZIP's SHA-256 "matches" a governing-prompt-supplied hash that
  was, in fact, a two-character truncation of the real 64-character value
  - a mathematical impossibility that is now stated transparently in
  ``INCREMENT_05_1_1_MANIFEST.md`` as a documentation/input typo, never as
  baseline corruption or uncertainty. (3) ``INCREMENT_05_1_MANIFEST.md``
  Section 7 stated that ``outputs/`` is excluded from the delivered ZIP;
  this was false - the delivered Increment 5.1 ZIP packages the
  ``outputs/`` tree (including the byte-identical Increment 5 formation-
  top outputs/figures) exactly as every prior increment's ZIP has; only
  the dev-only regenerated-comparison directories and private raw source
  files are excluded, and this is now stated accurately. (4) the same
  manifest's clean-room section stated that no ``*.las`` file exists in
  the package; this was false because small, intentionally packaged
  synthetic LAS/checkshot/deviation/top fixtures exist under
  ``tests/fixtures/`` for portable testing - the corrected wording
  distinguishes these fictional fixtures (never leaked private data) from
  the genuinely excluded real/private project LAS, deviation, checkshot,
  and formation-top source files. See ``INCREMENT_05_1_1_MANIFEST.md`` for
  the full audit, the regression-test list, and the real-data
  non-regression verification record.

Increment 6 (this release, v0.6.0) adds the gamma-ray QC, shale-proxy
sensitivity, well-frame assembly, and method-eligibility framework, on top
of the LOCKED Increment 1-5.1.2 foundation (no locked module, config,
test, fixture, notebook, output, or figure is modified by it). It
contributes:

* ``p2mem.wellframe_models`` / ``p2mem.wellframe`` - a typed, auditable
  per-well assembly of the locked canonical LAS curve arrays alongside the
  locked MD->TVD/TVDSS mapping, with per-sample validity masks, per-curve
  provenance, QC flags, and evidence classification. Sample count and
  order are preserved exactly; invalidity is expressed only through masks;
  no depth is ever extrapolated (a LAS sample outside the survey's own MD
  coverage is recorded as depth-unmapped, never clamped or held).
* ``config/petrophysics_eligibility.yml`` - the human-authored, reviewable
  per-well gamma-ray-family disposition, endpoint-sensitivity policy, and
  eligibility rules. Boreas 1 is formally excluded from every
  lithology-dependent, GR-normalized, shale-proxy and NCT-candidate
  calculation under the machine-readable reason
  ``BOREAS_ECGR_SCALE_UNRESOLVED``; it is EXCLUDED, never corrected or
  rescaled, because no calibration evidence exists to support any
  correction.
* ``p2mem.petrophysics_models`` / ``p2mem.petrophysics`` - factual
  GR-family QC statistics for every well (including excluded ones),
  per-well low/base/high endpoint scenarios whose measured endpoint values
  are recorded, and the dimensionless GR index with clipped and unclipped
  results retained side by side. The only permitted shale-proxy transform
  is the linear identity of the clipped index, exported under the
  self-labelling name ``VSH_GR_linear_proxy_frac``; every nonlinear Vsh
  transform (Larionov, Clavier, Stieber, ...) is deliberately DEFERRED
  pending a retrieved, verified primary-source method record.
* ``p2mem.method_eligibility`` - three input-admissibility masks
  (``eligible_density_for_sv``, ``eligible_dynamic_elastic``,
  ``eligible_sonic_nct_candidate``) plus contiguous-interval registers on
  MD/TVD/TVDSS with explicit, configured, tested gap tolerances that
  distinguish sample-count continuity from physical-depth continuity.
  ELIGIBILITY IS NOT VALIDITY: none of the gated methods is implemented,
  fitted, or validated here.
* ``p2mem.io.petrophysics_inventory`` - deterministic summary/interval/
  manifest builders that never export a per-sample real-data array and
  never emit an absolute path.

Increment 6 assigns NO named lithology anywhere. Gamma-ray response is not
uniquely diagnostic of rock type and no independent lithological evidence
exists in this project, so every classification it produces describes DATA
AND PROXY CONFIDENCE ONLY, guarded by an enforced prohibited-vocabulary
check.

Increment 6.1 (v0.6.1) is a narrowly scoped corrective patch
to Increment 6, applied after an independent geomechanics/rock-physics and
software audit. It changes no architecture and starts no new phase. Four
findings were corrected:

* **Vp/Vs terminology and boundaries.** Increment 6 labelled every excluded
  Vp/Vs ratio "non-physical" and used a strictly exclusive sqrt(2) bound.
  Both were wrong. With r = Vp/Vs, nu = (r^2 - 2) / (2 (r^2 - 1)) and
  K = rho (Vp^2 - (4/3) Vs^2), so: r = sqrt(2) gives nu = 0 EXACTLY and must
  be ACCEPTED by a non-negative-nu policy (the bound is now INCLUSIVE);
  sqrt(4/3) < r < sqrt(2) gives POSITIVE bulk modulus with negative Poisson
  ratio - unusual and outside this project's conservative policy, but not
  physically impossible; only r <= sqrt(4/3) implies a non-positive bulk
  modulus and is genuinely outside the isotropic elastic model; and r > 4 is
  a CONFIGURED PLAUSIBILITY LIMIT, not a Poisson-domain boundary (nu ~= 0.467
  there). The condition is renamed a CONFIGURED NON-NEGATIVE-POISSON-RATIO
  APPLICABILITY SCREEN, the three config bounds are separately named, and
  exclusions are diagnosed by regime (`n_ratio_nonpositive_bulk_modulus`,
  `n_ratio_positive_bulk_but_negative_poisson`,
  `n_ratio_above_configured_plausibility_max`, `n_vp_not_greater_than_vs`) -
  never aggregated under a single "non-physical" count.
* **Poseidon North 1 depth-tied status.** Its machine-readable `use_status`
  was `screening_proxy_allowed` while it has no approved formation tops,
  contradicting both the status vocabulary and the prose limitation. It is
  now `screening_proxy_allowed_depth_tied`, and a config invariant makes any
  contradictory has-tops/use-status pairing fail config loading loudly.
* **Unsupported lithology claims and a circular gate.** Project-specific
  "clastic-dominated" assertions and the unsupported "regionally persistent"
  cross-well claim are removed (two of the three GR-eligible wells have no
  approved tops, so cross-well stratigraphic persistence cannot be
  established). `clastic` and related rock-class terms join the prohibited
  vocabulary, and `named_lithology_assigned` is now DERIVED from an actual
  validation pass over every persisted label, per-well note, mask name and
  manifest statement - injecting a prohibited term makes the validation, the
  manifest flag and the completion gate fail together. Validation is
  three-tier: LABELS admit no prohibited term at all, per-well PROSE may name
  the method category ("shale proxy") but not assert a rock, and EXPLANATORY
  text may use rock names as generic examples of gamma-ray non-uniqueness
  but never in a sentence naming one of this project's wells.
* **Gross versus net/strict interval thickness.** The reported "qualifying
  thickness" summed block endpoint spans that may contain explicitly bridged
  ineligible samples. Thickness is now exported only under qualified names -
  `gross_thickness_*_m` (endpoint span, bridging-inclusive) and
  `net_thickness_*_m` (bridged gaps removed) - every mask is additionally
  decomposed under a `strict_no_gap` contiguity policy for comparison, every
  sensitivity case reports its bridged-sample and interrupted-block counts,
  and Figure 4 now draws qualifying and rejected sub-threshold blocks
  distinctly with the counted population stated.

Increment 6.1.1 (v0.6.2) is a second, narrower corrective
patch, applied after an independent audit of Increment 6.1. It starts no
new phase, changes no architecture, and alters no configured tolerance,
threshold, or qualifying-block policy. Five findings were corrected:

* **Named-lithology validator bypass.** The method-term allowlist that lets
  per-well prose name a METHOD ("shale proxy") contained "shale gas", which
  is not a method-category phrase but can be a direct geological/hydrocarbon
  assertion; sentences such as "This interval contains shale gas." therefore
  passed with zero violations. The allowlist is reduced to the two phrases
  that are genuinely method/quantity names required to describe this
  project's boundaries - ``shale proxy`` and ``shale volume`` - and the
  allowance is now evaluated PER SENTENCE and suppressed entirely in any
  sentence carrying a geological-assertion cue (``contains``, ``comprises``,
  ``bearing``, ``facies``, ...) or where the phrase is immediately preceded
  by a quantity cue (``has a high shale volume``). Regression tests prove
  the allowlist can no longer hide a geological assertion and that injecting
  either bypass case into manifest content makes ``named_lithology_assigned``
  true, ``lithology_validation.n_violations`` non-zero, and the completion
  gate fail.
* **Stale Vp/Vs scientific description.** The active top-level docstring of
  ``p2mem.method_eligibility`` still described the screen as keeping samples
  within the Poisson domain under a strictly EXCLUSIVE sqrt(2) ratio bound,
  contradicting the corrected implementation. It now states the configured
  non-negative-Poisson-ratio applicability screen with an INCLUSIVE
  ``Vp/Vs >= sqrt(2)`` bound and says explicitly that this is neither a
  physical-possibility test nor a boundary of the mathematical Poisson
  domain. A regression test asserts the corrected wording against the live
  module documentation.
* **Ambiguous interruption counts.** ``n_interruptions`` was a boolean-like
  flag reported as a count (always 1 for every bridged block), and
  ``n_interrupted_subruns`` did not describe what it counted. Interval
  records now carry three separately named, independently meaningful
  quantities: ``n_bridged_samples`` (ineligible samples absorbed inside the
  gross block), ``n_bridged_gaps`` (distinct bridged runs) and
  ``n_eligible_subruns`` (strictly contiguous eligible sub-runs), with the
  identity ``n_bridged_gaps == n_eligible_subruns - 1`` enforced at
  construction. The ambiguous aliases are gone from all active exports.
* **Notebook output-count error.** The notebook creates and checks eight
  deterministic CSV/JSON outputs but its gate text and printed label said
  seven. Both now say eight, and the gate asserts both the declared count
  and the existence of all eight files. Four figures remain separate,
  giving twelve outputs/figures in total.
* **Incorrect Increment 6.1 delta arithmetic.** The Increment 6.1 completion
  record stated "Changed (12)"; a clean recursive comparison gives 18
  changed, 3 added and 0 removed (21 path differences). That statement is
  explicitly superseded - not silently rewritten - in the Increment 6.1.1
  manifest and completion record, which report both measured deltas file by
  file.

Increment 6.1.2 (v0.6.3) is a third corrective patch, applied
after an independent audit of Increment 6.1.1. It starts no new phase, changes
no architecture, alters no scientific threshold, tolerance, endpoint scenario,
contiguity policy, GR disposition, depth-mapping rule, or real-data
interpretation, and adds no runtime dependency (NumPy and PyYAML remain the
only two). Two residual findings were corrected:

* **The named-lithology validator was bidirectionally incorrect.** Increment
  6.1.1 decided the method-phrase allowance from a SENTENCE-WIDE assertion-cue
  list plus a fixed LOOK-BEHIND window. Both were structurally wrong. Because
  nothing to the RIGHT of an allowed phrase was ever inspected, and because
  the normalizer destroyed possessives, direct assertions such as "Poseidon
  2's shale volume is high.", "Poseidon 2's shale volume is 70 percent." and
  "The interval's shale volume exceeds 60 percent." passed with ZERO
  violations. Conversely, because a sentence-wide cue fires without asking
  what the cue word is predicated OF, legitimate method and boundary
  statements such as "This method contains a shale proxy calculation." and
  "The analysis shows no shale volume was computed." were reported as
  lithological assertions. The allowance is no longer a property of the
  sentence: it is decided for EACH OCCURRENCE of an allowed phrase from that
  occurrence's own local grammar - whether it is possessed by a geological
  entity (``the interval's shale volume``), modified by a magnitude (``a high
  shale volume``), predicated with an amount or a dominance (``is 70
  percent``, ``exceeds 60 percent``, ``dominates the interval``), or sits in a
  sentence whose composition verb takes a GEOLOGICAL subject (``the unit
  comprises ...``, but not ``this method contains ...``). Apostrophes and
  possessives are parsed rather than erased, sentence boundaries include line
  breaks, and genuinely ambiguous project-specific sentences fail closed.
  ``SCOPE_LABEL`` remains absolute: a label gets no latitude at all.

* **Interval-record invariants were only partially enforced.** Increment 6.1.1
  claimed the interruption-count identities were enforced at construction, but
  the only check was ``n_bridged_gaps == n_eligible_subruns - 1``, skipped
  whenever either value was ``None`` or ``n_eligible_subruns`` was 0. Records
  with missing counts, negative counts, zero sub-runs, boolean counts, or
  bridged samples without a bridged gap were all constructible. All three
  counts are now validated together as one coherent record: each is required,
  must be a true integer count (booleans, strings, complex values and
  fractional floats are rejected, never coerced), ``n_bridged_samples >= 0``,
  ``n_bridged_gaps >= 0``, ``n_eligible_subruns >= 1``, ``n_bridged_gaps ==
  n_eligible_subruns - 1``, ``n_bridged_samples == 0`` if and only if
  ``n_bridged_gaps == 0``, and ``n_bridged_samples >= n_bridged_gaps`` because
  every distinct gap holds at least one sample. Each violation raises
  ``PetrophysicsInputError`` naming the offending field or relationship, and
  the removed ``n_interruptions`` / ``n_interrupted_subruns`` field names are
  rejected outright rather than silently ignored.

Every scientific result is unchanged by this patch: the same eight
deterministic outputs and four figures are produced, byte for byte.

Increment 6.1.3 (v0.6.4) is the fourth and architectural
corrective patch, applied after an independent audit of Increment 6.1.2. It
starts no new phase, changes no scientific threshold, tolerance, endpoint
scenario, contiguity policy, GR disposition, depth-mapping rule, or real-data
interpretation, and adds no runtime dependency (NumPy and PyYAML remain the
only two).

**The validator no longer tries to understand English.** Increments 6.1.1 and
6.1.2 each attempted to decide, from grammar, whether a sentence containing a
rock name was NAMING A METHOD or ASSERTING GEOLOGY - 6.1.1 with a
sentence-wide cue list and a fixed look-behind window, 6.1.2 with
per-occurrence possessive/modifier/predicate/subject analysis. Both were
audited and both failed in BOTH directions. 6.1.2 still missed "The interval
has a shale volume.", "The shale volume in Poseidon 2 exceeds 60 percent." and
"Poseidon 2 shale volume was determined to be high.", while wrongly rejecting
"The well contains no shale volume estimate." Every one of those is a list gap
or a window edge. The lesson is not that the lists were too small: free-text
geological-assertion detection is unbounded, and no finite grammar closes it.

Increment 6.1.3 replaces judgement with membership. Every scope is now decided
by set membership or exact equality:

* ``SCOPE_LABEL`` - verdicts. Zero allowance.
* ``SCOPE_INTERPRETIVE`` - project-specific prose. **ZERO ALLOWANCE.** There is
  no exemption path at all, so there is nothing to bypass. The
  ``allow_method_phrases`` parameter is gone.
* ``SCOPE_METHOD`` (new) - method and limitation statements. The text must
  EQUAL a member of the closed, provenance-tagged ``METHOD_STATEMENTS``
  registry. Not matched, not scored - equal. The registry has five members,
  measured rather than guessed by scanning every string literal in active
  packaged source and every persisted field under a zero-allowance rule.
* ``SCOPE_EXPLANATORY`` - generic scientific text. A rock name is permitted
  only when the sentence refers to no project well AND no project rock body.
  6.1.2 checked well names alone, which is why an assertion about "the
  interval" behaved inconsistently between scopes.

The deletion is the correction: ``ALLOWED_METHOD_TERM_PHRASES``,
``GEOLOGICAL_ENTITY_TOKENS``, ``COMPOSITION_PREDICATES``,
``MAGNITUDE_PREDICATES``, ``MAGNITUDE_WORDS``, ``COPULAR_VERBS``,
``ATTRIBUTIVE_ROCK_TOKENS``, ``NEGATION_TOKENS``, the look-behind and
look-ahead windows, subject resolution and occurrence classification are all
GONE, and a regression test asserts none of them is importable. Correctness is
proved by CLOSURE - every prohibited term, in every position, inside carrier
prose built from the exact constructions that defeated both previous
implementations - not by a list of example sentences.

This patch also closes a gap neither audit reported: three strings this project
WRITES INTO PACKAGED EXPORTS had never been inside the validated scope in any
increment, including a ``calibration_status`` value literally containing
``not_a_shale_volume`` persisted to every row of
``gr_proxy_sensitivity_summary.csv``. All three are now scanned in
``SCOPE_METHOD``, which raises ``n_fields_checked`` from 138 to 143.

**Interval-record type gate.** Increment 6.1.2 enforced the relational rules
but let three type defects through: ``0.0 / 0.0 / 1.0`` was accepted although
the contract requires integers; ``NaN`` and ``Inf`` escaped as bare
``ValueError`` / ``OverflowError`` from ``int()``; and an unknown keyword such
as a misspelled count name was silently ignored, leaving the real count unset.
Keyword acceptance is now a WHITELIST over the declared slots, floats are
rejected outright including whole-valued ones, and non-finite values raise a
typed ``PetrophysicsInputError`` before any conversion is attempted.

All eleven scientific outputs and figures are byte-identical to Increment
6.1.2; only the manifest changes, by the single scalar named above.

Increment 6.1.4 (v0.6.5) completes the architecture Increment
6.1.3 began. It is deliberately narrow: one scope rule, no other change.

Increment 6.1.3 closed LABEL and INTERPRETIVE by removing every exemption and
closed METHOD by exact registry membership - but left EXPLANATORY decided by a
FINITE TOKEN LIST of project references. That is the same shape of rule that
failed in 6.1.1 and 6.1.2, and it had the same defect. Ordinary stratigraphic
and exploration nouns were absent from the list, so in explanatory scope

    "The member is shale."               passed
    "The group is limestone."            passed
    "The package is a clean sandstone."  passed
    "The play is shale-dominated."       passed
    "The prospect is carbonate."         passed
    "The target is sandstone."           passed

while "The upper member is a clean sandstone reservoir." failed only because
``reservoir`` happened to be listed - an accident, which is what a list-shaped
rule produces.

The rule is INVERTED and made identical in kind to SCOPE_METHOD: explanatory
text carrying a prohibited term is a violation UNLESS the text is a member of
the closed ``GENERIC_EXPLANATORY_STATEMENTS`` registry. It FAILS CLOSED, so no
vocabulary gap can admit anything. ``PROJECT_WELL_NAME_TOKENS``,
``PROJECT_ROCK_BODY_TOKENS`` and ``PROJECT_REFERENCE_TOKENS`` are deleted, and
a regression test asserts none of them is importable. Nothing in the validator
now enumerates what a project reference looks like.

The generic registry is **empty**, as a measured fact rather than an omission:
this project persists exactly one explanatory field,
``manifest.named_lithology_statement``, and it carries no prohibited term at
all. The mechanism is nevertheless live and tested, because later increments
explaining gamma-ray non-uniqueness may genuinely need to write "a clean
sandstone and a clean limestone read alike on GR" - and when they do, that is
a registered, reviewable statement rather than a sentence admitted by shape.

All four validation scopes are now closed by membership or exact equality, and
the closure proof covers all of them. All twelve outputs and figures are
byte-identical to Increment 6.1.3.

Increment 6.1.5 (v0.6.6) replaces blacklist-based acceptance
with POSITIVE AUTHORIZATION, and is the final Increment 6 corrective patch.

Increments 6.1 through 6.1.4 all asked the same question in different ways:
"does this text contain a geological assertion?" All four shared one
structural assumption - that content is ACCEPTABLE BY DEFAULT and becomes
unacceptable only when a recognizer fires - and all four were defeated,
finally by a word no recognizer had been given. In the 6.1.4 package these
all passed label, interpretive and explanatory scope:

    "The interval is chalk."         "The interval is chert."
    "The interval is halite."        "The interval is tuff."
    "The interval is gypsum."        "The interval is basalt."
    "The interval is conglomerate."  "The interval is dolostone."
    "The interval is lignite."       "The interval is calcareous."

and so did "The interval is qxzite.", a word that does not exist. They already
failed in METHOD scope, which was the only scope then requiring registration -
and that is the clue this patch acts on. A longer blacklist would have caught
the first ten and still missed the eleventh, so lengthening it is neither a
completion criterion nor the mechanism this package's assurance rests on.

The model is inverted. Nothing is acceptable by default:

* ``SCOPE_LABEL`` - the value must be a member of ``APPROVED_LABELS``, a
  registry of typed, enumerated label values each declaring its field kind,
  purpose and provenance. Arbitrary caller-supplied label text is rejected
  even when it contains no recognizable rock name at all.
* ``SCOPE_INTERPRETIVE`` - the text must resolve to a registered
  ``statement_id``, or to a reviewed ``template_id`` whose substitutions are
  strictly typed. Unregistered free text is rejected unconditionally.
* ``SCOPE_METHOD`` - the text must resolve to a registered ``statement_id``,
  and the id and the exact rendered text are validated TOGETHER, so neither a
  renamed id nor an edited sentence passes on the strength of the other.
* ``SCOPE_EXPLANATORY`` - identical, for every non-empty statement, whether or
  not any prohibited term is detected. The early-pass behaviour equivalent to
  "if no prohibited term is found: accept" is gone from every scope.

The registries were MEASURED from the actual persisted Increment 6 export, not
designed: 17 approved label values, 17 registered statements (11 interpretive,
5 method, 1 explanatory) and 1 controlled template covering the three per-well
confidence rationales, whose only variable parts are three decimal literals.
Every registered entry carries a stable id, its scope, its exact text or
controlled template, a scientific purpose, a provenance justification, and its
permitted typed substitutions. Duplicate ids fail at import.

``PROHIBITED_LITHOLOGY_TERMS`` survives ONLY as a supplementary diagnostic
linter. It authorizes nothing, and it is never cited as evidence that all
named lithologies have been detected - it cannot be: its 28 terms include
neither ``chalk`` nor ``chert`` nor ``qxzite``, and every rejection listed
above happens with that linter returning empty.

THE DEFENSIBLE ASSURANCE STATEMENT, which supersedes the wording of every
earlier Increment 6 manifest: every persisted project-specific classification
and interpretive statement is generated from an approved typed value, a
controlled template, or a registered statement, and arbitrary free text cannot
enter these controlled fields. This is NOT a claim that the software
understands or exhaustively recognizes natural-language lithology; it does
not, and no earlier version did. Free-form notebook narrative and
documentation lie outside these controlled fields and remain subject to
ordinary manual scientific review.

All twelve outputs and figures are byte-identical to Increment 6.1.4.

Increment 6.1.6 (previous corrective patch, v0.6.7) enforces authorization at the EMISSION
BOUNDARY. Increment 6.1.5's positive-authorization model was sound but was
applied to a scope the manifest builder RECONSTRUCTED from dispositions,
confidences and masks - a parallel object, not the records written to disk. A
`GrEndpointScenario` carrying `description="The interval is chalk."` was
persisted verbatim by `build_gr_endpoint_scenario_rows()` while never entering
that 143-field scope, so it could not move `named_lithology_assigned`. The unit
validator was closed; the export path was not.

Five findings, all reproduced first:

* **Exported endpoint description bypass** - closed. The row builder now
  authorizes the value it is about to place in the record and raises
  ``PetrophysicsInputError`` if it cannot.
* **Incomplete output coverage** - closed. ``p2mem.io.output_policy`` declares a
  category for EVERY string column and JSON path of all eight artifacts (105
  entries). Nothing is unclassified; unknown artifacts, columns, JSON paths and
  categories fail closed. Categories: structural enum, identifier, filename,
  typed label, registered statement, controlled template, structured diagnostic,
  sanitized diagnostic. There is no general category admitting arbitrary prose.
* **Field-kind label mismatch** - closed. ``APPROVED_LABELS`` is keyed by
  ``(field_kind, value)``; ``use_status="GR"`` and ``mask_name="measured"`` now
  fail, the field kind is supplied by the caller and never parsed from a context
  string, and duplicate pairs fail at import.
* **Stale exported derivation** - closed. The superseded prohibited-term wording
  is replaced by a registered statement describing the model actually
  implemented, so the assurance prose is itself authorized.
* **Duplicated manifest statement** - closed. The manifest takes
  ``REGISTERED_STATEMENTS["named_lithology_statement"].text``; no second literal
  exists to diverge from it.

Export is two-stage: build the exact pre-serialization records, authorize every
string occurrence, write, then RE-READ the written bytes and authorize again.
A value mutated after authorization is caught before delivery, and nothing is
written at all if any field fails.

The assurance metrics now say what they count. ``n_fields_checked=143`` is gone;
the manifest reports ``scope_object_fields_checked`` alongside an
``emitted_field_coverage`` block giving total emitted string-field occurrences,
controlled occurrences, structural occurrences, occurrences outside the
guarantee, unclassified fields, unauthorized fields and field-kind mismatches.
Machine diagnostics and the operator-facing issue text are counted separately
and are explicitly OUTSIDE the controlled-interpretation guarantee.

All seven CSV artifacts and all four figures are byte-identical to
Increment 6.1.5. ``petrophysics_eligibility_manifest.json`` changes, and only
inside ``lithology_validation``: the derivation is corrected and the coverage
metrics become truthful. No numerical, disposition, mask, threshold or depth
value moves.

Increment 6.1.7 (this release, v0.6.8) corrects the remaining export-boundary
assurance defect. Increment 6.1.6 discovered fields from non-empty string
values, so missing controlled columns, empty or numeric-looking controlled
strings, non-string substitutions and unknown fields with non-prose values
could escape collection. It also wrote into the official directory before the
post-write check and compared aggregate coverage counts, allowing an
authorized value to be changed into a different authorized value without
detection and leaving partial artifacts after a rejected write.

Increment 6.1.7 defines exact schemas for all eight artifacts and validates
artifact inventory, ordered CSV columns, JSON keys, requiredness, strict types
and finite numerics independently of prose authorization. Every schema-declared
string occurrence is then authorized, including empty and numeric-looking
strings. Candidate files are written only to an isolated sibling directory,
re-read and re-validated, and every typed field and row is compared against the
authorized pre-serialization record before failure-atomic publication. Unknown
well identifiers, stale output artifacts, serializer failures, field additions
or deletions, row reordering, type changes and authorized-to-authorized value
changes all fail closed while leaving the official destination unchanged.
This is failure-atomic for handled process errors; it is not a claim of
multi-file atomicity across power loss or operating-system failure.

Increment 6.1.7 is now LOCKED. Every module, config, test, fixture, notebook,
manifest, ledger, output and figure it delivered is byte-identical in this
release; the only pre-existing files that change are this module's version and
narrative, ``pyproject.toml``'s version, and ``README.md``.

Increment 7 / 7.0.1 / 7.0.2 / 7.0.3 / 7.0.4 (this release, v0.7.4) adds DENSITY QC,
DENSITY-COVERAGE QUALIFICATION, and a VERTICAL OVERBURDEN-STRESS FRAMEWORK.

Increment 7.0.1 is a narrowly scoped corrective patch. It makes profile
truncation disposition-driven so every unresolved internal gap stops the
integral, including a short gap left unresolved because bridging is disabled
or a bridge precondition fails. It also rejects coercible non-numeric scalar
inputs and malformed closed configuration vocabularies. The 10 m bridge
threshold is documented as a sensitivity-tested heuristic rather than a
mathematical error bound, and the shallow-column endpoints are labelled as
conditional/illustrative scenarios rather than physical bounds.

Increment 7.0.2 is an assurance-only corrective patch. It fixes the completion
gate's scenario-basis lookup so the gate reads the emitted
``assumed_density_basis`` field declared by the real CSV schema, and it makes
the public frozen ``OverburdenConfig`` constructor enforce the same strict
types, finite numerics, closed vocabularies and internal invariants as the YAML
loader. This closes bypasses through direct construction and
``dataclasses.replace`` without changing any scientific input, calculation,
threshold, eligibility result or output artifact.

Increment 7.0.3 closes one configuration-to-computation provenance defect.
The high shallow-column scenario is implemented from the explicitly stored
same-well P05 density statistic, so ``scenario_high_percentile`` is now
required to equal exactly 5.0 at both YAML loading and public constructor
entry points. Earlier releases accepted other percentile labels even though
the calculation continued to use P05. The packaged configuration already
uses 5.0, so no scientific input, calculation, threshold, eligibility result,
CSV/JSON artifact or figure changes in this patch.

Increment 7.0.4 is a final corrective patch following an independent audit of
the full data and publication paths. The high shallow-column endpoint now uses
the P05 of the eligible integration population, not all finite density values;
per-call gap thresholds and all threshold-bearing records reject boolean,
textual, complex, negative and non-finite values; scenario totals disclose
assumed, conditioned and measured fractions that sum to one; the locked seabed
reader fails closed on missing, malformed, duplicate or non-finite matching
rows; and the JSON exporter writes explicit UTF-8 LF bytes on every platform.
The four approved wells have identical finite and eligible RHOB populations,
zero bridged contribution in the two published scenario wells, and a valid
unique seabed table, so the measured scientific values remain unchanged. The
assurance JSON and scenario/QC schemas change to state these contracts
truthfully. Increment 7.0.4 is now LOCKED.

What it does
------------
* ``config/overburden_stress.yml`` - the human-authored screening policy: the
  bulk-density plausibility band, the gap-conditioning threshold, standard
  gravity, the assumed seawater density, and the shallow-column scenarios. No
  well name appears anywhere in it.
* ``p2mem.overburden_models`` - typed records and the closed vocabularies for
  gap classes, gap dispositions, overburden statuses, limiting reasons, seabed
  bases and scenario names, with constructor-level invariants that refuse an
  incoherent record (a bridged shallow gap, a total reported while a component
  is unresolved, a gap count that disagrees with its sample count, an absolute
  status carrying a limiting reason).
* ``p2mem.density_qc`` - RHOB availability, unit and conversion confirmation,
  TWELVE explicit per-sample masks, factual QC statistics, gap classification
  into the five structurally distinct cases, and gap conditioning into a
  SEPARATELY NAMED array.
* ``p2mem.overburden`` - trapezoidal integration of ``rho*g*dz`` in TRUE
  VERTICAL DEPTH, run-time verification of the project's depth-sign
  convention against each frame's own arrays, evidence-derived method
  eligibility, transparent shallow-column scenarios, and the mandatory
  gap-threshold sensitivity.
* ``p2mem.io.overburden_policy`` / ``overburden_registry`` /
  ``overburden_inventory`` / ``overburden_workflow`` - the Increment 6.1.7
  output-policy architecture GENERALIZED so its registries arrive as an
  explicit policy bundle, plus Increment 7's own nine closed artifact schemas
  and its complete field classification. The locked Increment 6 module and
  export path are untouched; a test harness runs the generalized engine over
  the locked registries and the real packaged Increment 6 records and requires
  the same decision on every occurrence.

Scientific boundaries this increment does not cross
---------------------------------------------------
An absolute vertical overburden stress requires density coverage from the
relevant datum or seabed to the evaluation depth. Where that column is not
measured, Increment 7 reports a partial measured increment or a transparent
low/base/high sensitivity spread, and NEVER a single absolute curve presented
as measured truth. No density value is clipped, rescaled, smoothed, despiked,
replaced or extrapolated; invalid samples are masked, short internal gaps may
be linearly bridged in true vertical depth into a separate array whose
contribution is reported separately, and nothing else is filled. The water
column, the unresolved shallow column and standard gravity are ASSUMPTIONS,
and every reported stress is partitioned so that measured, conditioned and
assumed contributions stay separately visible.

Increment 7 assigns NO named lithology. The density screening band, the gap
policy, the shallow-column bracket and the eligibility ladder are expressed in
physical and coverage terms, and none of them is justified by an assumed rock
type.

Increment 8.0.1 (this release, v0.8.1) is the final corrective patch to
Increment 8's PORE-PRESSURE DATA-GAP,
HYDROSTATIC-REFERENCE, and EFFECTIVE-STRESS SCREENING framework. It consumes
only packaged, checksum-locked Increment 6/7 outputs: no private raw file is
copied into the release. The hydrostatic reference is rho*g*TVDSS from a
mean-sea-level gauge datum under configured 1020/1025/1030 kg/m3 fluid-density
scenarios. Effective vertical stress is reported only as the transparent
scenario sigma'_v = Sv - alpha*Pp, pairing Increment 7 low/base/high vertical-
stress scenarios with configured Biot-alpha values 0.8 and 1.0. Only Boreas 1
and Poseidon 2 have an Increment 7 shallow-column stress scenario, so the
effective-stress calculation is withheld for Poseidon North 1 and Proteus
1ST2. No result is extrapolated or clipped.

The approved packaged input inventory contains zero RFT, MDT, DST, FIT, LOT,
XLOT or DFIT files; this does not prove that unprovided field data do not
exist. Candidate sonic intervals are
therefore retained only as readiness/sensitivity evidence. No normal-
compaction trend is selected or fitted; no Eaton, Bowers, equivalent-depth or
drilling-exponent transform is run; and no overpressure is inferred. A
hydrostatic reference is not a measured formation pressure, and the
effective-stress values are uncalibrated screening scenarios rather than
field-ready estimates.

Increment 9 (v0.9.0) adds dynamic isotropic elastic estimates from the approved
co-located Vp, Vs and RHOB samples. Primary Poisson, bulk and Young estimates
retain the inherited nonnegative-Poisson applicability screen. Stable negative
Poisson ratios remain separately named diagnostics. Shear modulus requires
only Vs and density; Poisson ratio does not require density. No gaps are filled.
Static conversion, rock strength, horizontal stress, stress calibration,
mud-window and wellbore-stability calculations remain deferred. Increment 10
has not been started. Earlier increment descriptions above are historical.
"""

__version__ = "0.12.0"

# Fixed project-wide assurance tier. Referenced by later modules (reporting,
# plotting) so that every generated output can stamp its own classification
# without each module re-declaring the string. This value must not be
# changed without a documented calibration event (e.g. a verified RFT/MDT,
# LOT/XLOT, or core-calibrated log tie) recorded in the method-and-citation
# register.
ASSURANCE_TIER = "Tier C - Screening-Level / Uncalibrated Educational"

__all__ = ["__version__", "ASSURANCE_TIER"]

# Increment 10 adds conditional analogue static/strength experiments only.
# No field eligibility, calibrated mechanics, horizontal stresses or WBS.
