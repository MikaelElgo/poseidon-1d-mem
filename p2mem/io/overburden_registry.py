"""
The Increment 7 output-policy REGISTRIES: exact closed schemas, the complete
field classification, and every statement, template and label this increment
is permitted to persist.

Kept in its own module so that `p2mem.io.overburden_policy` stays a readable
ENGINE and this file stays a readable CONTRACT. Nothing here executes logic;
everything here is a declaration that the engine enforces.

Provenance rule, inherited from the locked Increment 6.1.7 design: every entry
below is enumerated from the ACTUAL records the Increment 7 export path emits.
A statement that no artifact emits does not belong here, and an emitted string
with no entry here fails closed at the export boundary.
"""

from p2mem.io.output_policy import CsvArtifactSchema
from p2mem.wellframe_models import ApprovedLabel, RegisteredStatement, RegisteredTemplate
from p2mem.io.overburden_policy import (
    CATEGORY_ENUMERATED_CODE_LIST, FieldPolicy, OVERBURDEN_FIELD_TYPES, PolicyBundle,
    SCOPE_OUTPUT_INC7,
)
from p2mem.overburden import SIGN_CONVENTION_ID
from p2mem.overburden_models import (
    SCENARIO_BASIS_BASE, SCENARIO_BASIS_HIGH, SCENARIO_BASIS_LOW,
    VALID_GAP_CLASSES, VALID_GAP_DISPOSITIONS, VALID_LIMITING_REASONS,
    VALID_OVERBURDEN_STATUSES, VALID_SCENARIO_NAMES, VALID_SEABED_BASES,
)

__all__ = [
    "OVERBURDEN_ARTIFACTS", "OVERBURDEN_CSV_SCHEMAS", "OVERBURDEN_MANIFEST_ARTIFACT",
    "OVERBURDEN_STATEMENTS", "OVERBURDEN_TEMPLATES", "OVERBURDEN_LABELS",
    "APPROVED_WELL_KEYS", "OVERBURDEN_BUNDLE", "ISSUE_CODES", "NOT_IMPLEMENTED_TOKENS",
    "ASSURANCE_TIER_VALUE", "INCREMENT_TITLE",
]

ASSURANCE_TIER_VALUE = "Tier C - Screening-Level / Uncalibrated Educational"
INCREMENT_TITLE = "Density QC, Density-Coverage Qualification, and Vertical Overburden-Stress Framework"

OVERBURDEN_MANIFEST_ARTIFACT = "density_overburden_manifest.json"

APPROVED_WELL_KEYS = frozenset((
    "Boreas_1", "Poseidon_2", "Poseidon_North_1", "Proteus_1ST2",
))

#: Sentinel emitted in a curve-identity column when a well has no density curve.
NA_DENSITY = "not_applicable_no_density_curve"

ISSUE_CODES = (
    "DENSITY_CURVE_ABSENT",
    "DENSITY_CONVERSION_FUNCTION_UNEXPECTED",
    "SCREENING_BOUND_FAILURES_PRESENT",
    "MEASURED_MAXIMUM_NEAR_SCREENING_BOUND",
    "SHALLOW_DENSITY_COLUMN_UNRESOLVED",
    "SEABED_DATUM_UNRESOLVED",
    "LONG_INTERNAL_GAP_PRESENT",
    "TERMINAL_DENSITY_COLUMN_UNRESOLVED",
    "STRESS_COLUMN_TRUNCATED_AT_UNRESOLVED_GAP",
    "ABSOLUTE_OVERBURDEN_NOT_SUPPORTED",
    "WELL_FRAME_ASSEMBLY_FAILED",
)

NOT_IMPLEMENTED_TOKENS = (
    "pore_pressure_prediction",
    "sonic_normal_compaction_trend_fitting",
    "resistivity_normal_compaction_trend_fitting",
    "eaton_method",
    "bowers_method",
    "equivalent_depth_method",
    "drilling_exponent_method",
    "effective_stress_calculation",
    "dynamic_elastic_property_modelling",
    "static_elastic_property_modelling",
    "rock_strength_modelling",
    "horizontal_stress_calculation",
    "stress_calibration",
    "mud_window_calculation",
    "breakout_analysis",
    "tensile_fracture_analysis",
    "wellbore_stability_analysis",
    "named_lithology_assignment",
    "mineralogical_interpretation",
    "shallow_density_reconstruction_from_a_fitted_trend",
    "density_extrapolation_beyond_measured_coverage",
)

_UNIT_VALUES = (
    "kg/m3; m; Pa; MPa",
    "m",
    "kg/m3",
    "Pa; MPa",
    "count",
    "dimensionless",
)

_DEPTH_BASIS_VALUES = ("petrel_source_trace", "minimum_curvature_computed")
_DEPTH_MAP_STATUS_VALUES = (
    "fully_mapped_within_survey_coverage",
    "partially_mapped_survey_coverage_gap",
    "not_mapped_no_survey",
)
_INTEGRATION_METHOD_VALUES = ("trapezoidal_in_true_vertical_depth",)
_INTEGRATION_COORDINATE_VALUES = ("tvdss_m",)
_CURVE_NAME_VALUES = ("RHOB_kg_m3", NA_DENSITY)
_SOURCE_CURVE_VALUES = ("RHOB", NA_DENSITY)
_RAW_UNIT_VALUES = ("g/cc", "g/cm3", "G/C3", NA_DENSITY)
_CANONICAL_UNIT_VALUES = ("kg/m3", NA_DENSITY)
_CONVERSION_VALUES = ("gcc_to_kgm3", "identity", NA_DENSITY)


# ---------------------------------------------------------------------------
# Registered statements - the exact prose this increment may persist
# ---------------------------------------------------------------------------

_S = SCOPE_OUTPUT_INC7

_LIM_DATA = (
    "Screening-level, uncalibrated. This project holds no core density, no measured "
    "seawater density, no local gravity survey, and no shallow-density control, so no "
    "number derived here is calibrated. Asserts no named lithology.")

