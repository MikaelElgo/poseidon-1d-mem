"""
Increment 6.1.7 - SCHEMA-DRIVEN, FAILURE-ATOMIC OUTPUT AUTHORIZATION.

Increment 6.1.5 introduced positive authorization and closed
`validate_no_prohibited_interpretation`. It then validated a scope that the
manifest builder RECONSTRUCTED from dispositions, confidences and masks - a
parallel object, not the records actually written to disk. The consequence was
demonstrable: a `GrEndpointScenario` carrying
`description="The interval is chalk."` was persisted verbatim by
`build_gr_endpoint_scenario_rows()`, while that string never entered the
143-field scope and so could not move `named_lithology_assigned`.

The unit validator was closed. The 6.1.6 export path still discovered fields
from their values: missing fields, empty strings, non-string substitutions and
unknown numeric-looking fields could escape the occurrence collector. It also
wrote directly into the official directory before its post-write check and
compared aggregate counts rather than every authorized value.

This module closes those gaps with independent, exact artifact schemas. Schema
validation checks artifact inventory, keys, ordered CSV columns, requiredness,
types and finite numeric values before content authorization. Export writes a
complete candidate set into an isolated sibling directory, re-reads it,
re-validates it, and compares a type-aware canonical representation of every
field and row before publishing. Validation or serializer failure leaves the
official destination unchanged.

CATEGORIES (closed; an unknown category, artifact, column or JSON path fails):

  structural_enum        fixed vocabulary enumerated per field
  identifier             approved well / scenario identifiers
  filename               bare basename, no separators, approved extension
  typed_label            APPROVED_LABELS[(field_kind, value)] - both required
  registered_statement   exact text of a registered statement, by id
  controlled_template    registered template rendered with typed substitutions
  structured_diagnostic  machine-generated, grammar-constrained; no free prose
  sanitized_diagnostic   dynamic operator text under an explicit safety contract

There is deliberately NO general-purpose category admitting arbitrary prose.

SCOPE OF THE GUARANTEE. `structured_diagnostic` and `sanitized_diagnostic` are
NOT covered by the controlled-interpretation guarantee, and are counted and
reported separately. `structured_diagnostic` values must match a declared
grammar of `name=integer` / `name(number<number)` / `CODE:token` items, which
admits no sentence. `sanitized_diagnostic` covers the operator-facing issue
`message` and `context` only; its contract is bounded length, a restricted
character set, no path separator, no newline and no absolute path, and it is
tested separately. It is not claimed to be interpretation-controlled.
"""

from typing import Dict, Optional, Tuple

from p2mem.wellframe_models import (
    APPROVED_LABELS,
    Authorization,
    FIELD_TYPES,
    RegisteredStatement,
    RegisteredTemplate,
    approved_label,
    find_prohibited_lithology_terms,
)

__all__ = [
    "CATEGORIES", "SCOPE_OUTPUT", "FieldPolicy", "OUTPUT_FIELD_POLICY",
    "OUTPUT_STATEMENTS", "OUTPUT_TEMPLATES", "OUTPUT_ARTIFACTS", "CSV_SCHEMAS",
    "FieldOccurrence", "CoverageReport",
    "collect_string_fields", "authorize_occurrence", "validate_artifact_schema",
    "validate_emitted_records", "canonicalize_emitted_records",
    "export_authorized_outputs", "OutputAuthorizationError",
    "SANITIZED_DIAGNOSTIC_MAX_LEN", "SANITIZED_DIAGNOSTIC_CHARSET",
]

#: Statements registered because they are EMITTED, distinct from the
#: scope-level registry in `wellframe_models`.
SCOPE_OUTPUT = "output"

CATEGORIES: Tuple[str, ...] = (
    "structural_enum", "identifier", "filename", "typed_label",
    "registered_statement", "controlled_template",
    "structured_diagnostic", "sanitized_diagnostic",
)

#: Categories covered by the controlled-interpretation guarantee.
CONTROLLED_CATEGORIES: Tuple[str, ...] = (
    "typed_label", "registered_statement", "controlled_template",
)
#: Categories that carry no interpretation and are counted separately.
STRUCTURAL_CATEGORIES: Tuple[str, ...] = (
    "structural_enum", "identifier", "filename",
)
#: Explicitly OUTSIDE the controlled-interpretation guarantee.
UNGUARANTEED_CATEGORIES: Tuple[str, ...] = (
    "structured_diagnostic", "sanitized_diagnostic",
)


class FieldPolicy:
    """The declared classification of one emitted string field."""

    __slots__ = ("artifact", "field", "category", "field_kind",
                 "allowed_values", "statement_ids", "template_id",
                 "allow_empty")

    def __init__(self, artifact, field, category, field_kind=None,
                 allowed_values=(), statement_ids=(), template_id=None,
                 allow_empty=False):
        # `allowed_values` on a controlled_template declares enumerated SENTINELS
        # (e.g. "not_applicable_..."), and `statement_ids` declares registered
        # alternatives. Together they are the field's complete closed form set.
        if category not in CATEGORIES:
            raise ValueError(f"{artifact}:{field}: unknown category {category!r}")
        self.artifact = artifact
        self.field = field
        self.category = category
        self.field_kind = field_kind
        self.allowed_values = tuple(allowed_values)
        self.statement_ids = tuple(statement_ids)
        self.template_id = template_id
        self.allow_empty = bool(allow_empty)

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"FieldPolicy({self.artifact!r}, {self.field!r}, {self.category!r})"