_STATEMENT_LIST = (
    RegisteredStatement(
        statement_id="availability_statistics_basis",
        scope=_S,
        text="Counts and depths measured over this well's OWN contract-resolved density curve, in the canonical unit the LOCKED Increment 2.1.1 loader recorded for it. No environmental correction, rescaling, smoothing, despiking, replacement, or extrapolation has been applied, and no value has been modified. These numbers describe the curve as recorded and imply no lithology.",
        purpose="Persisted as the 'statistics_basis' field of density_availability_inventory.csv.",
        provenance="Enumerated from the ACTUAL emitted density_availability_inventory.csv record."),
    RegisteredStatement(
        statement_id="availability_limitations",
        scope=_S,
        text="AVAILABILITY AND COVERAGE ONLY. Coverage is not fitness: a density curve can be complete over its own logged interval and still be unable to support an absolute overburden integral, because the integral needs the column above it as well. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of density_availability_inventory.csv.",
        provenance="Enumerated from the ACTUAL emitted density_availability_inventory.csv record."),
    RegisteredStatement(
        statement_id="qc_statistics_basis",
        scope=_S,
        text="Mask counts are counts of samples satisfying explicitly declared, configuration-driven criteria; the screening plausibility band is a SCREENING CRITERION chosen to catch tool, hole-condition and processing artefacts, and is not a statement of universal geological truth or of what rock exists in this well. A sample failing a criterion is MASKED, never modified, clipped, rescaled or replaced.",
        purpose="Persisted as the 'statistics_basis' field of density_qc_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted density_qc_summary.csv record."),
    RegisteredStatement(
        statement_id="qc_limitations",
        scope=_S,
        text="QC MASKS ONLY. Passing every mask makes a sample admissible to an integral; it does not make it correct, and it assigns no lithology. The original resolved density array is unchanged: any conditioned representation lives in a separately named array with its own mask. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of density_qc_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted density_qc_summary.csv record."),
    RegisteredStatement(
        statement_id="gap_inventory_limitations",
        scope=_S,
        text="FACTUAL GAP EXTENTS ONLY. A shallow gap between the seabed and the first valid density sample is an UNMEASURED COLUMN, not a dropout, and is never bridged at any threshold. A bridged short internal gap carries linearly interpolated density in true vertical depth; its samples are conditioned, not measured, and its contribution to any stress is reported separately. A long internal gap is never bridged and truncates the integrable column. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of density_gap_inventory.csv.",
        provenance="Enumerated from the ACTUAL emitted density_gap_inventory.csv record."),
    RegisteredStatement(
        statement_id="eligibility_purpose",
        scope=_S,
        text="States what the MEASURED density coverage of this well can and cannot support for a vertical overburden-stress calculation. The status is DERIVED from measured coverage and QC results; no well name participates in the derivation and no configuration key names a well.",
        purpose="Persisted as the 'purpose' field of overburden_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted overburden_eligibility_summary.csv record."),
    RegisteredStatement(
        statement_id="eligibility_limitations",
        scope=_S,
        text="ELIGIBILITY IS NOT VALIDITY. A measured increment is the integral of recorded density over the supported interval ONLY; it is not an absolute vertical stress and must never be read as one. An absolute stress additionally requires the density column from the datum or seabed down to the evaluation depth, which no amount of coverage inside the logged interval can supply. Where that column is unmeasured, the deficit is reported as a thickness and bracketed as a transparent scenario, never filled. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of overburden_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted overburden_eligibility_summary.csv record."),
    RegisteredStatement(
        statement_id="profile_limitations",
        scope=_S,
        text="MEASURED INCREMENT, NOT ABSOLUTE STRESS. The cumulative value is the integral of rho*g*dz from this well's FIRST eligible density sample down to the node, taken in true vertical depth by trapezoidal quadrature. It is zero at the first node by definition and excludes every column above it, including the water column and any unmeasured shallow section. Reported nodes are SELECTED existing samples at the configured step; no value here is interpolated for reporting, and the integral itself uses every eligible sample. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of vertical_stress_profile.csv.",
        provenance="Enumerated from the ACTUAL emitted vertical_stress_profile.csv record."),
    RegisteredStatement(
        statement_id="scenario_limitations",
        scope=_S,
        text="TRANSPARENT SCENARIO, NOT A RESULT. Every total in this table depends on an ASSUMED depth-averaged bulk density for an unmeasured column and an ASSUMED seawater density. The low endpoint is conditional on a fully saturated column; the project does not establish the unknown interval's fluid state. The high endpoint is the same well's measured P05 over samples eligible for measured integration, used only as an illustrative upper scenario motivated by monotonic-compaction reasoning; it is not a physical ceiling or rigorous uncertainty bound. The distinct all-finite P05 remains a factual QC statistic and does not drive the scenario. The base case is the arithmetic midpoint and has NO evidentiary support. No depth-dependent density function is fitted anywhere, no lithology is assumed, and the base case is never a best estimate. Read the full sensitivity spread, never a single row. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of shallow_column_scenarios.csv.",
        provenance="Enumerated from the ACTUAL emitted shallow_column_scenarios.csv record."),
    RegisteredStatement(
        statement_id="gap_sensitivity_limitations",
        scope=_S,
        text="SENSITIVITY TO A CONFIGURED CHOICE. Each row re-runs gap conditioning, integration and status derivation at one candidate threshold, so that the effect of the approved threshold is visible rather than assumed. The approved row is flagged; nothing in this table selects a preferred value, and a threshold that bridges more gaps is not thereby better. " + _LIM_DATA,
        purpose="Persisted as the 'limitations' field of gap_threshold_sensitivity.csv.",
        provenance="Enumerated from the ACTUAL emitted gap_threshold_sensitivity.csv record."),
    RegisteredStatement(
        statement_id="manifest_depth_convention_statement",
        scope=_S,
        text="TVD is zero at the well datum and increases downward; the datum elevation is referenced to mean sea level, positive upward; TVDSS = TVD - datum elevation and is positive downward from mean sea level. A downward interval therefore has a positive increment in both coordinates, and dTVD equals dTVDSS exactly. This convention is documented and independently tested in the locked depth-mapping module, and is re-verified against each well frame's own arrays at run time rather than inferred from a variable name.",
        purpose="Persisted as the 'depth_convention_statement' key of the Increment 7 manifest.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_gravity_basis",
        scope=_S,
        text="CGPM standard gravity, exact by definition at 9.80665 m/s2. This is a CONFIGURED ASSUMPTION: no local gravity survey exists for these wells, and every absolute or scenario stress reported here carries it.",
        purpose="Persisted as the 'gravity_basis' key of the Increment 7 manifest.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_assumption_statement",
        scope=_S,
        text="Every value in this register is a CONFIGURED SCREENING ASSUMPTION reviewed in config/overburden_stress.yml, not a measurement. The seawater density is assumed, not measured; the screening plausibility band is a project criterion, not a geological limit; the gap threshold is a heuristic whose effect is published as a sensitivity; and the shallow-column endpoints are illustrative scenarios, not physical bounds or a model.",
        purpose="Persisted as the 'statement' key of the manifest assumption register.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_calibration_statement",
        scope=_S,
        text="No calibration data of any kind are available to this project: no RFT/MDT/DST pressure, no LOT/XLOT/DFIT stress fit, no core or log-calibrated density control, no measured seawater density, and no local gravity survey. Nothing in Increment 7 is calibrated, and no result here may be described as calibrated truth.",
        purpose="Persisted as the 'statement' key of the manifest calibration block.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_named_lithology_statement",
        scope=_S,
        text="No named lithology is assigned anywhere in Increment 7. The density screening band, the gap policy, the shallow-column bracket and the eligibility ladder are all expressed in physical and coverage terms, and none of them is justified by an assumed rock type.",
        purpose="Persisted as the 'named_lithology_statement' key of the Increment 7 manifest.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_lithology_model",
        scope=_S,
        text="positive_authorization_of_every_emitted_controlled_field",
        purpose="Persisted as the 'model' key of the manifest lithology-validation block.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="manifest_lithology_derivation",
        scope=_S,
        text="Derived from the ACTUAL emitted records, not from a reconstructed parallel scope: every schema-declared string occurrence in every artifact this run serializes is collected by schema, classified, and authorized against a closed registry, before and after serialization.",
        purpose="Persisted as the 'derivation' key of the manifest lithology-validation block.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="limitation_no_absolute_without_full_column",
        scope=_S,
        text="An absolute vertical overburden stress requires density coverage from the relevant datum or seabed to the evaluation depth. Where that column is not measured, Increment 7 reports a partial measured increment or a transparent screening bracket, and never a single absolute curve presented as measured truth.",
        purpose="Persisted as one entry of the manifest 'limitations' list.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="limitation_no_density_repair",
        scope=_S,
        text="No density value is clipped, rescaled, smoothed, despiked, replaced or extrapolated anywhere in Increment 7. Invalid samples are masked; short internal gaps may be linearly bridged in true vertical depth into a separately named array whose contribution is reported separately; nothing else is filled.",
        purpose="Persisted as one entry of the manifest 'limitations' list.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="limitation_assumed_components",
        scope=_S,
        text="The water column, the unresolved shallow column and standard gravity are ASSUMPTIONS, not measurements. Every reported stress is partitioned so that the measured formation contribution, the conditioned bridged contribution and the assumed contributions are separately visible, and no total is reported while any component is unresolved.",
        purpose="Persisted as one entry of the manifest 'limitations' list.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="limitation_no_pore_pressure",
        scope=_S,
        text="Increment 7 computes no pore pressure, no effective stress, no normal compaction trend, no elastic property, no rock strength, no horizontal stress, no mud window and no wellbore-stability result. Those methods are deferred to later increments and are absent from this version; importing them will fail until they exist.",
        purpose="Persisted as one entry of the manifest 'limitations' list.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
    RegisteredStatement(
        statement_id="limitation_seabed_provenance",
        scope=_S,
        text="A seabed datum is read only from the LOCKED Increment 5 survey-corrected marker table for the well it was picked in. A well with no approved formation-top file has no determinable seabed, no determinable water column and no determinable shallow-gap thickness; those are reported as unresolved, never as zero and never borrowed from another well.",
        purpose="Persisted as one entry of the manifest 'limitations' list.",
        provenance="Enumerated from the ACTUAL emitted density_overburden_manifest.json record."),
)

OVERBURDEN_STATEMENTS = {s.statement_id: s for s in _STATEMENT_LIST}

_TEMPLATE_LIST = (
    RegisteredTemplate(
        template_id="scenario_basis",
        scope=_S,
        template=(
            "Screening scenario. The depth-averaged bulk density of the unmeasured column is "
            "ASSUMED at {assumed_density_kg_m3} kg/m3 over {unresolved_thickness_m} m of true "
            "vertical depth. Of the reported total, {assumed_fraction_pct} percent comes "
            "from configured column assumptions, {conditioned_fraction_pct} percent from "
            "explicitly bridged density, and {measured_fraction_pct} percent from strictly "
            "measured density. This is not a calibrated value and is not an estimate of "
            "the true vertical stress."),
        fields={"assumed_density_kg_m3": "decimal",
                "unresolved_thickness_m": "decimal",
                "assumed_fraction_pct": "decimal",
                "conditioned_fraction_pct": "decimal",
                "measured_fraction_pct": "decimal"},
        purpose="Persisted as the 'scenario_basis' field of shallow_column_scenarios.csv, "
                "carrying the measured three-component fraction disclosure the policy "
                "requires.",
        provenance="Enumerated from the ACTUAL emitted shallow_column_scenarios.csv record."),
    RegisteredTemplate(
        template_id="empty_mnemonic_ordinal",
        scope=_S,
        template="(empty mnemonic, ordinal {ordinal})",
        fields={"ordinal": "integer"},
        purpose="Persisted as the 'raw_mnemonic' field of "
                "density_availability_inventory.csv for a density column whose LAS ~C "
                "line carries an EMPTY mnemonic. The locked Increment 2.1.1 loader "
                "synthesises exactly this descriptor from the column's ordinal position; "
                "Increment 7 reproduces the loader's own identity string rather than "
                "inventing a mnemonic the file does not contain.",
        provenance="Enumerated from the ACTUAL emitted "
                   "density_availability_inventory.csv record."),
)

OVERBURDEN_TEMPLATES = {t.template_id: t for t in _TEMPLATE_LIST}


# ---------------------------------------------------------------------------
# Approved labels - verdicts a well is stamped with
# ---------------------------------------------------------------------------

def _labels(field_kind, values, purpose):
    return tuple(ApprovedLabel(
        value=v, field_kind=field_kind, purpose=purpose,
        provenance="Enumerated from the ACTUAL persisted Increment 7 export; every label "
                   "this increment writes is a member of this registry.")
        for v in values)


OVERBURDEN_LABELS = (
    _labels("overburden_status", VALID_OVERBURDEN_STATUSES,
            "Derived verdict on what this well's measured density coverage can support.")
    + _labels("seabed_basis", VALID_SEABED_BASES,
              "Where this well's seabed datum came from, or that it is not determinable.")
    + _labels("gap_class", VALID_GAP_CLASSES,
              "Structural classification of one gap in the density column.")
    + _labels("gap_disposition", VALID_GAP_DISPOSITIONS,
              "What the configured policy actually did about one gap.")
    + _labels("assumed_density_basis",
              (SCENARIO_BASIS_LOW, SCENARIO_BASIS_BASE, SCENARIO_BASIS_HIGH),
              "How one shallow-column scenario's assumed density was bounded.")
    + _labels("density_source", ("measured_rhob", "bridged_linear_in_tvd"),
              "Whether one profile node's density was recorded or conditioned.")
    + _labels("evidence_class", ("measured", "assumed_configured",
                                 "derived_locked_prior_increment"),
              "The evidential standing of the quantity in this record.")
    + _labels("calibration_status", ("uncalibrated_screening_only",),
              "Calibration standing; this project holds no calibration data of any kind.")
)


# ---------------------------------------------------------------------------
# Closed CSV schemas
# ---------------------------------------------------------------------------

AVAILABILITY = "density_availability_inventory.csv"
QC = "density_qc_summary.csv"
GAPS = "density_gap_inventory.csv"
ELIGIBILITY = "overburden_eligibility_summary.csv"
PROFILE = "vertical_stress_profile.csv"
SCENARIOS = "shallow_column_scenarios.csv"
SENSITIVITY = "gap_threshold_sensitivity.csv"
ISSUES = "density_overburden_issues.csv"

OVERBURDEN_CSV_SCHEMAS = {
    AVAILABILITY: CsvArtifactSchema(
        columns=(
            "well_key", "source_las_filename", "source_survey_filename",
            "density_curve_present", "canonical_curve_name", "source_curve_name",
            "raw_mnemonic", "raw_unit", "canonical_unit", "conversion_function",
            "unit_resolved", "conversion_confirmed", "evidence_class",
            "n_samples", "n_finite_rhob", "n_non_finite_rhob", "n_non_positive_rhob",
            "n_below_screening_min", "n_above_screening_max",
            "n_screening_bound_failures", "n_in_screening_band", "n_depth_mapped",
            "n_depth_unmapped", "n_outside_survey_coverage", "n_eligible",
            "first_valid_md_m", "last_valid_md_m", "first_valid_tvd_m",
            "last_valid_tvd_m", "first_valid_tvdss_m", "last_valid_tvdss_m",
            "gross_coverage_md_m", "gross_coverage_tvd_m", "median_md_step_m",
            "depth_basis_used", "depth_map_status", "survey_md_min_m", "survey_md_max_m",
            "unit", "assurance_tier", "statistics_basis", "limitations",
        ),
        integer_fields=("n_samples", "n_finite_rhob", "n_non_finite_rhob",
                        "n_non_positive_rhob", "n_below_screening_min",
                        "n_above_screening_max", "n_screening_bound_failures",
                        "n_in_screening_band", "n_depth_mapped", "n_depth_unmapped",
                        "n_outside_survey_coverage", "n_eligible"),
        number_fields=("first_valid_md_m", "last_valid_md_m", "first_valid_tvd_m",
                       "last_valid_tvd_m", "first_valid_tvdss_m", "last_valid_tvdss_m",
                       "gross_coverage_md_m", "gross_coverage_tvd_m", "median_md_step_m",
                       "survey_md_min_m", "survey_md_max_m"),
        boolean_fields=("density_curve_present", "unit_resolved", "conversion_confirmed"),
        nullable_fields=("first_valid_md_m", "last_valid_md_m", "first_valid_tvd_m",
                         "last_valid_tvd_m", "first_valid_tvdss_m", "last_valid_tvdss_m",
                         "gross_coverage_md_m", "gross_coverage_tvd_m",
                         "median_md_step_m")),
    QC: CsvArtifactSchema(
        columns=(
            "well_key", "canonical_curve_name", "screening_min_kg_m3",
            "screening_max_kg_m3", "bounds_are_inclusive", "n_source_value_present",
            "n_finite_numeric_density", "n_unit_resolved", "n_screening_range_plausible",
            "n_below_seabed_sample", "n_depth_mapping_valid", "n_within_survey_coverage",
            "n_eligible_for_measured_integration", "n_bridged_short_gap",
            "n_unresolved_long_gap", "n_unresolved_shallow_column",
            "n_unresolved_terminal_column", "rhob_min_kg_m3", "rhob_p05_kg_m3",
            "rhob_median_kg_m3", "rhob_p95_kg_m3", "rhob_max_kg_m3",
            "rhob_eligible_p05_kg_m3", "seabed_basis",
            "seabed_mdrt_m", "seabed_tvd_m", "seabed_tvdss_m", "shallow_gap_md_m",
            "shallow_gap_tvd_m", "terminal_gap_md_m", "terminal_gap_tvd_m",
            "n_internal_gaps", "n_internal_gap_samples", "longest_internal_gap_md_m",
            "longest_internal_gap_tvd_m", "mask_counts", "unit", "assurance_tier",
            "statistics_basis", "limitations",
        ),
        integer_fields=("n_source_value_present", "n_finite_numeric_density",
                        "n_unit_resolved", "n_screening_range_plausible",
                        "n_below_seabed_sample", "n_depth_mapping_valid",
                        "n_within_survey_coverage",
                        "n_eligible_for_measured_integration", "n_bridged_short_gap",
                        "n_unresolved_long_gap", "n_unresolved_shallow_column",
                        "n_unresolved_terminal_column", "n_internal_gaps",
                        "n_internal_gap_samples"),
        number_fields=("screening_min_kg_m3", "screening_max_kg_m3", "rhob_min_kg_m3",
                       "rhob_p05_kg_m3", "rhob_median_kg_m3", "rhob_p95_kg_m3",
                       "rhob_max_kg_m3", "rhob_eligible_p05_kg_m3",
                       "seabed_mdrt_m", "seabed_tvd_m",
                       "seabed_tvdss_m", "shallow_gap_md_m", "shallow_gap_tvd_m",
                       "terminal_gap_md_m", "terminal_gap_tvd_m",
                       "longest_internal_gap_md_m", "longest_internal_gap_tvd_m"),
        boolean_fields=("bounds_are_inclusive",),
        nullable_fields=("n_below_seabed_sample", "rhob_min_kg_m3", "rhob_p05_kg_m3",
                         "rhob_median_kg_m3", "rhob_p95_kg_m3", "rhob_max_kg_m3",
                         "rhob_eligible_p05_kg_m3",
                         "seabed_mdrt_m", "seabed_tvd_m", "seabed_tvdss_m",
                         "shallow_gap_md_m", "shallow_gap_tvd_m", "terminal_gap_md_m",
                         "terminal_gap_tvd_m", "longest_internal_gap_md_m",
                         "longest_internal_gap_tvd_m")),
    GAPS: CsvArtifactSchema(
        columns=(
            "well_key", "gap_index", "gap_class", "disposition", "n_samples",
            "start_index", "end_index", "md_start_m", "md_end_m", "thickness_md_m",
            "tvd_start_m", "tvd_end_m", "thickness_tvd_m", "threshold_tvd_m",
            "bounding_density_above_kg_m3", "bounding_density_below_kg_m3",
            "unit", "assurance_tier", "limitations",
        ),
        integer_fields=("gap_index", "n_samples", "start_index", "end_index"),
        number_fields=("md_start_m", "md_end_m", "thickness_md_m", "tvd_start_m",
                       "tvd_end_m", "thickness_tvd_m", "threshold_tvd_m",
                       "bounding_density_above_kg_m3", "bounding_density_below_kg_m3"),
        nullable_fields=("start_index", "end_index", "md_start_m", "md_end_m",
                         "thickness_md_m", "tvd_start_m", "tvd_end_m",
                         "thickness_tvd_m", "threshold_tvd_m",
                         "bounding_density_above_kg_m3", "bounding_density_below_kg_m3"),
        min_rows=0),
    ELIGIBILITY: CsvArtifactSchema(
        columns=(
            "well_key", "overburden_status", "limiting_reasons", "seabed_resolved",
            "seabed_basis", "n_eligible_samples", "n_bridged_samples",
            "n_unresolved_internal_gaps", "n_unresolved_long_gaps",
            "column_uninterrupted",
            "column_truncated_at_unresolved_gap", "n_eligible_samples_below_truncation",
            "eligible_top_tvd_m", "eligible_base_tvd_m", "eligible_top_tvdss_m",
            "eligible_base_tvdss_m", "measured_thickness_tvd_m",
            "water_column_thickness_tvd_m", "shallow_unresolved_thickness_tvd_m",
            "terminal_unresolved_thickness_tvd_m",
            "unresolved_long_gap_thickness_tvd_m", "measured_increment_pa",
            "measured_increment_mpa", "bridged_increment_pa", "bridged_increment_mpa",
            "absolute_stress_supported", "gravity_m_s2", "integration_method",
            "integration_coordinate", "depth_convention", "evidence_class",
            "calibration_status", "unit", "assurance_tier", "purpose", "limitations",
        ),
        integer_fields=("n_eligible_samples", "n_bridged_samples",
                        "n_unresolved_internal_gaps", "n_unresolved_long_gaps",
                        "n_eligible_samples_below_truncation"),
        number_fields=("eligible_top_tvd_m", "eligible_base_tvd_m",
                       "eligible_top_tvdss_m", "eligible_base_tvdss_m",
                       "measured_thickness_tvd_m", "water_column_thickness_tvd_m",
                       "shallow_unresolved_thickness_tvd_m",
                       "terminal_unresolved_thickness_tvd_m",
                       "unresolved_long_gap_thickness_tvd_m", "measured_increment_pa",
                       "measured_increment_mpa", "bridged_increment_pa",
                       "bridged_increment_mpa", "gravity_m_s2"),
        boolean_fields=("seabed_resolved", "column_uninterrupted",
                        "column_truncated_at_unresolved_gap",
                        "absolute_stress_supported"),
        nullable_fields=("eligible_top_tvd_m", "eligible_base_tvd_m",
                         "eligible_top_tvdss_m", "eligible_base_tvdss_m",
                         "measured_thickness_tvd_m", "water_column_thickness_tvd_m",
                         "shallow_unresolved_thickness_tvd_m",
                         "terminal_unresolved_thickness_tvd_m",
                         "measured_increment_pa", "measured_increment_mpa",
                         "bridged_increment_pa", "bridged_increment_mpa")),
    PROFILE: CsvArtifactSchema(
        columns=(
            "well_key", "node_index", "md_m", "tvd_m", "tvdss_m", "rhob_kg_m3",
            "density_source", "cumulative_measured_increment_pa",
            "cumulative_measured_increment_mpa", "gravity_m_s2",
            "integration_coordinate", "evidence_class", "calibration_status",
            "unit", "assurance_tier", "limitations",
        ),
        integer_fields=("node_index",),
        number_fields=("md_m", "tvd_m", "tvdss_m", "rhob_kg_m3",
                       "cumulative_measured_increment_pa",
                       "cumulative_measured_increment_mpa", "gravity_m_s2"),
        min_rows=0),
    SCENARIOS: CsvArtifactSchema(
        columns=(
            "well_key", "scenario_name", "assumed_shallow_density_kg_m3",
            "assumed_density_basis", "seawater_density_kg_m3", "gravity_m_s2",
            "water_column_thickness_tvd_m", "unresolved_thickness_tvd_m",
            "measured_thickness_tvd_m", "water_column_stress_pa",
            "unresolved_shallow_stress_pa", "measured_formation_stress_pa",
            "bridged_gap_stress_pa", "total_stress_pa", "total_stress_mpa",
            "assumed_fraction_of_total", "conditioned_fraction_of_total",
            "measured_fraction_of_total",
            "evidence_class", "calibration_status", "unit", "assurance_tier",
            "scenario_basis", "limitations",
        ),
        number_fields=("assumed_shallow_density_kg_m3", "seawater_density_kg_m3",
                       "gravity_m_s2", "water_column_thickness_tvd_m",
                       "unresolved_thickness_tvd_m", "measured_thickness_tvd_m",
                       "water_column_stress_pa", "unresolved_shallow_stress_pa",
                       "measured_formation_stress_pa", "bridged_gap_stress_pa",
                       "total_stress_pa", "total_stress_mpa",
                       "assumed_fraction_of_total", "conditioned_fraction_of_total",
                       "measured_fraction_of_total"),
        min_rows=0),
    SENSITIVITY: CsvArtifactSchema(
        columns=(
            "well_key", "threshold_tvd_m", "is_approved_threshold", "n_bridged_gaps",
            "n_bridged_samples", "bridged_thickness_tvd_m", "n_long_gaps",
            "long_gap_thickness_tvd_m", "n_eligible_or_bridged_samples",
            "total_measured_increment_pa", "total_measured_increment_mpa",
            "bridged_increment_pa", "derived_status", "unit", "assurance_tier",
            "limitations",
        ),
        integer_fields=("n_bridged_gaps", "n_bridged_samples", "n_long_gaps",
                        "n_eligible_or_bridged_samples"),
        number_fields=("threshold_tvd_m", "bridged_thickness_tvd_m",
                       "long_gap_thickness_tvd_m", "total_measured_increment_pa",
                       "total_measured_increment_mpa", "bridged_increment_pa"),
        boolean_fields=("is_approved_threshold",),
        nullable_fields=("total_measured_increment_pa", "total_measured_increment_mpa",
                         "bridged_increment_pa")),
    ISSUES: CsvArtifactSchema(
        columns=("severity", "code", "context", "message", "assurance_tier"),
        min_rows=0),
}


# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------

def _enum(artifact, field, values):
    return FieldPolicy(artifact, field, "structural_enum", allowed_values=values)


def _label(artifact, field, kind):
    return FieldPolicy(artifact, field, "typed_label", field_kind=kind)


def _stmt(artifact, field, *sids):
    return FieldPolicy(artifact, field, "registered_statement", statement_ids=sids)


_TIER = (ASSURANCE_TIER_VALUE,)
_WELLS = tuple(sorted(APPROVED_WELL_KEYS))

_FIELD_POLICIES = (
    # --- density_availability_inventory.csv -------------------------------
    FieldPolicy(AVAILABILITY, "well_key", "identifier", allowed_values=_WELLS),
    FieldPolicy(AVAILABILITY, "source_las_filename", "filename"),
    FieldPolicy(AVAILABILITY, "source_survey_filename", "filename"),
    _enum(AVAILABILITY, "canonical_curve_name", _CURVE_NAME_VALUES),
    _enum(AVAILABILITY, "source_curve_name", _SOURCE_CURVE_VALUES),
    FieldPolicy(AVAILABILITY, "raw_mnemonic", "controlled_template",
                allowed_values=_SOURCE_CURVE_VALUES,
                template_id="empty_mnemonic_ordinal"),
    _enum(AVAILABILITY, "raw_unit", _RAW_UNIT_VALUES),
    _enum(AVAILABILITY, "canonical_unit", _CANONICAL_UNIT_VALUES),
    _enum(AVAILABILITY, "conversion_function", _CONVERSION_VALUES),
    _label(AVAILABILITY, "evidence_class", "evidence_class"),
    _enum(AVAILABILITY, "depth_basis_used", _DEPTH_BASIS_VALUES),
    _enum(AVAILABILITY, "depth_map_status", _DEPTH_MAP_STATUS_VALUES),
    _enum(AVAILABILITY, "unit", _UNIT_VALUES),
    _enum(AVAILABILITY, "assurance_tier", _TIER),
    _stmt(AVAILABILITY, "statistics_basis", "availability_statistics_basis"),
    _stmt(AVAILABILITY, "limitations", "availability_limitations"),

    # --- density_qc_summary.csv -------------------------------------------
    FieldPolicy(QC, "well_key", "identifier", allowed_values=_WELLS),
    _enum(QC, "canonical_curve_name", _CURVE_NAME_VALUES),
    _label(QC, "seabed_basis", "seabed_basis"),
    FieldPolicy(QC, "mask_counts", "structured_diagnostic"),
    _enum(QC, "unit", _UNIT_VALUES),
    _enum(QC, "assurance_tier", _TIER),
    _stmt(QC, "statistics_basis", "qc_statistics_basis"),
    _stmt(QC, "limitations", "qc_limitations"),

    # --- density_gap_inventory.csv ----------------------------------------
    FieldPolicy(GAPS, "well_key", "identifier", allowed_values=_WELLS),
    _label(GAPS, "gap_class", "gap_class"),
    _label(GAPS, "disposition", "gap_disposition"),
    _enum(GAPS, "unit", _UNIT_VALUES),
    _enum(GAPS, "assurance_tier", _TIER),
    _stmt(GAPS, "limitations", "gap_inventory_limitations"),

    # --- overburden_eligibility_summary.csv -------------------------------
    FieldPolicy(ELIGIBILITY, "well_key", "identifier", allowed_values=_WELLS),
    _label(ELIGIBILITY, "overburden_status", "overburden_status"),
    FieldPolicy(ELIGIBILITY, "limiting_reasons", CATEGORY_ENUMERATED_CODE_LIST,
                allowed_values=tuple(sorted(VALID_LIMITING_REASONS + ("none",)))),
    _label(ELIGIBILITY, "seabed_basis", "seabed_basis"),
    _enum(ELIGIBILITY, "integration_method", _INTEGRATION_METHOD_VALUES),
    _enum(ELIGIBILITY, "integration_coordinate", _INTEGRATION_COORDINATE_VALUES),
    _enum(ELIGIBILITY, "depth_convention", (SIGN_CONVENTION_ID,)),
    _label(ELIGIBILITY, "evidence_class", "evidence_class"),
    _label(ELIGIBILITY, "calibration_status", "calibration_status"),
    _enum(ELIGIBILITY, "unit", _UNIT_VALUES),
    _enum(ELIGIBILITY, "assurance_tier", _TIER),
    _stmt(ELIGIBILITY, "purpose", "eligibility_purpose"),
    _stmt(ELIGIBILITY, "limitations", "eligibility_limitations"),

    # --- vertical_stress_profile.csv --------------------------------------
    FieldPolicy(PROFILE, "well_key", "identifier", allowed_values=_WELLS),
    _label(PROFILE, "density_source", "density_source"),
    _enum(PROFILE, "integration_coordinate", _INTEGRATION_COORDINATE_VALUES),
    _label(PROFILE, "evidence_class", "evidence_class"),
    _label(PROFILE, "calibration_status", "calibration_status"),
    _enum(PROFILE, "unit", _UNIT_VALUES),
    _enum(PROFILE, "assurance_tier", _TIER),
    _stmt(PROFILE, "limitations", "profile_limitations"),

    # --- shallow_column_scenarios.csv -------------------------------------
    FieldPolicy(SCENARIOS, "well_key", "identifier", allowed_values=_WELLS),
    _enum(SCENARIOS, "scenario_name", VALID_SCENARIO_NAMES),
    _label(SCENARIOS, "assumed_density_basis", "assumed_density_basis"),
    _label(SCENARIOS, "evidence_class", "evidence_class"),
    _label(SCENARIOS, "calibration_status", "calibration_status"),
    _enum(SCENARIOS, "unit", _UNIT_VALUES),
    _enum(SCENARIOS, "assurance_tier", _TIER),
    FieldPolicy(SCENARIOS, "scenario_basis", "controlled_template",
                template_id="scenario_basis"),
    _stmt(SCENARIOS, "limitations", "scenario_limitations"),

    # --- gap_threshold_sensitivity.csv ------------------------------------
    FieldPolicy(SENSITIVITY, "well_key", "identifier", allowed_values=_WELLS),
    _label(SENSITIVITY, "derived_status", "overburden_status"),
    _enum(SENSITIVITY, "unit", _UNIT_VALUES),
    _enum(SENSITIVITY, "assurance_tier", _TIER),
    _stmt(SENSITIVITY, "limitations", "gap_sensitivity_limitations"),

    # --- density_overburden_issues.csv ------------------------------------
    _enum(ISSUES, "severity", ("INFO", "WARNING", "ERROR")),
    _enum(ISSUES, "code", ISSUE_CODES),
    FieldPolicy(ISSUES, "context", "sanitized_diagnostic"),
    FieldPolicy(ISSUES, "message", "sanitized_diagnostic"),
    _enum(ISSUES, "assurance_tier", _TIER),
)

M = OVERBURDEN_MANIFEST_ARTIFACT

_MANIFEST_POLICIES = (
    _enum(M, "/assurance_tier", _TIER),
    _enum(M, "/increment_title", (INCREMENT_TITLE,)),
    FieldPolicy(M, "/config_filename", "filename"),
    _enum(M, "/config_schema_version", ("7.0.1",)),
    _enum(M, "/depth_convention", (SIGN_CONVENTION_ID,)),
    _stmt(M, "/depth_convention_statement", "manifest_depth_convention_statement"),
    _enum(M, "/integration_method", _INTEGRATION_METHOD_VALUES),
    _enum(M, "/integration_coordinate", _INTEGRATION_COORDINATE_VALUES),
    _stmt(M, "/gravity_basis", "manifest_gravity_basis"),
    _stmt(M, "/assumption_register/statement", "manifest_assumption_statement"),
    _stmt(M, "/calibration_data_available/statement", "manifest_calibration_statement"),
    _stmt(M, "/named_lithology_statement", "manifest_named_lithology_statement"),
    _stmt(M, "/lithology_validation/model", "manifest_lithology_model"),
    _stmt(M, "/lithology_validation/derivation", "manifest_lithology_derivation"),
    FieldPolicy(M, "/lithology_validation/violations[]/artifact", "sanitized_diagnostic"),
    FieldPolicy(M, "/lithology_validation/violations[]/field", "sanitized_diagnostic"),
    FieldPolicy(M, "/lithology_validation/violations[]/location", "sanitized_diagnostic"),
    FieldPolicy(M, "/lithology_validation/violations[]/reason", "sanitized_diagnostic"),
    FieldPolicy(M, "/lithology_validation/violations[]/linter_terms[]", "sanitized_diagnostic"),
    FieldPolicy(M, "/lithology_validation/emitted_field_coverage/artifacts_inspected[]",
                "filename"),
    _enum(M, "/methods_not_implemented[]", NOT_IMPLEMENTED_TOKENS),
    _stmt(M, "/limitations[]",
          "limitation_no_absolute_without_full_column", "limitation_no_density_repair",
          "limitation_assumed_components", "limitation_no_pore_pressure",
          "limitation_seabed_provenance"),
    _enum(M, "/issues[]/severity", ("INFO", "WARNING", "ERROR")),
    _enum(M, "/issues[]/code", ISSUE_CODES),
    FieldPolicy(M, "/issues[]/context", "sanitized_diagnostic"),
    FieldPolicy(M, "/issues[]/message", "sanitized_diagnostic"),
    FieldPolicy(M, "/wells/*/source_las_filename", "filename"),
    FieldPolicy(M, "/wells/*/source_survey_filename", "filename"),
    _enum(M, "/wells/*/canonical_curve_name", _CURVE_NAME_VALUES),
    _enum(M, "/wells/*/canonical_unit", _CANONICAL_UNIT_VALUES),
    _enum(M, "/wells/*/conversion_function", _CONVERSION_VALUES),
    _enum(M, "/wells/*/depth_basis_used", _DEPTH_BASIS_VALUES),
    _enum(M, "/wells/*/depth_map_status", _DEPTH_MAP_STATUS_VALUES),
    _label(M, "/wells/*/seabed_basis", "seabed_basis"),
    _label(M, "/wells/*/overburden_status", "overburden_status"),
    _enum(M, "/wells/*/limiting_reasons[]", tuple(sorted(VALID_LIMITING_REASONS))),
    _enum(M, "/wells/*/shallow_column_scenarios[]/scenario_name", VALID_SCENARIO_NAMES),
    _label(M, "/wells/*/shallow_column_scenarios[]/assumed_density_basis",
           "assumed_density_basis"),
    _label(M, "/wells/*/gap_threshold_sensitivity[]/derived_status", "overburden_status"),
)

JSON_OBJECT_KEYS = {
    "": frozenset((
        "assurance_tier", "assumption_register", "calibration_data_available",
        "config_filename", "config_schema_version", "depth_convention",
        "depth_convention_statement", "depth_convention_verified", "gravity_basis",
        "gravity_m_s2", "increment", "increment_title", "integration_coordinate",
        "integration_method", "issues", "limitations", "lithology_validation",
        "methods_not_implemented", "n_wells_absolute_supported", "n_wells_evaluated",
        "n_wells_not_eligible", "n_wells_partial_measured_only",
        "n_wells_screening_sensitivity_only", "named_lithology_assigned",
        "named_lithology_statement", "total_bridged_density_samples",
        "total_eligible_density_samples", "wells",
    )),
    "/assumption_register": frozenset((
        "bounds_are_inclusive", "profile_report_step_tvdss_m", "rhob_max_kg_m3",
        "rhob_min_kg_m3", "scenario_high_percentile", "seawater_density_high_kg_m3",
        "seawater_density_kg_m3", "seawater_density_low_kg_m3",
        "shallow_gap_tolerance_tvd_m", "short_gap_max_tvd_m", "statement",
    )),
    "/calibration_data_available": frozenset((
        "core_or_log_calibrated_density_control", "local_gravity_survey",
        "measured_seawater_density", "pressure_rft_mdt_dst",
        "stress_fit_lot_xlot_dfit", "statement",
    )),
    "/lithology_validation": frozenset((
        "model", "derivation", "emitted_field_coverage", "violations",
    )),
    "/lithology_validation/emitted_field_coverage": frozenset((
        "n_string_field_occurrences", "n_controlled_occurrences",
        "n_structural_occurrences", "n_unguaranteed_occurrences",
        "n_unclassified_fields", "n_unauthorized_controlled_fields",
        "n_field_kind_mismatches", "n_schema_violations", "violations",
        "artifacts_inspected", "distinct_statements_used", "distinct_templates_used",
        "distinct_labels_used",
    )),
    "/lithology_validation/violations[]": frozenset((
        "artifact", "field", "location", "reason", "linter_terms")),
    "/issues[]": frozenset(("severity", "code", "context", "message")),
    "/wells": None,
    "/wells/*": frozenset((
        "absolute_stress_supported", "bridged_increment_pa", "canonical_curve_name",
        "canonical_unit", "column_truncated_at_unresolved_gap", "column_uninterrupted",
        "conversion_function", "datum_elevation_m", "density_curve_present",
        "depth_basis_used", "depth_map_status", "gap_threshold_sensitivity",
        "limiting_reasons", "measured_increment_mpa", "measured_increment_pa",
        "n_bridged_samples", "n_depth_unmapped", "n_eligible", "n_finite_rhob",
        "n_samples", "n_screening_bound_failures", "n_unresolved_internal_gaps",
        "n_unresolved_long_gaps", "rhob_eligible_p05_kg_m3",
        "overburden_status", "seabed_basis", "seabed_resolved", "seabed_tvdss_m",
        "shallow_column_scenarios", "shallow_unresolved_thickness_tvd_m",
        "source_las_filename", "source_survey_filename",
        "terminal_unresolved_thickness_tvd_m", "unit_resolved",
    )),
    "/wells/*/shallow_column_scenarios[]": frozenset((
        "scenario_name", "assumed_density_basis", "assumed_shallow_density_kg_m3",
        "total_stress_pa", "total_stress_mpa", "assumed_fraction_of_total",
        "conditioned_fraction_of_total", "measured_fraction_of_total",
    )),
    "/wells/*/gap_threshold_sensitivity[]": frozenset((
        "threshold_tvd_m", "is_approved_threshold", "n_bridged_gaps", "n_long_gaps",
        "derived_status",
    )),
}

JSON_LIST_ITEM_KINDS = {
    "/issues": "object",
    "/limitations": "string",
    "/lithology_validation/emitted_field_coverage/artifacts_inspected": "string",
    "/lithology_validation/violations": "object",
    "/lithology_validation/violations[]/linter_terms": "string",
    "/methods_not_implemented": "string",
    "/wells/*/limiting_reasons": "string",
    "/wells/*/shallow_column_scenarios": "object",
    "/wells/*/gap_threshold_sensitivity": "object",
}

JSON_BOOLEAN_PATHS = frozenset((
    "/depth_convention_verified", "/named_lithology_assigned",
    "/assumption_register/bounds_are_inclusive",
    "/calibration_data_available/core_or_log_calibrated_density_control",
    "/calibration_data_available/local_gravity_survey",
    "/calibration_data_available/measured_seawater_density",
    "/calibration_data_available/pressure_rft_mdt_dst",
    "/calibration_data_available/stress_fit_lot_xlot_dfit",
    "/wells/*/absolute_stress_supported",
    "/wells/*/column_truncated_at_unresolved_gap",
    "/wells/*/column_uninterrupted", "/wells/*/density_curve_present",
    "/wells/*/seabed_resolved", "/wells/*/unit_resolved",
    "/wells/*/gap_threshold_sensitivity[]/is_approved_threshold",
))

JSON_INTEGER_PATHS = frozenset((
    "/increment", "/n_wells_absolute_supported", "/n_wells_evaluated",
    "/n_wells_not_eligible", "/n_wells_partial_measured_only",
    "/n_wells_screening_sensitivity_only", "/total_bridged_density_samples",
    "/total_eligible_density_samples",
    "/lithology_validation/emitted_field_coverage/distinct_labels_used",
    "/lithology_validation/emitted_field_coverage/distinct_statements_used",
    "/lithology_validation/emitted_field_coverage/distinct_templates_used",
    "/lithology_validation/emitted_field_coverage/n_controlled_occurrences",
    "/lithology_validation/emitted_field_coverage/n_field_kind_mismatches",
    "/lithology_validation/emitted_field_coverage/n_schema_violations",
    "/lithology_validation/emitted_field_coverage/n_string_field_occurrences",
    "/lithology_validation/emitted_field_coverage/n_structural_occurrences",
    "/lithology_validation/emitted_field_coverage/n_unauthorized_controlled_fields",
    "/lithology_validation/emitted_field_coverage/n_unclassified_fields",
    "/lithology_validation/emitted_field_coverage/n_unguaranteed_occurrences",
    "/lithology_validation/emitted_field_coverage/violations",
    "/wells/*/n_bridged_samples", "/wells/*/n_depth_unmapped", "/wells/*/n_eligible",
    "/wells/*/n_finite_rhob", "/wells/*/n_samples",
    "/wells/*/n_screening_bound_failures", "/wells/*/n_unresolved_internal_gaps",
    "/wells/*/n_unresolved_long_gaps",
    "/wells/*/gap_threshold_sensitivity[]/n_bridged_gaps",
    "/wells/*/gap_threshold_sensitivity[]/n_long_gaps",
))

JSON_NUMBER_PATHS = frozenset((
    "/gravity_m_s2", "/assumption_register/profile_report_step_tvdss_m",
    "/assumption_register/rhob_max_kg_m3", "/assumption_register/rhob_min_kg_m3",
    "/assumption_register/scenario_high_percentile",
    "/assumption_register/seawater_density_high_kg_m3",
    "/assumption_register/seawater_density_kg_m3",
    "/assumption_register/seawater_density_low_kg_m3",
    "/assumption_register/shallow_gap_tolerance_tvd_m",
    "/assumption_register/short_gap_max_tvd_m",
    "/wells/*/bridged_increment_pa", "/wells/*/datum_elevation_m",
    "/wells/*/measured_increment_mpa", "/wells/*/measured_increment_pa",
    "/wells/*/seabed_tvdss_m", "/wells/*/shallow_unresolved_thickness_tvd_m",
    "/wells/*/terminal_unresolved_thickness_tvd_m",
    "/wells/*/rhob_eligible_p05_kg_m3",
    "/wells/*/shallow_column_scenarios[]/assumed_fraction_of_total",
    "/wells/*/shallow_column_scenarios[]/conditioned_fraction_of_total",
    "/wells/*/shallow_column_scenarios[]/measured_fraction_of_total",
    "/wells/*/shallow_column_scenarios[]/assumed_shallow_density_kg_m3",
    "/wells/*/shallow_column_scenarios[]/total_stress_mpa",
    "/wells/*/shallow_column_scenarios[]/total_stress_pa",
    "/wells/*/gap_threshold_sensitivity[]/threshold_tvd_m",
))

JSON_NULLABLE_PATHS = frozenset((
    "/lithology_validation/violations[]/field",
    "/lithology_validation/violations[]/location",
    "/wells/*/bridged_increment_pa", "/wells/*/measured_increment_mpa",
    "/wells/*/measured_increment_pa", "/wells/*/seabed_tvdss_m",
    "/wells/*/rhob_eligible_p05_kg_m3",
    "/wells/*/shallow_unresolved_thickness_tvd_m",
    "/wells/*/terminal_unresolved_thickness_tvd_m",
))

OVERBURDEN_BUNDLE = PolicyBundle(
    name="increment7_density_overburden",
    field_policies=_FIELD_POLICIES + _MANIFEST_POLICIES,
    statements=_STATEMENT_LIST,
    templates=_TEMPLATE_LIST,
    labels=OVERBURDEN_LABELS,
    csv_schemas=OVERBURDEN_CSV_SCHEMAS,
    manifest_artifact=OVERBURDEN_MANIFEST_ARTIFACT,
    json_object_keys=JSON_OBJECT_KEYS,
    json_list_item_kinds=JSON_LIST_ITEM_KINDS,
    json_boolean_paths=JSON_BOOLEAN_PATHS,
    json_integer_paths=JSON_INTEGER_PATHS,
    json_number_paths=JSON_NUMBER_PATHS,
    json_nullable_paths=JSON_NULLABLE_PATHS,
    approved_well_keys=APPROVED_WELL_KEYS,
    field_types=OVERBURDEN_FIELD_TYPES,
)

#: The nine deterministic Increment 7 artifacts this policy governs.
OVERBURDEN_ARTIFACTS = OVERBURDEN_BUNDLE.artifacts