_OUTPUT_STATEMENT_LIST: Tuple[RegisteredStatement, ...] = (
    RegisteredStatement(
        statement_id="boreas_excluded_confidence_rationale",
        scope=SCOPE_OUTPUT,
        text="Formally excluded from every GR-derived calculation (exclusion_reason='BOREAS_ECGR_SCALE_UNRESOLVED'). The curve remains available for factual raw QC display and availability reporting only. Good coverage does not resolve an unresolved scale/acquisition anomaly, so coverage statistics do not override this classification.",
        purpose="The per-well confidence rationale emitted for the excluded well, where "
                "no measured proxy statistics exist to render the template.",
        provenance="Enumerated from the ACTUAL emitted manifest record."),
    RegisteredStatement(
        statement_id="eligibility_interval_register_limitations",
        scope=SCOPE_OUTPUT,
        text="Candidate/eligible DATA extent only. GROSS thickness is the block's endpoint span and, under the configured contiguity policy, may include explicitly bridged ineligible samples (see n_bridged_samples); NET thickness removes those gaps. Neither is an unqualified 'eligible thickness'. A sonic-NCT-candidate interval is not proof of normal compaction, is not a fitted trend, and is not a selected donor interval. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of eligibility_interval_register.csv.",
        provenance="Enumerated from the ACTUAL emitted eligibility_interval_register.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_endpoint_scenarios_description_1",
        scope=SCOPE_OUTPUT,
        text="Conventional mid-range bracket. Chosen for comparability with common screening practice, NOT because any evidence in this project supports it over the other two.",
        purpose="Persisted as the 'description' field of gr_endpoint_scenarios.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_endpoint_scenarios.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_endpoint_scenarios_description_2",
        scope=SCOPE_OUTPUT,
        text="Narrow bracket: a high low-endpoint and a low high-endpoint. This compresses the normalization range, so more samples clip at both ends and the proxy saturates sooner. Reported to show the upper bound of apparent proxy magnitude.",
        purpose="Persisted as the 'description' field of gr_endpoint_scenarios.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_endpoint_scenarios.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_endpoint_scenarios_description_3",
        scope=SCOPE_OUTPUT,
        text="Wide bracket: a low low-endpoint and a high high-endpoint. This expands the normalization range, so fewer samples clip and the proxy is damped. Reported to show the lower bound of apparent proxy magnitude.",
        purpose="Persisted as the 'description' field of gr_endpoint_scenarios.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_endpoint_scenarios.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_endpoint_scenarios_limitations",
        scope=SCOPE_OUTPUT,
        text="Endpoints are ASSUMED, configured percentile values estimated from this well's OWN samples. They are not calibrated, are not shared across wells, and must never be presented as a validated endpoint pair. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of gr_endpoint_scenarios.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_endpoint_scenarios.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_family_qc_summary_limitations",
        scope=SCOPE_OUTPUT,
        text="Descriptive statistics of the curve AS RECORDED. No environmental correction, rescaling, or cross-well normalization applied. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of gr_family_qc_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_family_qc_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_family_qc_summary_statistics_basis",
        scope=SCOPE_OUTPUT,
        text="Descriptive statistics over finite samples of this well's OWN GR-family curve, in its own recorded API units. No environmental correction, rescaling, normalization, or cross-well transfer of any kind has been applied. These numbers describe the curve as recorded and imply no lithology.",
        purpose="Persisted as the 'statistics_basis' field of gr_family_qc_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_family_qc_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="gr_proxy_sensitivity_summary_limitations",
        scope=SCOPE_OUTPUT,
        text="IGR and the linear screening proxy are dimensionless quantities derived under ASSUMED endpoints. The proxy is NOT a calibrated shale volume and NOT a lithology. Clipped and unclipped indices are computed and retained together in memory; the clipped counts here quantify how far the real data fell outside the assumed endpoint bracket. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of gr_proxy_sensitivity_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted gr_proxy_sensitivity_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_limitations_1",
        scope=SCOPE_OUTPUT,
        text="ELIGIBILITY IS NOT VALIDITY. This is a necessary, not sufficient, condition for a LATER method; the method itself is not implemented, not fitted, and not validated in Increment 6. CANDIDATE DATA ONLY - no NCT fitted. This mask does not fit a trend, does not select a donor interval, does not claim normal compaction, and does not claim overpressure. It is not proof that any interval is normally compacted, and it assigns no lithology. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_limitations_2",
        scope=SCOPE_OUTPUT,
        text="ELIGIBILITY IS NOT VALIDITY. This is a necessary, not sufficient, condition for a LATER method; the method itself is not implemented, not fitted, and not validated in Increment 6. Eligibility is a necessary, not sufficient, condition. Increment 6 does not fill missing density and does not compute vertical stress. A log that begins well below the seabed cannot support an overburden integral from surface regardless of how many of its own samples are eligible. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_limitations_3",
        scope=SCOPE_OUTPUT,
        text="ELIGIBILITY IS NOT VALIDITY. This is a necessary, not sufficient, condition for a LATER method; the method itself is not implemented, not fitted, and not validated in Increment 6. Input-admissibility only. Increment 6 computes no Young's modulus, Poisson ratio, bulk modulus, or shear modulus. The Vp/Vs condition is a CONFIGURED NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN (inclusive at Vp/Vs = sqrt(2), where nu = 0 exactly), not a test of physical possibility. Excluded ratios are diagnosed by regime: non-positive bulk modulus (Vp/Vs <= sqrt(4/3), genuinely outside the isotropic elastic model); positive bulk modulus with negative Poisson ratio (sqrt(4/3) < Vp/Vs < sqrt(2), unusual and outside this project's conservative policy, but NOT non-physical); and above the configured plausibility maximum (Vp/Vs > 4, a project credibility limit, not a Poisson-domain boundary). These are never aggregated into a single 'non-physical' count. No excluded sample is deleted from the well frame or corrected. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_purpose_1",
        scope=SCOPE_OUTPUT,
        text="Marks samples technically admissible as input to a LATER dynamic-elastic calculation. Increment 6 computes NO elastic property - no Young's modulus, no Poisson ratio, no bulk or shear modulus. It only records where the three required inputs coexist and pass the configured non-negative-Poisson-ratio applicability screen. Excluded Vp/Vs values are diagnosed BY REGIME (non-positive bulk modulus; positive bulk modulus with negative Poisson ratio; above the configured plausibility maximum) and are never aggregated under a single \"non-physical\" label.",
        purpose="Persisted as the 'purpose' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_purpose_2",
        scope=SCOPE_OUTPUT,
        text="Marks samples technically admissible as input to a LATER vertical-stress (Sv) integration. Increment 6 neither fills missing density nor computes Sv; a sample being eligible says nothing about whether an integration over it would be defensible, since a density log that starts at ~470 m TVDSS cannot by itself support an overburden integral from surface.",
        purpose="Persisted as the 'purpose' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="method_eligibility_summary_purpose_3",
        scope=SCOPE_OUTPUT,
        text="Marks samples that are CANDIDATE DATA for a LATER sonic normal-compaction -trend analysis. This is a data-admissibility mask and nothing more. It does NOT fit a trend, does NOT select a donor interval, does NOT claim normal compaction, does NOT claim overpressure, and must never be read as evidence that any interval is normally compacted or is any named lithology.",
        purpose="Persisted as the 'purpose' field of method_eligibility_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted method_eligibility_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_calibration_data_available_statement",
        scope=SCOPE_OUTPUT,
        text="No RFT, MDT, DST, FIT, LOT, XLOT or DFIT data exist for this project. The supplied Vp/Vs text file is derived from the existing sonic curves and is NOT independent calibration data. Every quantity in this increment therefore remains uncalibrated.",
        purpose="Persisted as the '/calibration_data_available/statement' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_increment_title",
        scope=SCOPE_OUTPUT,
        text="Gamma-Ray QC, Shale-Proxy Sensitivity, Well-Frame Assembly, and Method-Eligibility Framework",
        purpose="Persisted as the '/increment_title' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_1",
        scope=SCOPE_OUTPUT,
        text="A sonic-NCT-candidate interval is candidate DATA only. It is not a fitted trend, not a selected donor interval, and not evidence of normal compaction or overpressure.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_2",
        scope=SCOPE_OUTPUT,
        text="Boreas 1 is formally excluded from all GR-derived work under BOREAS_ECGR_SCALE_UNRESOLVED and is retained for factual raw QC display only. It is excluded rather than corrected because no calibration evidence exists to support any correction.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_3",
        scope=SCOPE_OUTPUT,
        text="Eligibility is a necessary, not sufficient, condition. No method gated by these masks is implemented, fitted, or validated in this increment.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_4",
        scope=SCOPE_OUTPUT,
        text="GR endpoints are ASSUMED configured percentiles of each well's own samples, never calibrated and never shared across wells.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_5",
        scope=SCOPE_OUTPUT,
        text="No named lithology is assigned, and the available data do not support assigning one.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_6",
        scope=SCOPE_OUTPUT,
        text="Poseidon North 1 and Proteus 1ST2 have no approved formation tops; their results are depth-tied and stratigraphically unvalidated.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_limitations_7",
        scope=SCOPE_OUTPUT,
        text="Tier C - screening-level and uncalibrated. Nothing here is validated against independent measurement.",
        purpose="Persisted as the '/limitations[]' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="lithology_validation_derivation",
        scope=SCOPE_OUTPUT,
        text='named_lithology_assigned is DERIVED at a SCHEMA-DRIVEN EMISSION BOUNDARY. Exact artifact schemas validate inventory, keys, ordered CSV columns, requiredness, types and finite numeric values independently of content. Every declared string occurrence - including empty and numeric-looking strings - is then positively authorized as an approved (field_kind, value) label, a registered statement matched by id and exact text, a registered template rendered with typed substitutions, an enumerated structural value, or a declared machine-diagnostic grammar. Export writes only to an isolated staging directory, re-reads and re-validates the candidate bytes, and requires a type-aware canonical match of every field and row before publication; a rejected export leaves the official destination unchanged. This is NOT a claim that the software recognizes natural-language lithology; the prohibited-term list is a diagnostic linter that authorizes nothing. Machine diagnostics and operator-facing issue text are counted separately and are outside the controlled-interpretation guarantee.',
        purpose="Persisted as manifest lithology_validation.derivation. Describes the "
                "Increment 6.1.7 schema-driven, failure-atomic emission-boundary model "
                "that is actually implemented, superseding the incomplete 6.1.6 wording.",
        provenance="Registered so the assurance prose is itself authorized like any other "
                   "emitted field, and cannot drift from the implementation silently."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_named_lithology_statement",
        scope=SCOPE_OUTPUT,
        text="NO named lithology is assigned anywhere in Increment 6. Gamma-ray response is not uniquely diagnostic of rock type, and no independent lithological evidence (core, cuttings description, image log, spectral GR, or calibrated multi-mineral solution) is available in this project. Low-GR intervals occur independently in each of the three GR-eligible wells; cross-well stratigraphic persistence is NOT established, and cannot be, because two of those wells have no approved formation tops. Those intervals therefore remain UNRESOLVED in lithology. All classifications in this increment describe DATA AND PROXY CONFIDENCE ONLY.",
        purpose="Persisted as the '/named_lithology_statement' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="petrophysics_eligibility_manifest_nonlinear_vsh_deferral_statement",
        scope=SCOPE_OUTPUT,
        text="No nonlinear Vsh transform (Larionov, Clavier, Stieber, or any other) is implemented. Each would require a retrieved, verified primary-source method record and a closed method-register entry; none exists in this project.",
        purpose="Persisted as the '/nonlinear_vsh_deferral_statement' field of petrophysics_eligibility_manifest.json.",
        provenance="Enumerated from the ACTUAL emitted petrophysics_eligibility_manifest.json record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
    RegisteredStatement(
        statement_id="thickness_sensitivity_summary_limitations",
        scope=SCOPE_OUTPUT,
        text="Eligible/candidate DATA extent only. No gated method is implemented, fitted, or validated. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="Persisted as the 'limitations' field of thickness_sensitivity_summary.csv.",
        provenance="Enumerated from the ACTUAL emitted thickness_sensitivity_summary.csv record. Authorization is by id and exact text at the emission boundary, not from a parallel reconstructed scope."),
)

OUTPUT_STATEMENTS = {s.statement_id: s for s in _OUTPUT_STATEMENT_LIST}

_SEABED_TEMPLATE = (
    "Counted where canonical LAS MD_m < {seabed_mdrt_m} m MDRT, the seabed marker's "
    "reconciled MDRT from the LOCKED Increment 5 survey-corrected output."
)
_POPULATION_TEMPLATE = (
    "Totals cover the {n_qualifying} block(s) meeting the configured minimums out of "
    "{n_found} found under the {policy} contiguity policy. GROSS is the sum of block "
    "endpoint spans and includes {n_bridged_samples} disclosed bridged sample(s) across "
    "{n_bridged_gaps} bridged gap(s) in {n_interrupted} interrupted block(s); NET removes "
    "those gaps."
)
_RATIONALE_TEMPLATE = (
    "valid_fraction={valid_fraction}, dynamic_range_p05_p95={dynamic_range_p05_p95} API, "
    "proxy_median_spread_across_3_scenarios={proxy_median_spread}. Describes confidence in "
    "the DATA and the SCREENING PROXY only; asserts no lithology and no calibration."
)

_OUTPUT_TEMPLATE_LIST: Tuple[RegisteredTemplate, ...] = (
    RegisteredTemplate(
        template_id="seabed_basis", scope=SCOPE_OUTPUT, template=_SEABED_TEMPLATE,
        fields={"seabed_mdrt_m": "decimal"},
        purpose="Persisted as the 'seabed_basis' field of gr_family_qc_summary.csv.",
        provenance="Fixed prose with one MEASURED depth. Enumerated from the actual "
                   "emitted record; the substitution is restricted to a decimal literal."),
    RegisteredTemplate(
        template_id="population_statement", scope=SCOPE_OUTPUT,
        template=_POPULATION_TEMPLATE,
        fields={"n_qualifying": "integer", "n_found": "integer",
                "policy": "quoted_policy_name", "n_bridged_samples": "integer",
                "n_bridged_gaps": "integer", "n_interrupted": "integer"},
        purpose="Persisted as the 'population_statement' field of "
                "thickness_sensitivity_summary.csv.",
        provenance="Fixed prose with five MEASURED counts and one enumerated policy "
                   "name. Enumerated from the actual emitted record."),
    RegisteredTemplate(
        template_id="gr_proxy_confidence_rationale", scope=SCOPE_OUTPUT,
        template=_RATIONALE_TEMPLATE,
        fields={"valid_fraction": "decimal", "dynamic_range_p05_p95": "decimal",
                "proxy_median_spread": "decimal"},
        purpose="Persisted as the per-well 'gr_proxy_confidence_rationale'.",
        provenance="Fixed prose with three MEASURED numbers. Enumerated from the "
                   "actual emitted record."),
)

OUTPUT_TEMPLATES = {t.template_id: t for t in _OUTPUT_TEMPLATE_LIST}

_dupe = sorted({i for i in
                [s.statement_id for s in _OUTPUT_STATEMENT_LIST]
                + [t.template_id for t in _OUTPUT_TEMPLATE_LIST]
                if ([s.statement_id for s in _OUTPUT_STATEMENT_LIST]
                    + [t.template_id for t in _OUTPUT_TEMPLATE_LIST]).count(i) > 1})
if _dupe:  # pragma: no cover - fails at import if violated
    raise ValueError(f"duplicate output registry ids: {_dupe}")
del _dupe


def _is_integer_literal(value):
    if isinstance(value, bool) or not isinstance(value, str) or not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return bool(body) and body.isdigit()


def _is_quoted_policy_name(value):
    return isinstance(value, str) and value in ("'configured_bridging'", "'strict_no_gap'")


#: Substitution types available to OUTPUT templates. Every one is a predicate
#: over the substituted STRING - never a judgement about its meaning.
OUTPUT_FIELD_TYPES = dict(FIELD_TYPES)
OUTPUT_FIELD_TYPES["integer"] = _is_integer_literal
OUTPUT_FIELD_TYPES["quoted_policy_name"] = _is_quoted_policy_name


OUTPUT_FIELD_POLICY_LIST: Tuple[FieldPolicy, ...] = (
    # Increment 6.1.6 assurance-metadata paths. The `violations[]` records are
    # DIAGNOSTIC: they exist only when something failed, and they are explicitly
    # outside the controlled-interpretation guarantee (counted separately).
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/model",
        category="structural_enum",
        allowed_values=("schema_driven_transactional_authorization_at_emission_boundary",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/violations[]/context",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/violations[]/reason",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/violations[]/scope",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/violations[]/terms[]",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/emitted_field_coverage/artifacts_inspected[]",
        category="identifier",
        allowed_values=(
            "eligibility_interval_register.csv", "gr_endpoint_scenarios.csv",
            "gr_family_qc_summary.csv", "gr_proxy_sensitivity_summary.csv",
            "method_eligibility_summary.csv", "petrophysics_eligibility_issues.csv",
            "petrophysics_eligibility_manifest.json",
            "thickness_sensitivity_summary.csv")),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/emitted_field_coverage/status",
        category="structural_enum", allowed_values=("not_supplied",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/emitted_field_coverage/note",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="contiguity_policy",
        category="structural_enum",
        allowed_values=(
            "configured_bridging",
            "strict_no_gap",
        )),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="depth_basis_used",
        category="structural_enum",
        allowed_values=(
            "petrel_source_trace",
        )),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("eligibility_interval_register_limitations",)),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="limiting_reason",
        category="structured_diagnostic",
        allowed_values=("none_meets_all_configured_minimums",)),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="mask_name",
        category="typed_label",
        field_kind="mask_name"),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        ),
        allow_empty=True),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "metres",
        )),
    FieldPolicy(
        artifact="eligibility_interval_register.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Boreas_1",
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="calibration_status",
        category="structural_enum",
        allowed_values=(
            "uncalibrated_assumed_no_calibration_data_exists",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="description",
        category="registered_statement",
        statement_ids=("gr_endpoint_scenarios_description_1", "gr_endpoint_scenarios_description_2", "gr_endpoint_scenarios_description_3",)),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="endpoint_sample_basis",
        category="structural_enum",
        allowed_values=(
            "finite_and_depth_mapped_samples_only",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="evidence_class",
        category="typed_label",
        field_kind="evidence_class"),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("gr_endpoint_scenarios_limitations",)),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "API",
        )),
    FieldPolicy(
        artifact="gr_endpoint_scenarios.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="depth_basis",
        category="structural_enum",
        allowed_values=(
            "MDRT (measured depth below rotary table), metres",
        )),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="evidence_class",
        category="typed_label",
        field_kind="evidence_class"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="exclusion_reason",
        category="typed_label",
        field_kind="exclusion_reason",
        allow_empty=True),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="gr_family_canonical_name",
        category="typed_label",
        field_kind="gr_family_canonical_name"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="gr_family_source_curve_name",
        category="typed_label",
        field_kind="gr_family_source_curve_name"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="gr_proxy_confidence_class",
        category="typed_label",
        field_kind="gr_proxy_confidence_class"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("gr_family_qc_summary_limitations",)),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="seabed_basis",
        category="controlled_template",
        template_id="seabed_basis",
        allowed_values=('Not determinable: this well has no approved formation-top file, so no seabed marker exists in the locked Increment 5 output. Reported as None (unknown), never as 0.',)),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="source_las_filename",
        category="filename"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="statistics_basis",
        category="registered_statement",
        statement_ids=("gr_family_qc_summary_statistics_basis",)),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "API",
        )),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="use_status",
        category="typed_label",
        field_kind="use_status"),
    FieldPolicy(
        artifact="gr_family_qc_summary.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Boreas_1",
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="calibration_status",
        category="structural_enum",
        allowed_values=(
            "screening_proxy_uncalibrated_not_a_shale_volume",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="evidence_class",
        category="typed_label",
        field_kind="evidence_class"),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="gr_family_canonical_name",
        category="typed_label",
        field_kind="gr_family_canonical_name"),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("gr_proxy_sensitivity_summary_limitations",)),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="proxy_field_name",
        category="structural_enum",
        allowed_values=(
            "VSH_GR_linear_proxy_frac",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="transform_name",
        category="structural_enum",
        allowed_values=(
            "linear_identity_of_clipped_igr",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "dimensionless_fraction",
        )),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="use_status",
        category="typed_label",
        field_kind="use_status"),
    FieldPolicy(
        artifact="gr_proxy_sensitivity_summary.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="criteria_counts",
        category="structured_diagnostic"),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="depth_basis_used",
        category="structural_enum",
        allowed_values=(
            "petrel_source_trace",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="depth_map_status",
        category="structural_enum",
        allowed_values=(
            "fully_mapped_within_survey_coverage",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="diagnostic_counts",
        category="structured_diagnostic",
        allow_empty=True),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="exclusion_reason",
        category="typed_label",
        field_kind="exclusion_reason",
        allow_empty=True),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="interpolation_method",
        category="structural_enum",
        allowed_values=(
            "piecewise_linear_station_interpolation",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("method_eligibility_summary_limitations_1", "method_eligibility_summary_limitations_2", "method_eligibility_summary_limitations_3",)),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="limiting_criterion",
        category="structural_enum",
        allowed_values=(
            # Enumerated from the criterion vocabulary the mask builder can
            # emit, not merely from the values one dataset happened to hit.
            "depth_mapped",
            "gr_disposition_approved",
            "proxy_at_or_above_threshold",
            "proxy_finite",
            "rhob_finite",
            "rhob_finite_in_bounds",
            "rhob_within_physical_bounds",
            "sonic_finite",
            "vp_finite_in_bounds",
            "vp_finite_positive_in_bounds",
            "vs_finite_positive_in_bounds",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="mask_name",
        category="typed_label",
        field_kind="mask_name"),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="purpose",
        category="registered_statement",
        statement_ids=("method_eligibility_summary_purpose_1", "method_eligibility_summary_purpose_2", "method_eligibility_summary_purpose_3",)),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        ),
        allow_empty=True),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "sample_count_and_fraction",
        )),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="use_status",
        category="typed_label",
        field_kind="use_status"),
    FieldPolicy(
        artifact="method_eligibility_summary.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Boreas_1",
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_issues.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_issues.csv",
        field="code",
        category="structural_enum",
        allowed_values=(
            "GR_DERIVED_CALCULATION_SKIPPED_BY_EXCLUSION",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_issues.csv",
        field="context",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_issues.csv",
        field="message",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_issues.csv",
        field="severity",
        category="structural_enum",
        allowed_values=(
            "WARNING",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/calibration_data_available/statement",
        category="registered_statement",
        statement_ids=("petrophysics_eligibility_manifest_calibration_data_available_statement",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/config_filename",
        category="structural_enum",
        allowed_values=(
            "petrophysics_eligibility.yml",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/config_schema_version",
        category="structural_enum",
        allowed_values=(
            "6.0",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/depth_reference_convention",
        category="structural_enum",
        allowed_values=(
            "MD and TVD are referenced to the well datum (rotary table), increasing downward; TVDSS_m = TVD_m - DatumElevation_m, with datum elevation referenced to MSL, positive upward. Identical to the LOCKED Increment 3.1.1 convention - not re-derived here.",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/increment_title",
        category="registered_statement",
        statement_ids=("petrophysics_eligibility_manifest_increment_title",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/issues[]/code",
        category="structural_enum",
        allowed_values=(
            "GR_DERIVED_CALCULATION_SKIPPED_BY_EXCLUSION",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/issues[]/context",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/issues[]/message",
        category="sanitized_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/issues[]/severity",
        category="structural_enum",
        allowed_values=(
            "WARNING",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/limitations[]",
        category="registered_statement",
        statement_ids=("petrophysics_eligibility_manifest_limitations_1", "petrophysics_eligibility_manifest_limitations_2", "petrophysics_eligibility_manifest_limitations_3", "petrophysics_eligibility_manifest_limitations_4", "petrophysics_eligibility_manifest_limitations_5", "petrophysics_eligibility_manifest_limitations_6", "petrophysics_eligibility_manifest_limitations_7",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/lithology_validation/derivation",
        category="registered_statement",
        statement_ids=("lithology_validation_derivation",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/methods_not_implemented[]",
        category="structural_enum",
        allowed_values=(
            "bowers_pore_pressure",
            "density_reconstruction_or_extrapolation",
            "dynamic_elastic_property_calculation",
            "eaton_resistivity_pore_pressure",
            "eaton_sonic_pore_pressure",
            "environmental_gr_correction",
            "friction_angle_modelling",
            "gr_rescaling_or_normalization_across_wells",
            "hydrostatic_pressure_modelling",
            "mud_weight_recommendation",
            "named_lithology_interpretation",
            "normal_compaction_trend_fitting",
            "rock_strength_correlation",
            "shmin_shmax_modelling",
            "static_elastic_conversion",
            "stress_polygon_construction",
            "vertical_stress_integration",
            "wellbore_stability_analysis",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/named_lithology_statement",
        category="registered_statement",
        statement_ids=("petrophysics_eligibility_manifest_named_lithology_statement",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/nonlinear_vsh_deferral_statement",
        category="registered_statement",
        statement_ids=("petrophysics_eligibility_manifest_nonlinear_vsh_deferral_statement",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/depth_basis_used",
        category="structural_enum",
        allowed_values=(
            "petrel_source_trace",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/depth_map_status",
        category="structural_enum",
        allowed_values=(
            "fully_mapped_within_survey_coverage",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/endpoint_scenarios[]/calibration_status",
        category="structural_enum",
        allowed_values=(
            "uncalibrated_assumed_no_calibration_data_exists",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/endpoint_scenarios[]/evidence_class",
        category="typed_label",
        field_kind="evidence_class"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/endpoint_scenarios[]/scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/exclusion_reason",
        category="typed_label",
        field_kind="exclusion_reason"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/gr_family_canonical_name",
        category="typed_label",
        field_kind="gr_family_canonical_name"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/gr_family_source_curve_name",
        category="typed_label",
        field_kind="gr_family_source_curve_name"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/gr_proxy_confidence_class",
        category="typed_label",
        field_kind="gr_proxy_confidence_class"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/gr_proxy_confidence_rationale",
        category="controlled_template",
        template_id="gr_proxy_confidence_rationale",
        statement_ids=("boreas_excluded_confidence_rationale",)),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/interpolation_method",
        category="structural_enum",
        allowed_values=(
            "piecewise_linear_station_interpolation",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/method_eligibility[]/limiting_criterion",
        category="structural_enum",
        allowed_values=(
            # Enumerated from the criterion vocabulary the mask builder can
            # emit, not merely from the values one dataset happened to hit.
            "depth_mapped",
            "gr_disposition_approved",
            "proxy_at_or_above_threshold",
            "proxy_finite",
            "rhob_finite",
            "rhob_finite_in_bounds",
            "rhob_within_physical_bounds",
            "sonic_finite",
            "vp_finite_in_bounds",
            "vp_finite_positive_in_bounds",
            "vs_finite_positive_in_bounds",
        )),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/method_eligibility[]/mask_name",
        category="typed_label",
        field_kind="mask_name"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/method_eligibility[]/scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        ),
        allow_empty=True),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/qc_flags[]",
        category="structured_diagnostic"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/source_las_filename",
        category="filename"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/source_survey_filename",
        category="filename"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/use_status",
        category="typed_label",
        field_kind="use_status"),
    FieldPolicy(
        artifact="petrophysics_eligibility_manifest.json",
        field="/wells/*/well_identity_evidence_status",
        category="structural_enum",
        allowed_values=(
            "verified_against_file_well_header",
        )),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="assurance_tier",
        category="structural_enum",
        allowed_values=(
            "Tier C - Screening-Level / Uncalibrated Educational",
        )),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="contiguity_policy",
        category="structural_enum",
        allowed_values=(
            "configured_bridging",
            "strict_no_gap",
        )),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="limitations",
        category="registered_statement",
        statement_ids=("thickness_sensitivity_summary_limitations",)),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="mask_name",
        category="typed_label",
        field_kind="mask_name"),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="population_statement",
        category="controlled_template",
        template_id="population_statement"),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="scenario_name",
        category="identifier",
        allowed_values=(
            "base",
            "high",
            "low",
        ),
        allow_empty=True),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="unit",
        category="structural_enum",
        allowed_values=(
            "metres",
        )),
    FieldPolicy(
        artifact="thickness_sensitivity_summary.csv",
        field="well_key",
        category="identifier",
        allowed_values=(
            "Boreas_1",
            "Poseidon_2",
            "Poseidon_North_1",
            "Proteus_1ST2",
        )),
)

OUTPUT_FIELD_POLICY: Dict[Tuple[str, str], FieldPolicy] = {}
for _pol in OUTPUT_FIELD_POLICY_LIST:
    _key = (_pol.artifact, _pol.field)
    if _key in OUTPUT_FIELD_POLICY:  # pragma: no cover - fails at import
        raise ValueError(f"duplicate output field policy {_key}")
    OUTPUT_FIELD_POLICY[_key] = _pol
del _pol, _key

# ---------------------------------------------------------------------------
# Closed artifact schemas.  Unlike the 6.1.6 collector, these declarations do
# not infer a field's existence or type from its value.  Keys are validated
# first, including empty and non-string values, and content authorization is a
# separate second operation.
# ---------------------------------------------------------------------------


class CsvArtifactSchema:
    """Exact ordered columns and pre/post-serialization types for one CSV."""

    __slots__ = ("columns", "integer_fields", "number_fields", "boolean_fields",
                 "nullable_fields", "min_rows")

    def __init__(self, columns, integer_fields=(), number_fields=(),
                 boolean_fields=(), nullable_fields=(), min_rows=1):
        self.columns = tuple(columns)
        self.integer_fields = frozenset(integer_fields)
        self.number_fields = frozenset(number_fields)
        self.boolean_fields = frozenset(boolean_fields)
        self.nullable_fields = frozenset(nullable_fields)
        self.min_rows = int(min_rows)
        declared = set(self.columns)
        typed = self.integer_fields | self.number_fields | self.boolean_fields
        if len(declared) != len(self.columns):
            raise ValueError("CSV schema contains duplicate columns")
        if not typed <= declared or not self.nullable_fields <= declared:
            raise ValueError("CSV schema type/nullability references an unknown column")
        if ((self.integer_fields & self.number_fields)
                or (self.integer_fields & self.boolean_fields)
                or (self.number_fields & self.boolean_fields)):
            raise ValueError("CSV schema type partitions overlap")

    @property
    def string_fields(self):
        return frozenset(self.columns) - self.integer_fields - self.number_fields - self.boolean_fields

    def kind(self, field):
        if field in self.integer_fields:
            return "integer"
        if field in self.number_fields:
            return "number"
        if field in self.boolean_fields:
            return "boolean"
        return "string"


CSV_SCHEMAS = {
    "eligibility_interval_register.csv": CsvArtifactSchema(
        columns=(
            "well_key", "mask_name", "contiguity_policy", "scenario_name",
            "proxy_threshold", "block_index", "start_index", "end_index",
            "n_samples", "n_eligible_samples", "n_bridged_samples",
            "n_bridged_gaps", "n_eligible_subruns", "meets_configured_minimums",
            "md_start_m", "md_end_m", "gross_thickness_md_m", "net_thickness_md_m",
            "tvd_start_m", "tvd_end_m", "gross_thickness_tvd_m",
            "net_thickness_tvd_m", "tvdss_start_m", "tvdss_end_m",
            "gross_thickness_tvdss_m", "net_thickness_tvdss_m", "limiting_reason",
            "depth_basis_used", "unit", "assurance_tier", "limitations",
        ),
        integer_fields=("block_index", "start_index", "end_index", "n_samples",
                        "n_eligible_samples", "n_bridged_samples", "n_bridged_gaps",
                        "n_eligible_subruns"),
        number_fields=("proxy_threshold", "md_start_m", "md_end_m",
                       "gross_thickness_md_m", "net_thickness_md_m", "tvd_start_m",
                       "tvd_end_m", "gross_thickness_tvd_m", "net_thickness_tvd_m",
                       "tvdss_start_m", "tvdss_end_m", "gross_thickness_tvdss_m",
                       "net_thickness_tvdss_m"),
        boolean_fields=("meets_configured_minimums",),
        nullable_fields=("proxy_threshold", "md_start_m", "md_end_m",
                         "gross_thickness_md_m", "net_thickness_md_m", "tvd_start_m",
                         "tvd_end_m", "gross_thickness_tvd_m", "net_thickness_tvd_m",
                         "tvdss_start_m", "tvdss_end_m", "gross_thickness_tvdss_m",
                         "net_thickness_tvdss_m")),
    "gr_endpoint_scenarios.csv": CsvArtifactSchema(
        columns=(
            "well_key", "scenario_name", "low_percentile", "high_percentile",
            "gr_low_endpoint_api", "gr_high_endpoint_api", "endpoint_separation_api",
            "n_samples_used_for_endpoints", "endpoint_sample_basis", "unit",
            "evidence_class", "calibration_status", "assurance_tier", "description",
            "limitations",
        ),
        integer_fields=("n_samples_used_for_endpoints",),
        number_fields=("low_percentile", "high_percentile", "gr_low_endpoint_api",
                       "gr_high_endpoint_api", "endpoint_separation_api")),
    "gr_family_qc_summary.csv": CsvArtifactSchema(
        columns=(
            "well_key", "source_las_filename", "gr_family_canonical_name",
            "gr_family_source_curve_name", "unit", "use_status", "exclusion_reason",
            "evidence_class", "gr_proxy_confidence_class",
            "has_approved_formation_tops", "n_samples", "valid_count", "valid_fraction",
            "min_api", "max_api", "median_api", "p01_api", "p05_api", "p10_api",
            "p25_api", "p50_api", "p75_api", "p90_api", "p95_api", "p99_api",
            "dynamic_range_p05_p95_api", "n_negative_samples", "n_zero_samples",
            "n_samples_above_seabed", "seabed_basis", "n_valid_blocks",
            "longest_valid_block_samples", "longest_missing_block_samples",
            "longest_missing_block_md_start_m", "longest_missing_block_md_end_m",
            "depth_basis", "assurance_tier", "statistics_basis", "limitations",
        ),
        integer_fields=("n_samples", "valid_count", "n_negative_samples",
                        "n_zero_samples", "n_samples_above_seabed", "n_valid_blocks",
                        "longest_valid_block_samples", "longest_missing_block_samples"),
        number_fields=("valid_fraction", "min_api", "max_api", "median_api",
                       "p01_api", "p05_api", "p10_api", "p25_api", "p50_api",
                       "p75_api", "p90_api", "p95_api", "p99_api",
                       "dynamic_range_p05_p95_api", "longest_missing_block_md_start_m",
                       "longest_missing_block_md_end_m"),
        boolean_fields=("has_approved_formation_tops",),
        nullable_fields=("valid_fraction", "min_api", "max_api", "median_api",
                         "p01_api", "p05_api", "p10_api", "p25_api", "p50_api",
                         "p75_api", "p90_api", "p95_api", "p99_api",
                         "dynamic_range_p05_p95_api", "n_samples_above_seabed",
                         "longest_missing_block_md_start_m", "longest_missing_block_md_end_m")),
    "gr_proxy_sensitivity_summary.csv": CsvArtifactSchema(
        columns=(
            "well_key", "scenario_name", "gr_family_canonical_name", "use_status",
            "gr_low_endpoint_api", "gr_high_endpoint_api", "transform_name",
            "proxy_field_name", "unit", "n_valid", "n_clipped_low", "n_clipped_high",
            "clipped_fraction", "proxy_median", "proxy_p25", "proxy_p75",
            "calibration_status", "evidence_class", "assurance_tier", "limitations",
        ),
        integer_fields=("n_valid", "n_clipped_low", "n_clipped_high"),
        number_fields=("gr_low_endpoint_api", "gr_high_endpoint_api", "clipped_fraction",
                       "proxy_median", "proxy_p25", "proxy_p75")),
    "method_eligibility_summary.csv": CsvArtifactSchema(
        columns=(
            "well_key", "mask_name", "scenario_name", "proxy_threshold",
            "lithology_dependent", "use_status", "exclusion_reason", "n_samples",
            "n_eligible", "eligible_fraction", "limiting_criterion", "criteria_counts",
            "diagnostic_counts", "depth_basis_used", "interpolation_method",
            "depth_map_status", "n_depth_unmapped", "n_extrapolated", "unit",
            "assurance_tier", "purpose", "limitations",
        ),
        integer_fields=("n_samples", "n_eligible", "n_depth_unmapped", "n_extrapolated"),
        number_fields=("proxy_threshold", "eligible_fraction"),
        boolean_fields=("lithology_dependent",),
        nullable_fields=("proxy_threshold", "n_depth_unmapped", "n_extrapolated")),
    "petrophysics_eligibility_issues.csv": CsvArtifactSchema(
        columns=("severity", "code", "context", "message", "assurance_tier"),
        min_rows=0),
    "thickness_sensitivity_summary.csv": CsvArtifactSchema(
        columns=(
            "well_key", "mask_name", "contiguity_policy", "scenario_name",
            "proxy_threshold", "n_blocks_all", "n_blocks_qualifying",
            "n_blocks_rejected_below_minimums",
            "n_bridged_samples_in_qualifying_blocks",
            "n_bridged_gaps_in_qualifying_blocks", "n_interrupted_qualifying_blocks",
            "gross_qualifying_thickness_tvdss_m", "net_qualifying_thickness_tvdss_m",
            "gross_all_block_thickness_tvdss_m", "n_eligible_samples_qualifying",
            "unit", "population_statement", "assurance_tier", "limitations",
        ),
        integer_fields=("n_blocks_all", "n_blocks_qualifying",
                        "n_blocks_rejected_below_minimums",
                        "n_bridged_samples_in_qualifying_blocks",
                        "n_bridged_gaps_in_qualifying_blocks",
                        "n_interrupted_qualifying_blocks", "n_eligible_samples_qualifying"),
        number_fields=("proxy_threshold", "gross_qualifying_thickness_tvdss_m",
                       "net_qualifying_thickness_tvdss_m",
                       "gross_all_block_thickness_tvdss_m"),
        nullable_fields=("proxy_threshold", "gross_qualifying_thickness_tvdss_m",
                         "net_qualifying_thickness_tvdss_m",
                         "gross_all_block_thickness_tvdss_m")),
}

MANIFEST_ARTIFACT = "petrophysics_eligibility_manifest.json"
APPROVED_WELL_KEYS = frozenset((
    "Boreas_1", "Poseidon_2", "Poseidon_North_1", "Proteus_1ST2",
))

# Exact object keys.  `None` denotes the dynamic `/wells` mapping, whose keys
# must equal the supplied well-key set.  No key is discovered from a leaf value.
JSON_OBJECT_KEYS = {
    "": frozenset((
        "assembly_failures", "assurance_tier", "calibration_data_available",
        "config_filename", "config_schema_version", "depth_reference_convention",
        "increment", "increment_title", "issues", "limitations",
        "lithology_validation", "methods_not_implemented", "n_wells_frame_assembled",
        "n_wells_frame_failed", "n_wells_gr_excluded", "n_wells_gr_proxy_permitted",
        "named_lithology_assigned", "named_lithology_statement",
        "nct_candidate_proxy_thresholds", "nonlinear_vsh_deferral_statement",
        "nonlinear_vsh_transforms_implemented", "total_samples_extrapolated", "wells",
    )),
    "/calibration_data_available": frozenset((
        "pressure_rft_mdt_dst", "stress_fit_lot_xlot_dfit",
        "independent_vp_vs_calibration", "statement",
    )),
    "/lithology_validation": frozenset((
        "model", "derivation", "scope_object_fields_checked",
        "scope_object_violations", "emitted_field_coverage", "violations",
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
        "context", "scope", "terms", "reason",
    )),
    "/issues[]": frozenset(("severity", "code", "context", "message")),
    "/assembly_failures[]": frozenset((
        "well_key", "failure_origin", "error_type", "message",
    )),
    "/wells": None,
    "/wells/*": frozenset((
        "source_las_filename", "source_survey_filename", "well_frame_assembled",
        "n_samples", "depth_basis_used", "interpolation_method", "depth_map_status",
        "n_depth_unmapped", "n_extrapolated", "datum_elevation_m",
        "well_identity_evidence_status", "qc_flags", "gr_family_canonical_name",
        "gr_family_source_curve_name", "use_status", "exclusion_reason",
        "has_approved_formation_tops", "gr_proxy_confidence_class",
        "gr_proxy_confidence_rationale", "gr_valid_fraction", "gr_median_api",
        "gr_min_api", "gr_max_api", "gr_n_samples_above_seabed",
        "endpoint_scenarios", "method_eligibility",
    )),
    "/wells/*/endpoint_scenarios[]": frozenset((
        "scenario_name", "gr_low_endpoint_api", "gr_high_endpoint_api",
        "endpoint_separation_api", "evidence_class", "calibration_status",
    )),
    "/wells/*/method_eligibility[]": frozenset((
        "mask_name", "scenario_name", "proxy_threshold", "n_eligible",
        "eligible_fraction", "limiting_criterion", "lithology_dependent",
    )),
}

JSON_LIST_ITEM_KINDS = {
    "/assembly_failures": "object", "/issues": "object", "/limitations": "string",
    "/lithology_validation/emitted_field_coverage/artifacts_inspected": "string",
    "/lithology_validation/violations": "object",
    "/lithology_validation/violations[]/terms": "string",
    "/methods_not_implemented": "string", "/nct_candidate_proxy_thresholds": "number",
    "/wells/*/endpoint_scenarios": "object", "/wells/*/method_eligibility": "object",
    "/wells/*/qc_flags": "string",
}

JSON_BOOLEAN_PATHS = frozenset((
    "/calibration_data_available/independent_vp_vs_calibration",
    "/calibration_data_available/pressure_rft_mdt_dst",
    "/calibration_data_available/stress_fit_lot_xlot_dfit",
    "/named_lithology_assigned", "/nonlinear_vsh_transforms_implemented",
    "/wells/*/has_approved_formation_tops",
    "/wells/*/method_eligibility[]/lithology_dependent",
    "/wells/*/well_frame_assembled",
))
JSON_INTEGER_PATHS = frozenset((
    "/increment", "/n_wells_frame_assembled", "/n_wells_frame_failed",
    "/n_wells_gr_excluded", "/n_wells_gr_proxy_permitted",
    "/total_samples_extrapolated",
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
    "/lithology_validation/scope_object_fields_checked",
    "/lithology_validation/scope_object_violations", "/wells/*/n_depth_unmapped",
    "/wells/*/n_extrapolated", "/wells/*/n_samples",
    "/wells/*/gr_n_samples_above_seabed",
    "/wells/*/method_eligibility[]/n_eligible",
))
JSON_NUMBER_PATHS = frozenset((
    "/nct_candidate_proxy_thresholds[]", "/wells/*/datum_elevation_m",
    "/wells/*/endpoint_scenarios[]/endpoint_separation_api",
    "/wells/*/endpoint_scenarios[]/gr_high_endpoint_api",
    "/wells/*/endpoint_scenarios[]/gr_low_endpoint_api", "/wells/*/gr_max_api",
    "/wells/*/gr_median_api", "/wells/*/gr_min_api", "/wells/*/gr_valid_fraction",
    "/wells/*/method_eligibility[]/eligible_fraction",
    "/wells/*/method_eligibility[]/proxy_threshold",
))
JSON_NULLABLE_PATHS = frozenset((
    "/wells/*/exclusion_reason", "/wells/*/gr_n_samples_above_seabed",
    "/wells/*/method_eligibility[]/proxy_threshold",
))

#: The eight Increment 6 deterministic artifacts this policy governs.
OUTPUT_ARTIFACTS: Tuple[str, ...] = tuple(sorted(tuple(CSV_SCHEMAS) + (MANIFEST_ARTIFACT,)))

# The string side of each schema must be classified exactly once.  This import-
# time assertion prevents a future schema/policy drift from weakening the gate.
_csv_policy_fields = {}
for (_artifact, _field), _policy in OUTPUT_FIELD_POLICY.items():
    if _artifact in CSV_SCHEMAS:
        _csv_policy_fields.setdefault(_artifact, set()).add(_field)
for _artifact, _schema in CSV_SCHEMAS.items():
    if _csv_policy_fields.get(_artifact, set()) != set(_schema.string_fields):
        raise ValueError(
            f"{_artifact}: CSV schema string fields and authorization policy differ: "
            f"schema_only={sorted(set(_schema.string_fields) - _csv_policy_fields.get(_artifact, set()))}, "
            f"policy_only={sorted(_csv_policy_fields.get(_artifact, set()) - set(_schema.string_fields))}")
del _artifact, _field, _policy, _schema, _csv_policy_fields


# ---------------------------------------------------------------------------
# Collection: the ACTUAL string fields of the ACTUAL records
# ---------------------------------------------------------------------------

#: The sanitized-diagnostic contract, stated explicitly and tested separately.
SANITIZED_DIAGNOSTIC_MAX_LEN = 1200
SANITIZED_DIAGNOSTIC_CHARSET = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " .,;:()[]{}<>=+-_/'\"%&*#@!?"
)
_FORBIDDEN_IN_DIAGNOSTIC = ("\n", "\r", "\t", "\\", "://")


def _normalize_json_path(path, well_keys):
    for w in sorted(well_keys, key=len, reverse=True):
        path = path.replace("/" + w + "/", "/*/")
        if path.endswith("/" + w):
            path = path[: -len(w)] + "*"
    out, i = [], 0
    while i < len(path):
        if path[i] == "[":
            j = path.index("]", i)
            out.append("[]")
            i = j + 1
        else:
            out.append(path[i])
            i += 1
    return "".join(out)


class FieldOccurrence:
    """One string value at one place in one emitted record."""

    __slots__ = ("artifact", "field", "value", "location")

    def __init__(self, artifact, field, value, location):
        self.artifact = artifact
        self.field = field
        self.value = value
        self.location = location

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"FieldOccurrence({self.artifact!r}, {self.field!r}, {self.location!r})"


def _schema_violation(artifact, field, location, reason):
    return {
        "artifact": artifact, "field": field, "location": location,
        "reason": "SCHEMA: " + reason, "linter_terms": [],
    }


def _csv_stage(payload, schema, requested):
    if requested in ("pre", "post"):
        return requested
    for row in payload if isinstance(payload, list) else ():
        if not isinstance(row, dict):
            continue
        for field in schema.integer_fields | schema.number_fields | schema.boolean_fields:
            if field in row and row[field] is not None and not isinstance(row[field], str):
                return "pre"
    return "post"


def _valid_decimal_string(value):
    import decimal
    if not isinstance(value, str) or not value:
        return False
    try:
        return decimal.Decimal(value).is_finite()
    except decimal.InvalidOperation:
        return False


def _validate_csv_schema(artifact, payload, serialization_stage="auto"):
    """Validate keys, order, requiredness and types without inspecting prose."""
    schema = CSV_SCHEMAS[artifact]
    out = []
    if not isinstance(payload, list):
        return [_schema_violation(
            artifact, None, None, "CSV payload must be a list of row dictionaries")]
    if len(payload) < schema.min_rows:
        out.append(_schema_violation(
            artifact, None, None,
            f"CSV requires at least {schema.min_rows} row(s), found {len(payload)}"))
    stage = _csv_stage(payload, schema, serialization_stage)
    for i, row in enumerate(payload):
        location = f"row[{i}]"
        if not isinstance(row, dict):
            out.append(_schema_violation(
                artifact, None, location, "CSV row must be a dictionary"))
            continue
        actual = tuple(row.keys())
        if actual != schema.columns:
            missing = [c for c in schema.columns if c not in row]
            unknown = [c for c in actual if c not in schema.columns]
            out.append(_schema_violation(
                artifact, None, location,
                f"ordered columns differ; missing={missing}, unknown={unknown}, "
                f"expected={list(schema.columns)}, actual={list(actual)}"))
        for field in schema.columns:
            if field not in row:
                continue
            value = row[field]
            nullable = field in schema.nullable_fields
            kind = schema.kind(field)
            if kind != "string" and (
                    (stage == "pre" and value is None)
                    or (stage == "post" and value == "")):
                if nullable:
                    continue
                out.append(_schema_violation(
                    artifact, field, f"{location}.{field}",
                    "required value is null/empty after serialization"))
                continue
            valid = False
            if kind == "string":
                valid = isinstance(value, str)
            elif kind == "integer":
                valid = ((type(value) is int) if stage == "pre"
                         else isinstance(value, str) and _is_integer_literal(value))
            elif kind == "number":
                if stage == "pre":
                    import math
                    valid = (type(value) in (int, float) and math.isfinite(value))
                else:
                    valid = _valid_decimal_string(value)
            elif kind == "boolean":
                valid = ((type(value) is bool) if stage == "pre"
                         else value in ("True", "False"))
            if not valid:
                out.append(_schema_violation(
                    artifact, field, f"{location}.{field}",
                    f"expected {kind} at {stage}-serialization stage, got "
                    f"{type(value).__name__} {value!r}"))
    return out


def _expected_json_primitive_kind(path):
    if path in JSON_BOOLEAN_PATHS:
        return "boolean"
    if path in JSON_INTEGER_PATHS:
        return "integer"
    if path in JSON_NUMBER_PATHS:
        return "number"
    if (MANIFEST_ARTIFACT, path) in OUTPUT_FIELD_POLICY:
        return "string"
    return None


def _validate_json_schema(artifact, payload, well_keys=()):
    """Validate the complete manifest tree, including empty/non-string leaves."""
    out = []
    supplied_wells = frozenset(well_keys)
    unknown_wells = supplied_wells - APPROVED_WELL_KEYS
    if unknown_wells:
        out.append(_schema_violation(
            artifact, "/wells", "/wells",
            f"well_keys contains unapproved identifier(s): {sorted(unknown_wells)}"))

    def walk(node, path):
        norm = _normalize_json_path(path, well_keys)
        if isinstance(node, dict):
            expected = JSON_OBJECT_KEYS.get(norm, "__missing__")
            if expected == "__missing__":
                out.append(_schema_violation(
                    artifact, norm, path, "object path is not declared"))
                return
            if expected is None:
                expected = supplied_wells
            actual = frozenset(node)
            if actual != expected:
                out.append(_schema_violation(
                    artifact, norm, path,
                    f"object keys differ; missing={sorted(expected - actual)}, "
                    f"unknown={sorted(actual - expected)}"))
            for key in sorted(actual & expected):
                walk(node[key], f"{path}/{key}")
            return
        if isinstance(node, list):
            expected_kind = JSON_LIST_ITEM_KINDS.get(norm)
            if expected_kind is None:
                out.append(_schema_violation(
                    artifact, norm, path, "list path is not declared"))
                return
            for i, value in enumerate(node):
                if expected_kind == "object" and not isinstance(value, dict):
                    out.append(_schema_violation(
                        artifact, norm, f"{path}[{i}]", "list item must be an object"))
                elif expected_kind == "string" and not isinstance(value, str):
                    out.append(_schema_violation(
                        artifact, norm, f"{path}[{i}]", "list item must be a string"))
                elif expected_kind == "number" and not (
                        type(value) in (int, float) and __import__("math").isfinite(value)):
                    out.append(_schema_violation(
                        artifact, norm, f"{path}[{i}]", "list item must be a finite number"))
                else:
                    walk(value, f"{path}[{i}]")
            return
        kind = _expected_json_primitive_kind(norm)
        if kind is None:
            out.append(_schema_violation(
                artifact, norm, path, "primitive path is not declared"))
            return
        if node is None:
            if norm not in JSON_NULLABLE_PATHS:
                out.append(_schema_violation(
                    artifact, norm, path, "required value is null"))
            return
        if kind == "string":
            valid = isinstance(node, str)
        elif kind == "boolean":
            valid = type(node) is bool
        elif kind == "integer":
            valid = type(node) is int
        else:
            import math
            valid = type(node) in (int, float) and math.isfinite(node)
        if not valid:
            out.append(_schema_violation(
                artifact, norm, path,
                f"expected {kind}, got {type(node).__name__} {node!r}"))

    if not isinstance(payload, dict):
        return [_schema_violation(
            artifact, None, None, "JSON manifest payload must be an object")]
    walk(payload, "")
    return out


def validate_artifact_schema(artifact, payload, well_keys=(), serialization_stage="auto"):
    if artifact in CSV_SCHEMAS:
        return _validate_csv_schema(artifact, payload, serialization_stage)
    if artifact == MANIFEST_ARTIFACT:
        return _validate_json_schema(artifact, payload, well_keys)
    return [_schema_violation(
        artifact, None, None, "artifact has no declared schema")]


def collect_string_fields(artifact, payload, well_keys=()):
    """Collect every schema-declared string occurrence, including ``""``.

    Field discovery is schema-driven. Numeric-looking text in a declared prose
    field is therefore still prose and must authorize; unknown or missing keys
    are handled independently by :func:`validate_artifact_schema`.
    """
    out = []
    if artifact in CSV_SCHEMAS and isinstance(payload, list):
        schema = CSV_SCHEMAS[artifact]
        for i, row in enumerate(payload):
            if not isinstance(row, dict):
                continue
            for column in schema.columns:
                value = row.get(column)
                if column in schema.string_fields and isinstance(value, str):
                    out.append(FieldOccurrence(
                        artifact, column, value, f"row[{i}].{column}"))
        return out
    if artifact == MANIFEST_ARTIFACT and isinstance(payload, dict):
        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}/{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")
            elif isinstance(node, str):
                norm = _normalize_json_path(path, well_keys)
                if _expected_json_primitive_kind(norm) == "string":
                    out.append(FieldOccurrence(artifact, norm, node, path))
        walk(payload, "")
    return out


# ---------------------------------------------------------------------------
# Authorization of one occurrence
# ---------------------------------------------------------------------------

def _is_number_with_optional_unit(token):
    """A decimal literal with an optional trailing alphabetic unit ("2.589m").
    Still a TYPE test: it admits a number and a unit, and no sentence."""
    if not isinstance(token, str) or not token:
        return False
    i = len(token)
    while i > 0 and token[i - 1].isalpha():
        i -= 1
    return OUTPUT_FIELD_TYPES["decimal"](token[:i]) and token[i:].isalpha() or (
        i == len(token) and OUTPUT_FIELD_TYPES["decimal"](token))


def _authorize_structured(value):
    """Grammar for machine-generated diagnostics. Admits `name=integer`,
    `name(number<number)` and `CODE:token` items joined by `;`. It admits no
    sentence: a space anywhere outside a bracket is a rejection."""
    for item in value.split(";"):
        item = item.strip()
        if not item:
            return False
        if "=" in item:
            name, _, num = item.partition("=")
            if not (name.replace("_", "").isalnum() and _is_integer_literal(num)):
                return False
        elif item.endswith(")") and "(" in item:
            name, _, rest = item.partition("(")
            lo, sep, hi = rest[:-1].partition("<")
            if not (name.replace("_", "").isalnum() and sep
                    and _is_number_with_optional_unit(lo)
                    and _is_number_with_optional_unit(hi)):
                return False
        elif ":" in item:
            code, _, token = item.partition(":")
            if not (code.replace("_", "").isalnum() and code.isupper()
                    and token.replace("_", "").replace(".", "").replace("-", "").isalnum()):
                return False
        else:
            return False
    return True


def _authorize_sanitized(value):
    if len(value) > SANITIZED_DIAGNOSTIC_MAX_LEN:
        return False, "exceeds the declared diagnostic length bound"
    if any(bad in value for bad in _FORBIDDEN_IN_DIAGNOSTIC):
        return False, "contains a forbidden control or path-like sequence"
    if not set(value) <= SANITIZED_DIAGNOSTIC_CHARSET:
        offending = sorted(set(value) - SANITIZED_DIAGNOSTIC_CHARSET)
        return False, f"contains characters outside the declared charset: {offending}"
    return True, None


def _parse_template(template, text):
    """Parse `text` back against `template`, returning the substitutions or None.
    The literal parts must match character for character."""
    names, literals, buf, rest = [], [], "", template
    while "{" in rest:
        head, _, rest = rest.partition("{")
        name, _, rest = rest.partition("}")
        literals.append(buf + head)
        names.append(name)
        buf = ""
    literals.append(buf + rest)
    if not text.startswith(literals[0]):
        return None
    remainder, values = text[len(literals[0]):], {}
    for name, nxt in zip(names, literals[1:]):
        if nxt:
            value, sep, remainder = remainder.partition(nxt)
            if not sep:
                return None
        else:
            value, remainder = remainder, ""
        values[name] = value
    return None if remainder else values


def authorize_occurrence(occ):
    """Authorize ONE emitted occurrence.

    Returns `(ok, authorization, reason)`. `authorization` is the credential
    that travels with the value: a statement id, a template id plus its typed
    substitutions, an `(field_kind, value)` label, or a category marker. It is
    retained by the caller until serialization so the emitted bytes can be
    re-checked against what was authorized.
    """
    policy = OUTPUT_FIELD_POLICY.get((occ.artifact, occ.field))
    if policy is None:
        return False, None, (
            f"UNCLASSIFIED output field {occ.artifact}:{occ.field!r}. Every emitted "
            f"string column and JSON path must carry a declared policy classification; "
            f"an unknown artifact, column or JSON path fails closed.")
    if occ.value == "":
        if policy.allow_empty:
            return True, ("declared_empty", policy.category), None
        return False, None, (
            f"empty string is not allowed for required field "
            f"{occ.artifact}:{occ.field!r}")
    cat = policy.category
    if cat in ("structural_enum", "identifier"):
        if occ.value not in policy.allowed_values:
            return False, None, (
                f"value is not in the enumerated {cat} vocabulary declared for "
                f"{occ.artifact}:{occ.field!r}")
        return True, (cat, occ.value), None
    if cat == "filename":
        if ("/" in occ.value or "\\" in occ.value or occ.value.startswith(".")
                or not occ.value.strip()):
            return False, None, "filename must be a bare basename with no path separator"
        return True, ("filename", occ.value), None
    if cat == "typed_label":
        lab = approved_label(policy.field_kind, occ.value)
        if lab is None:
            other = sorted(k for k in APPROVED_LABELS if occ.value in APPROVED_LABELS[k])
            extra = f" (it is approved only as {other})" if other else ""
            return False, None, (
                f"value is not approved for field_kind {policy.field_kind!r}{extra}")
        return True, ("typed_label", policy.field_kind, occ.value), None
    if cat == "registered_statement":
        for sid in policy.statement_ids:
            st = OUTPUT_STATEMENTS.get(sid)
            if st is not None and st.text == occ.value:
                return True, ("statement", sid), None
        return False, None, (
            f"text does not exactly match any statement registered for "
            f"{occ.artifact}:{occ.field!r} ({list(policy.statement_ids)}). Registered "
            f"prose is authorized by id and exact text; near-misses are rejected.")
    if cat == "controlled_template":
        if occ.value in policy.allowed_values:
            return True, ("template_sentinel", occ.value), None
        for sid in policy.statement_ids:
            st = OUTPUT_STATEMENTS.get(sid)
            if st is not None and st.text == occ.value:
                return True, ("statement", sid), None
        tpl = OUTPUT_TEMPLATES.get(policy.template_id)
        if tpl is None:
            return False, None, f"unknown template_id {policy.template_id!r}"
        values = _parse_template(tpl.template, occ.value)
        if values is None:
            return False, None, (
                f"text does not match template {tpl.template_id!r}; the fixed prose must "
                f"match character for character")
        if set(values) != set(tpl.fields):
            return False, None, f"template {tpl.template_id!r} substitution set mismatch"
        bad = sorted(n for n, v in values.items()
                     if not OUTPUT_FIELD_TYPES[tpl.fields[n]](v))
        if bad:
            return False, None, (
                f"template {tpl.template_id!r} substitution(s) {bad} do not satisfy their "
                f"declared type, so the template cannot carry prose")
        return True, ("template", tpl.template_id, values), None
    if cat == "structured_diagnostic":
        if occ.value in policy.allowed_values:
            # An enumerated sentinel token declared for this field.
            return True, ("structured_sentinel", occ.value), None
        if not _authorize_structured(occ.value):
            return False, None, (
                "value does not satisfy the declared machine-diagnostic grammar "
                "(name=integer / name(number<number) / CODE:token, joined by ';')")
        return True, ("structured_diagnostic", None), None
    if cat == "sanitized_diagnostic":
        ok, why = _authorize_sanitized(occ.value)
        return (True, ("sanitized_diagnostic", None), None) if ok else (False, None, why)
    return False, None, f"unhandled category {cat!r}"  # pragma: no cover


class CoverageReport:
    """What was actually inspected, and what it was."""

    __slots__ = ("n_string_field_occurrences", "n_controlled_occurrences",
                 "n_structural_occurrences", "n_unguaranteed_occurrences",
                 "n_unclassified_fields", "n_unauthorized_controlled_fields",
                 "n_field_kind_mismatches", "n_schema_violations",
                 "violations", "authorizations",
                 "artifacts_inspected", "distinct_statements_used",
                 "distinct_templates_used", "distinct_labels_used")

    def __init__(self, **kw):
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    def as_dict(self):
        out = {s: getattr(self, s) for s in self.__slots__ if s != "authorizations"}
        # This dictionary is embedded directly in the JSON manifest before the
        # pre-serialization schema pass. Keep it JSON-native at construction;
        # do not rely on json.dumps silently converting tuples later.
        out["violations"] = [dict(v) for v in self.violations]
        out["artifacts_inspected"] = list(self.artifacts_inspected)
        return out

    @property
    def ok(self):
        return (self.n_unclassified_fields == 0
                and self.n_unauthorized_controlled_fields == 0
                and self.n_field_kind_mismatches == 0
                and self.n_schema_violations == 0
                and not self.violations)


def validate_emitted_records(payloads, well_keys=(), expected_artifacts=None,
                             serialization_stage="auto"):
    """Validate schema, then authorize every declared string occurrence.

    `payloads` maps artifact filename -> pre-serialization payload. Every
    declared artifact must be present; exact keys/order, requiredness and types
    are checked independently of values. Only after that closed schema pass are
    string values authorized. ``serialization_stage`` is ``pre``, ``post`` or
    ``auto`` (the compatibility default for callers loading packaged CSVs).
    """
    violations, authorizations = [], []
    counts = dict(controlled=0, structural=0, unguaranteed=0,
                  unclassified=0, unauthorized=0, kind_mismatch=0, schema=0)
    stmts, tpls, labels = set(), set(), set()
    # `expected_artifacts` narrows the completeness requirement. The manifest
    # builder uses it because it cannot present the manifest it is still
    # building; the export gate always requires the full declared set.
    declared = set(OUTPUT_ARTIFACTS if expected_artifacts is None else expected_artifacts)
    unknown_artifacts = sorted(set(payloads) - declared)
    missing_artifacts = sorted(declared - set(payloads))
    for name in unknown_artifacts:
        violations.append(_schema_violation(
            name, None, None, "artifact has no declared output schema"))
        counts["unclassified"] += 1
        counts["schema"] += 1
    for name in missing_artifacts:
        violations.append(_schema_violation(
            name, None, None, "declared artifact was not presented for validation"))
        counts["unclassified"] += 1
        counts["schema"] += 1
    total = 0
    for artifact in sorted(set(payloads) & declared):
        schema_bad = validate_artifact_schema(
            artifact, payloads[artifact], well_keys,
            serialization_stage=serialization_stage)
        violations.extend(schema_bad)
        counts["schema"] += len(schema_bad)
        for occ in collect_string_fields(artifact, payloads[artifact], well_keys):
            total += 1
            ok, auth, reason = authorize_occurrence(occ)
            policy = OUTPUT_FIELD_POLICY.get((artifact, occ.field))
            cat = policy.category if policy is not None else None
            if cat in CONTROLLED_CATEGORIES:
                counts["controlled"] += 1
            elif cat in STRUCTURAL_CATEGORIES:
                counts["structural"] += 1
            elif cat in UNGUARANTEED_CATEGORIES:
                counts["unguaranteed"] += 1
            if ok:
                authorizations.append((occ, auth))
                if auth[0] == "statement":
                    stmts.add(auth[1])
                elif auth[0] == "template":
                    tpls.add(auth[1])
                elif auth[0] == "typed_label":
                    labels.add((auth[1], auth[2]))
                continue
            if policy is None:
                counts["unclassified"] += 1
            elif cat == "typed_label":
                counts["kind_mismatch"] += 1
                counts["unauthorized"] += 1
            elif cat in CONTROLLED_CATEGORIES:
                counts["unauthorized"] += 1
            violations.append({
                "artifact": artifact, "field": occ.field, "location": occ.location,
                "reason": reason,
                "linter_terms": sorted(set(find_prohibited_lithology_terms(occ.value))),
            })
    return CoverageReport(
        n_string_field_occurrences=total,
        n_controlled_occurrences=counts["controlled"],
        n_structural_occurrences=counts["structural"],
        n_unguaranteed_occurrences=counts["unguaranteed"],
        n_unclassified_fields=counts["unclassified"],
        n_unauthorized_controlled_fields=counts["unauthorized"],
        n_field_kind_mismatches=counts["kind_mismatch"],
        n_schema_violations=counts["schema"],
        violations=tuple(violations), authorizations=tuple(authorizations),
        artifacts_inspected=tuple(sorted(set(payloads) & declared)),
        distinct_statements_used=len(stmts), distinct_templates_used=len(tpls),
        distinct_labels_used=len(labels),
    )


# ---------------------------------------------------------------------------
# The export gate: validate typed records, serialize to an isolated staging
# directory, compare the complete canonical round trip, then publish.
# ---------------------------------------------------------------------------


class OutputAuthorizationError(ValueError):
    """Raised when an artifact would persist an unauthorized controlled field."""


def _canonical_csv_value(value, kind, nullable, stage):
    import decimal
    if (stage == "pre" and value is None) or (stage == "post" and value == ""):
        if nullable:
            return ("null", None)
    if kind == "string":
        return ("string", value)
    if kind == "integer":
        return ("integer", int(value))
    if kind == "number":
        number = decimal.Decimal(str(value)).normalize()
        return ("number", number.as_tuple())
    if kind == "boolean":
        return ("boolean", value if stage == "pre" else value == "True")
    raise AssertionError(kind)  # pragma: no cover


def canonicalize_emitted_records(payloads, serialization_stage="auto"):
    """Return a complete, schema-aware semantic representation.

    The caller must first obtain a clean schema report. CSV values are restored
    to their declared semantic types, so harmless serialization representation
    differences do not mask or manufacture mutations. Row order and every
    declared field value remain part of the comparison.
    """
    import json as _json
    canonical = []
    for artifact in sorted(payloads):
        payload = payloads[artifact]
        if artifact in CSV_SCHEMAS:
            schema = CSV_SCHEMAS[artifact]
            stage = _csv_stage(payload, schema, serialization_stage)
            rows = tuple(
                tuple(_canonical_csv_value(
                    row[field], schema.kind(field), field in schema.nullable_fields, stage)
                    for field in schema.columns)
                for row in payload
            )
            canonical.append((artifact, schema.columns, rows))
        else:
            canonical.append((artifact, _json.dumps(
                payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                separators=(",", ":"))))
    return tuple(canonical)


def export_authorized_outputs(out_dir, payloads, well_keys=(), writer=None):
    """Schema-driven, transactional two-stage export.

    STAGE 1 validates exact artifact/field schemas, requiredness, types and
    content authorization. STAGE 2 writes only to a temporary sibling,
    validates the bytes read back, and compares every canonical record/value.
    The official destination is touched only after both stages pass.

    Returns `(report_before, report_after)`. Raises `OutputAuthorizationError`
    on any validation or serializer failure. A rejected export leaves the
    destination unchanged. Publication uses per-file atomic replacement with
    rollback; this is failure-atomic for handled process errors, not a claim of
    multi-file atomicity across power loss or operating-system failure.
    """
    import csv as _csv
    import json as _json
    import os as _os
    import pathlib as _pathlib
    import shutil as _shutil
    import tempfile as _tempfile

    out_dir = _pathlib.Path(out_dir)
    before = validate_emitted_records(
        payloads, well_keys=well_keys, serialization_stage="pre")
    if not before.ok:
        raise OutputAuthorizationError(
            f"refusing to write: {len(before.violations)} schema/authorization "
            f"output field(s); first: {before.violations[0] if before.violations else None}")
    canonical_before = canonicalize_emitted_records(payloads, serialization_stage="pre")

    allowed_destination_names = set(OUTPUT_ARTIFACTS) | {"figures"}
    if out_dir.exists():
        if not out_dir.is_dir():
            raise OutputAuthorizationError("output destination exists and is not a directory")
        stale = sorted(p.name for p in out_dir.iterdir()
                       if p.name not in allowed_destination_names)
        if stale:
            raise OutputAuthorizationError(
                f"output destination contains undeclared stale artifact(s): {stale}")

    parent = out_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage_dir = _pathlib.Path(_tempfile.mkdtemp(
        prefix=f".{out_dir.name}.stage-", dir=str(parent)))
    try:
        try:
            for name, payload in sorted(payloads.items()):
                target = stage_dir / name
                if writer is not None:
                    writer(target, payload)
                elif name.endswith(".json"):
                    target.write_text(_json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
                else:
                    schema = CSV_SCHEMAS[name]
                    with open(target, "w", encoding="utf-8", newline="") as fh:
                        w = _csv.DictWriter(fh, fieldnames=list(schema.columns))
                        w.writeheader()
                        w.writerows(payload)
        except OutputAuthorizationError:
            raise
        except Exception as exc:
            raise OutputAuthorizationError(
                f"serializer failed before publication: {exc}") from exc

        staged_names = {p.name for p in stage_dir.iterdir()}
        expected_names = set(payloads)
        if (staged_names != expected_names
                or any(p.is_symlink() or not p.is_file() for p in stage_dir.iterdir())):
            raise OutputAuthorizationError(
                f"serializer produced wrong artifact inventory: "
                f"missing={sorted(expected_names - staged_names)}, "
                f"unknown={sorted(staged_names - expected_names)}")

        reread = {}
        for name in payloads:
            target = stage_dir / name
            try:
                if name.endswith(".json"):
                    reread[name] = _json.loads(target.read_text(encoding="utf-8"))
                else:
                    with open(target, newline="", encoding="utf-8") as fh:
                        reread[name] = list(_csv.DictReader(fh))
            except Exception as exc:
                raise OutputAuthorizationError(
                    f"could not re-read staged artifact {name!r}: {exc}") from exc
        after = validate_emitted_records(
            reread, well_keys=well_keys, serialization_stage="post")
        if not after.ok:
            raise OutputAuthorizationError(
                f"post-serialization re-check failed: {len(after.violations)} field(s) "
                f"changed or became unauthorized after authorization; first: "
                f"{after.violations[0] if after.violations else None}")
        canonical_after = canonicalize_emitted_records(
            reread, serialization_stage="post")
        if canonical_after != canonical_before:
            mismatch = next((i for i, pair in enumerate(zip(
                canonical_before, canonical_after)) if pair[0] != pair[1]), None)
            raise OutputAuthorizationError(
                f"post-serialization canonical record mismatch at artifact index {mismatch}; "
                "an authorized value, field, row order or type changed")

        # Publication happens only after the complete staged set has passed.
        out_dir.mkdir(parents=True, exist_ok=True)
        backup_dir = _pathlib.Path(_tempfile.mkdtemp(
            prefix=f".{out_dir.name}.backup-", dir=str(parent)))
        replaced, created = [], []
        try:
            for name in sorted(payloads):
                target = out_dir / name
                if target.exists():
                    _shutil.copy2(target, backup_dir / name)
                    replaced.append(name)
                else:
                    created.append(name)
                _os.replace(stage_dir / name, target)
        except Exception:
            for name in created:
                target = out_dir / name
                if target.exists():
                    target.unlink()
            for name in replaced:
                backup = backup_dir / name
                if backup.exists():
                    _os.replace(backup, out_dir / name)
            raise
        finally:
            _shutil.rmtree(backup_dir, ignore_errors=True)
        return before, after
    finally:
        _shutil.rmtree(stage_dir, ignore_errors=True)
