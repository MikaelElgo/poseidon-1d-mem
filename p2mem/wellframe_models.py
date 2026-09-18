"""
p2mem.wellframe_models - Typed, immutable data structures for the
Increment 6 well-frame layer.

Scope and intent
----------------
A "well frame" is a single, auditable, in-memory assembly of ONE well's
already-validated Increment 2.1.1 canonical LAS curve arrays alongside
the Increment 3.1.1 depth mapping (MD -> TVD / TVDSS) computed from that
well's LOCKED, explicitly selected survey trajectory basis. It is a
*view-and-annotate* layer, not a new ingestion layer:

* it NEVER re-parses a LAS or deviation file;
* it NEVER recomputes minimum curvature or replaces the locked
  `petrel_source_trace` basis;
* it NEVER overwrites, resamples, reorders, interpolates, gap-fills, or
  deletes a canonical curve array - every array in a `CurveSlot` is the
  locked loader's own array (or a read-only view of it), in the original
  file order, with the original sample count;
* it NEVER extrapolates MD -> TVD/TVDSS - a LAS sample outside the
  survey's own MD coverage is recorded as depth-unmapped (masked), never
  clamped, held, or linearly extended (see `p2mem.wellframe`).

Everything this layer adds is *additive metadata*: per-sample validity
masks, per-curve provenance (which physical source curve, from which
file, under which unit conversion), depth-mapping basis and coverage,
QC flags, and an evidence classification. This separation exists so that
a later increment can never confuse "the measured log" with "what this
project decided about the measured log".

Naming discipline (Increment 6 scientific boundary)
---------------------------------------------------
Nothing in this module - and nothing any Increment 6 module may write
into a field defined here - assigns a named lithology. `EVIDENCE_CLASSES`
and the QC-flag vocabulary describe *data and provenance confidence
only*. The prohibited-vocabulary guard `PROHIBITED_LITHOLOGY_TERMS` is
defined here (rather than in the petrophysics layer) precisely because
the well frame is the earliest place a rock-name could leak into a
persisted field, and it is enforced by tests over every generated
classification string.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

__all__ = [
    "EVIDENCE_CLASS_MEASURED",
    "EVIDENCE_CLASS_DERIVED_LOCKED",
    "EVIDENCE_CLASS_CORRELATION_DERIVED",
    "EVIDENCE_CLASS_ASSUMED",
    "EVIDENCE_CLASS_UNAVAILABLE",
    "VALID_EVIDENCE_CLASSES",
    "DEPTH_MAP_STATUS_FULL",
    "DEPTH_MAP_STATUS_PARTIAL",
    "DEPTH_MAP_STATUS_NONE",
    "VALID_DEPTH_MAP_STATUSES",
    "VALID_WELLFRAME_FAILURE_ORIGINS",
    "PROHIBITED_LITHOLOGY_TERMS",
    "CurveSlot",
    "WellFrame",
    "WellFrameAssemblyFailure",
    "assert_no_lithology_vocabulary",
    "SCOPE_LABEL",
    "SCOPE_INTERPRETIVE",
    "SCOPE_EXPLANATORY",
    "VALID_VALIDATION_SCOPES",
    "SCOPE_METHOD",
    "CONTROLLED_SCOPES",
    "ApprovedLabel",
    "APPROVED_LABELS",
    "APPROVED_LABEL_FIELD_KINDS",
    "approved_label",
    "RegisteredStatement",
    "REGISTERED_STATEMENTS",
    "RegisteredTemplate",
    "REGISTERED_TEMPLATES",
    "FIELD_TYPES",
    "Authorization",
    "find_prohibited_lithology_terms",
    "validate_no_prohibited_interpretation",
]

# ---------------------------------------------------------------------------
# Evidence classification vocabulary
# ---------------------------------------------------------------------------
# Deliberately describes the PROVENANCE of a quantity, never a geological
# interpretation of it. "measured" means a physically logged quantity that
# survived the locked per-file LAS contract; "derived_locked" means a
# quantity computed by an already-reviewed, LOCKED prior increment (the
# MD->TVD/TVDSS mapping); "correlation_derived" is reserved for a future
# increment's empirical transforms and is NOT produced anywhere in
# Increment 6; "assumed" marks an explicitly configured, human-authored
# value that no measurement supports; "unavailable" marks a factual data
# gap that must never be silently substituted.
EVIDENCE_CLASS_MEASURED = "measured"
EVIDENCE_CLASS_DERIVED_LOCKED = "derived_locked_prior_increment"
EVIDENCE_CLASS_CORRELATION_DERIVED = "correlation_derived"
EVIDENCE_CLASS_ASSUMED = "assumed_configured"
EVIDENCE_CLASS_UNAVAILABLE = "unavailable"

VALID_EVIDENCE_CLASSES: Tuple[str, ...] = (
    EVIDENCE_CLASS_MEASURED,
    EVIDENCE_CLASS_DERIVED_LOCKED,
    EVIDENCE_CLASS_CORRELATION_DERIVED,
    EVIDENCE_CLASS_ASSUMED,
    EVIDENCE_CLASS_UNAVAILABLE,
)

# ---------------------------------------------------------------------------
# Depth-mapping status vocabulary
# ---------------------------------------------------------------------------
# "full"    - every LAS sample lies inside the survey's own MD coverage and
#             received a TVD/TVDSS value from the locked mapper.
# "partial" - some samples lie outside survey MD coverage; those samples are
#             recorded as depth-unmapped (NaN + False in `depth_valid_mask`).
#             They are NEVER extrapolated, clamped, or held constant.
# "none"    - no sample could be mapped (e.g. no overlap at all).
DEPTH_MAP_STATUS_FULL = "fully_mapped_within_survey_coverage"
DEPTH_MAP_STATUS_PARTIAL = "partially_mapped_coverage_limited"
DEPTH_MAP_STATUS_NONE = "not_mapped_no_survey_coverage_overlap"

VALID_DEPTH_MAP_STATUSES: Tuple[str, ...] = (
    DEPTH_MAP_STATUS_FULL,
    DEPTH_MAP_STATUS_PARTIAL,
    DEPTH_MAP_STATUS_NONE,
)

# Which stage of assembly produced a failure. Mirrors the Increment 5.1
# `TopIngestionFailure.failure_origin` precedent so a caller can branch on
# the kind of failure without parsing message text.
VALID_WELLFRAME_FAILURE_ORIGINS: Tuple[str, ...] = (
    "las",
    "survey",
    "depth_mapping",
    "curve_assembly",
    "unknown",
)

# ---------------------------------------------------------------------------
# Prohibited named-lithology vocabulary (Increment 6 hard scientific bound)
# ---------------------------------------------------------------------------
# Increment 6 must not convert a gamma-ray response into a rock name. This
# tuple is the machine-checkable expression of that boundary: every
# classification string this increment generates is asserted against it by
# `assert_no_lithology_vocabulary` and by the test suite. It deliberately
# contains only ROCK/LITHOLOGY names - not words like "proxy", "screening",
# or "shale_proxy_*" field names, which are permitted precisely because they
# are self-labelling as non-lithological. The bare term "shale" IS listed:
# a class named "shale" would assert a rock type, whereas a FIELD named
# `VSH_GR_linear_proxy_frac` is a dimensionless proxy quantity and is
# checked separately (see `p2mem.petrophysics`).
PROHIBITED_LITHOLOGY_TERMS: Tuple[str, ...] = (
    "shale",
    "sand",
    "sandstone",
    "carbonate",
    "limestone",
    "dolomite",
    "marl",
    "claystone",
    "siltstone",
    "mudstone",
    "coal",
    "salt",
    "anhydrite",
    "evaporite",
    "reservoir_rock",
    "non_reservoir_rock",
    "reservoir rock",
    "non-reservoir rock",
    "pay",
    "net_pay",
    # Increment 6.1 (Finding 3): depositional-system and rock-class terms are
    # prohibited for the same reason rock names are. Calling a section
    # "clastic-dominated" is a lithological assertion about these wells, and a
    # trailing disclaimer does not undo it - the claim is in the noun, not in
    # the caveat. Gamma-ray response cannot establish a depositional system any
    # more than it can establish a rock name.
    "clastic",
    "clastics",
    "siliciclastic",
    "carbonates",
    "volcanic",
    "igneous",
    "metamorphic",
    "basement",
)


def assert_no_lithology_vocabulary(value: str, context: str) -> None:
    """
    Raise `ValueError` if `value` contains any prohibited named-lithology
    term as a standalone word.

    Matching is performed on a lowercased, non-alphanumeric-normalized
    token view of `value`, so `"GR_PROXY_HIGH"` passes while
    `"SHALE_HIGH"`, `"probable-sandstone"` and `"net pay"` are rejected.
    Substring matching alone is deliberately NOT used: it would reject the
    legitimate, explicitly self-labelling field name
    `VSH_GR_linear_proxy_frac` (which contains "sh"), and would reject
    "sand" inside "thousand". Multi-word prohibited terms are checked
    against the normalized whole string.

    This guard exists so a rock name can never reach a persisted
    classification field by accident. It is intentionally strict and is
    exercised directly by the Increment 6 test suite.
    """
    if not isinstance(value, str):
        raise TypeError(f"{context}: classification value must be a string, got {type(value).__name__!r}.")
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    tokens = set(normalized.split())
    for term in PROHIBITED_LITHOLOGY_TERMS:
        term_norm = "".join(ch.lower() if ch.isalnum() else " " for ch in term).strip()
        parts = term_norm.split()
        if len(parts) == 1:
            if parts[0] in tokens:
                raise ValueError(
                    f"{context}: value {value!r} contains prohibited named-lithology term "
                    f"{term!r}. Increment 6 classifies DATA/PROXY CONFIDENCE only and must "
                    f"never assign a named lithology."
                )
        else:
            if f" {term_norm} " in f" {' '.join(normalized.split())} ":
                raise ValueError(
                    f"{context}: value {value!r} contains prohibited named-lithology term "
                    f"{term!r}. Increment 6 classifies DATA/PROXY CONFIDENCE only and must "
                    f"never assign a named lithology."
                )


@dataclass(frozen=True)
class CurveSlot:
    """
    One canonical curve inside a well frame, with its full provenance and
    a per-sample validity mask.

    `values` is the LOCKED Increment 2.1.1 loader's own canonical array
    for this curve (NULL-sentinel already substituted to NaN, and the
    contract's exact unit conversion already applied by that locked
    loader). This layer does not copy-and-modify it: an invalid sample is
    expressed in `valid_mask`, never by deleting, replacing, or
    interpolating the value itself. `values.size` therefore always equals
    the well frame's `n_samples`, in the original file order.

    `source_curve_name` / `raw_mnemonic` / `raw_unit` preserve the
    physical identity of the column as it appeared in THIS file. Two wells
    whose contracts happen to produce the same `canonical_name` (for
    example Poseidon 2's `GR` and Proteus 1ST2's `GR`, both canonicalized
    to `GR_api`) are still distinct measurements from distinct tools in
    distinct wells; nothing in this project may treat them as
    interchangeable on the strength of a shared canonical name alone.

    `valid_mask` is True exactly where `values` is finite. It is a
    read-only boolean array (`writeable=False`) so that a downstream
    consumer cannot mutate one well frame's mask and silently affect
    another consumer holding the same object.
    """

    canonical_name: str
    source_curve_name: str
    raw_mnemonic: str
    raw_unit: str
    canonical_unit: str
    conversion_function: str
    source_filename: str
    evidence_class: str
    values: np.ndarray
    valid_mask: np.ndarray
    n_samples: int
    valid_count: int
    valid_fraction: float

    def __post_init__(self) -> None:
        if self.evidence_class not in VALID_EVIDENCE_CLASSES:
            raise ValueError(
                f"CurveSlot {self.canonical_name!r}: evidence_class {self.evidence_class!r} is not "
                f"one of {VALID_EVIDENCE_CLASSES}."
            )


@dataclass(frozen=True)
class WellFrame:
    """
    One well's complete, auditable Increment 6 assembly.

    Depth arrays
    ------------
    `MD_m` is the LOCKED loader's own canonical LAS MD array, unmodified.
    `TVD_m` / `TVDSS_m` are full-length arrays aligned sample-for-sample
    with `MD_m`; where a sample lies outside the survey's own MD coverage
    both are NaN and `depth_valid_mask` is False. `n_depth_unmapped`
    counts exactly those samples. `n_extrapolated` is always 0 by
    construction and is reported as a confirming, self-describing field
    (this layer has no code path that extrapolates).

    Formation tops
    --------------
    A well frame carries NO formation-top data. Increment 6 consumes tops
    only through the LOCKED Increment 5 survey-corrected output tables,
    and only for display/annotation - never by re-parsing, transferring
    between wells, or re-deriving them.
    """

    well_key: str
    source_las_filename: str
    source_survey_filename: str
    n_samples: int

    MD_m: np.ndarray
    TVD_m: np.ndarray
    TVDSS_m: np.ndarray
    depth_valid_mask: np.ndarray

    depth_basis_used: str
    interpolation_method: str
    datum_elevation_m: float
    depth_map_status: str
    survey_md_min_m: float
    survey_md_max_m: float
    las_md_min_m: float
    las_md_max_m: float
    n_depth_unmapped: int
    n_extrapolated: int

    curves: Dict[str, CurveSlot] = field(default_factory=dict)
    gr_family_canonical_name: Optional[str] = None
    gr_family_source_curve_name: Optional[str] = None
    well_identity_evidence_status: str = "inferred_unverified"
    qc_flags: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.depth_map_status not in VALID_DEPTH_MAP_STATUSES:
            raise ValueError(
                f"WellFrame {self.well_key!r}: depth_map_status {self.depth_map_status!r} is not "
                f"one of {VALID_DEPTH_MAP_STATUSES}."
            )

    def curve(self, canonical_name: str) -> Optional[CurveSlot]:
        """Return the named `CurveSlot`, or None if this well has no such
        contract-resolved curve. Never raises for a missing curve: a curve
        a well genuinely does not have is a factual data gap, not an
        error, and callers must be able to branch on it."""
        return self.curves.get(canonical_name)

    def values_or_none(self, canonical_name: str) -> Optional[np.ndarray]:
        """Return the canonical array for `canonical_name`, or None."""
        slot = self.curves.get(canonical_name)
        return None if slot is None else slot.values


@dataclass(frozen=True)
class WellFrameAssemblyFailure:
    """
    A typed record of one well's failed frame assembly, isolated so that
    one well's failure never stops the others (mirrors the LOCKED
    `IngestionFailure` / `DeviationIngestionFailure` / `TopIngestionFailure`
    precedents).

    `failure_origin` names the stage that actually failed, and BOTH
    candidate source paths are always retained, so an exporter can
    sanitize whichever path a message happens to contain rather than
    assuming a single one (the Increment 5.1 Finding-2 lesson, applied
    here from the start rather than retrofitted).
    """

    well_key: str
    failure_origin: str
    error_type: str
    message: str
    las_path: Optional[str] = None
    survey_path: Optional[str] = None
    exception: Optional[BaseException] = None

    def __post_init__(self) -> None:
        if self.failure_origin not in VALID_WELLFRAME_FAILURE_ORIGINS:
            raise ValueError(
                f"WellFrameAssemblyFailure {self.well_key!r}: failure_origin "
                f"{self.failure_origin!r} is not one of {VALID_WELLFRAME_FAILURE_ORIGINS}."
            )


# ---------------------------------------------------------------------------
# Increment 6.1.5: POSITIVE AUTHORIZATION for every persisted controlled field
# ---------------------------------------------------------------------------
# History, stated plainly because it is the justification for this design.
#
# Increments 6.1 through 6.1.4 all asked the same question in different ways:
# "does this text contain a geological assertion?" 6.1.1 answered it with
# sentence-wide cue lists, 6.1.2 with per-occurrence grammar, 6.1.3 with a
# prohibited-term scan, 6.1.4 with a prohibited-term scan plus a registry for
# explanatory text. Every one of them was defeated, because all of them shared
# a single structural assumption: that content is ACCEPTABLE BY DEFAULT and
# becomes unacceptable only when a recognizer fires.
#
# That assumption fails against a word the recognizer has never seen. In the
# Increment 6.1.4 package, all of the following passed label, interpretive and
# explanatory scope, because none of these words was in the blacklist:
#
#     "The interval is chalk."          "The interval is chert."
#     "The interval is halite."         "The interval is tuff."
#     "The interval is gypsum."         "The interval is basalt."
#     "The interval is conglomerate."   "The interval is dolostone."
#     "The interval is lignite."        "The interval is calcareous."
#
# and so did "The interval is qxzite." - a word that does not exist. A longer
# blacklist would have caught the first ten and still missed the eleventh, so
# lengthening it is not a completion criterion and is not the mechanism this
# module's assurance claim rests on.
#
# THE MODEL IS INVERTED. Nothing is acceptable by default. Every persisted
# controlled field must be POSITIVELY AUTHORIZED:
#
#   SCOPE_LABEL        the value must be a member of APPROVED_LABELS - a
#                      registry of typed, enumerated label values. Arbitrary
#                      caller text is rejected even when it contains no
#                      recognizable rock name at all.
#   SCOPE_INTERPRETIVE the text must resolve to a registered statement_id, or
#                      to a reviewed template_id whose substitutions are
#                      strictly typed. Unregistered free text is rejected
#                      unconditionally.
#   SCOPE_METHOD       the text must resolve to a registered statement_id, and
#                      BOTH the id and the exact rendered text are validated.
#   SCOPE_EXPLANATORY  the same, for every non-empty statement, whether or not
#                      any prohibited term is detected.
#
# There is NO path through this module that accepts arbitrary text because a
# recognizer failed to fire. `PROHIBITED_LITHOLOGY_TERMS` survives ONLY as a
# supplementary diagnostic linter: it annotates violations with any rock words
# it happens to recognize, it never authorizes anything, and it must never be
# cited as evidence that all named lithologies have been detected.
#
# WHAT THIS DOES AND DOES NOT CLAIM
#
#   It DOES claim: every persisted project-specific classification and
#   interpretive statement is generated from an approved typed value, a
#   controlled template, or a registered statement. Arbitrary free text cannot
#   enter these controlled fields.
#
#   It does NOT claim: that this software understands, recognizes, or
#   exhaustively enumerates natural-language lithology. It cannot, and no
#   version of it ever did. Free-form notebook narrative and documentation are
#   OUTSIDE these controlled fields and remain subject to ordinary manual
#   scientific review.

SCOPE_LABEL = "label"
SCOPE_INTERPRETIVE = "interpretive"
SCOPE_METHOD = "method"
SCOPE_EXPLANATORY = "explanatory"
VALID_VALIDATION_SCOPES: Tuple[str, ...] = (
    SCOPE_LABEL, SCOPE_INTERPRETIVE, SCOPE_METHOD, SCOPE_EXPLANATORY,
)

#: Scopes in which nothing is accepted without positive authorization.
CONTROLLED_SCOPES: Tuple[str, ...] = VALID_VALIDATION_SCOPES


class ApprovedLabel:
    """One authorized label value, with the field it belongs to and why it exists.

    A label is a verdict a well is stamped with. It is not prose, so it is
    enumerated rather than described: a value either is in this registry or it
    is not persisted.
    """

    __slots__ = ("value", "field_kind", "purpose", "provenance")

    def __init__(self, value, field_kind, purpose, provenance):
        self.value = value
        self.field_kind = field_kind
        self.purpose = purpose
        self.provenance = provenance

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"ApprovedLabel({self.value!r}, {self.field_kind!r})"


class RegisteredStatement:
    """One authorized exact statement, bound to a single scope.

    `text` is the canonical persisted decision. Authorization is by
    `statement_id`, and the id and the rendered text are validated together, so
    neither a renamed id nor an edited sentence can pass on the strength of the
    other.
    """

    __slots__ = ("statement_id", "scope", "text", "purpose", "provenance")

    def __init__(self, statement_id, scope, text, purpose, provenance):
        self.statement_id = statement_id
        self.scope = scope
        self.text = text
        self.purpose = purpose
        self.provenance = provenance

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"RegisteredStatement({self.statement_id!r}, {self.scope!r})"


class RegisteredTemplate:
    """One authorized statement template with strictly typed substitutions.

    Templates exist for statements that must carry MEASURED NUMBERS - a
    per-well confidence rationale, for example. The controlled part is the
    prose; the free part is restricted to values that satisfy a declared type,
    so a template can never become a channel for arbitrary text.

    `fields` maps each substitution name to a type name in `FIELD_TYPES`.
    """

    __slots__ = ("template_id", "scope", "template", "fields", "purpose", "provenance")

    def __init__(self, template_id, scope, template, fields, purpose, provenance):
        self.template_id = template_id
        self.scope = scope
        self.template = template
        self.fields = dict(fields)
        self.purpose = purpose
        self.provenance = provenance

    def render(self, values):
        return self.template.format(**values)

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"RegisteredTemplate({self.template_id!r}, {self.scope!r})"


def _is_decimal_literal(value) -> bool:
    """A finite decimal number written out, e.g. "0.8131" or "135.761".

    Deliberately a TYPE test, not a vocabulary test: it admits any number and
    no words at all, so a template substitution cannot smuggle prose.
    """
    if isinstance(value, bool) or not isinstance(value, str) or not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    if not body or body.count(".") > 1:
        return False
    return all(ch.isdigit() or ch == "." for ch in body) and any(ch.isdigit() for ch in body)


#: Declared substitution types. A field type is a predicate over the SUBSTITUTED
#: STRING - never a judgement about its meaning.
FIELD_TYPES = {
    "decimal": _is_decimal_literal,
}


class Authorization:
    """The authorization a caller presents for one persisted field.

    `statement_id` cites a registered statement; `template_id` plus `fields`
    cites a registered template and its substitutions. Supplying neither means
    the caller has no authorization, and the field is rejected.
    """

    __slots__ = ("statement_id", "template_id", "fields", "field_kind")

    def __init__(self, statement_id=None, template_id=None, fields=None,
                 field_kind=None):
        self.statement_id = statement_id
        self.template_id = template_id
        self.fields = dict(fields or {})
        self.field_kind = field_kind

    def __repr__(self):  # pragma: no cover - diagnostic only
        return f"Authorization({self.statement_id or self.template_id!r})"


_APPROVED_LABEL_LIST: Tuple["ApprovedLabel", ...] = (
    ApprovedLabel(
        value="BOREAS_ECGR_SCALE_UNRESOLVED",
        field_kind="exclusion_reason",
        purpose="Machine-readable reason Boreas 1 is excluded from every GR-derived calculation.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="ECGR",
        field_kind="gr_family_source_curve_name",
        purpose="Source curve mnemonic as recorded in the approved LAS file.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="ECGR_api",
        field_kind="gr_family_canonical_name",
        purpose="Canonical GR-family curve identity; never treated as interchangeable.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GR",
        field_kind="gr_family_source_curve_name",
        purpose="Source curve mnemonic as recorded in the approved LAS file.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GRD",
        field_kind="gr_family_source_curve_name",
        purpose="Source curve mnemonic as recorded in the approved LAS file.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GRD_api",
        field_kind="gr_family_canonical_name",
        purpose="Canonical GR-family curve identity; never treated as interchangeable.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GR_EXCLUDED_UNRESOLVED_SCALE",
        field_kind="gr_proxy_confidence_class",
        purpose="Confidence class assigned to a well excluded for an unresolved GR scale anomaly.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GR_PROXY_HIGH",
        field_kind="gr_proxy_confidence_class",
        purpose="Confidence class describing DATA and PROXY confidence only.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GR_PROXY_INTERMEDIATE",
        field_kind="gr_proxy_confidence_class",
        purpose="Confidence class describing DATA and PROXY confidence only.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="GR_api",
        field_kind="gr_family_canonical_name",
        purpose="Canonical GR-family curve identity; never treated as interchangeable.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="eligible_density_for_sv",
        field_kind="mask_name",
        purpose="Name of the density input-admissibility mask.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="eligible_dynamic_elastic",
        field_kind="mask_name",
        purpose="Name of the dynamic-elastic input-admissibility mask.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="eligible_sonic_nct_candidate",
        field_kind="mask_name",
        purpose="Name of the sonic NCT-candidate input-admissibility mask.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="assumed_configured",
        field_kind="evidence_class",
        purpose="Provenance class of a configured endpoint scenario; no code path can promote it.",
        provenance="Enumerated from the ACTUAL emitted gr_endpoint_scenarios.csv record."),
    ApprovedLabel(
        value="correlation_derived_screening_proxy_uncalibrated",
        field_kind="evidence_class",
        purpose="Provenance class of the uncalibrated screening proxy.",
        provenance="Enumerated from the ACTUAL emitted gr_proxy_sensitivity_summary.csv record."),
    ApprovedLabel(
        value="measured",
        field_kind="evidence_class",
        purpose="Provenance class: a physically logged quantity that passed the locked LAS contract.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="qc_only_excluded",
        field_kind="use_status",
        purpose="Configured disposition: factual QC display and availability reporting only.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="screening_proxy_allowed",
        field_kind="use_status",
        purpose="Configured disposition: screening proxy permitted, well has approved tops.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
    ApprovedLabel(
        value="screening_proxy_allowed_depth_tied",
        field_kind="use_status",
        purpose="Configured disposition: screening proxy permitted but results are depth-tied.",
        provenance="Enumerated from the actual persisted Increment 6 export; every label this project writes is a member of this registry."),
)

#: Increment 6.1.6 (Finding 3): authorization requires field_kind AND value.
#: Increment 6.1.5 keyed this registry by VALUE alone, so `ApprovedLabel.field_kind`
#: existed but was never enforced - `use_status="GR"` passed because `GR` was
#: approved somewhere, as a curve mnemonic. The mapping is now two-level and the
#: field kind is supplied by the caller, never parsed out of a context string.
APPROVED_LABELS: Dict[str, Dict[str, "ApprovedLabel"]] = {}
for _lab in _APPROVED_LABEL_LIST:
    _bucket = APPROVED_LABELS.setdefault(_lab.field_kind, {})
    if _lab.value in _bucket:  # pragma: no cover - fails at import if violated
        raise ValueError(
            f"duplicate approved label ({_lab.field_kind!r}, {_lab.value!r})")
    _bucket[_lab.value] = _lab
del _lab, _bucket

#: Every declared label field kind. An unknown field kind fails closed.
APPROVED_LABEL_FIELD_KINDS: Tuple[str, ...] = tuple(sorted(APPROVED_LABELS))


def approved_label(field_kind, value):
    """Return the ApprovedLabel for (field_kind, value), or None.

    Both parts are required. A value approved under one field kind does not
    authorize it under another.
    """
    return APPROVED_LABELS.get(field_kind, {}).get(value)


# Every exact statement this project persists, enumerated from the ACTUAL
# Increment 6 export rather than described. Authorization is by id.
_REGISTERED_STATEMENT_LIST: Tuple["RegisteredStatement", ...] = (
    RegisteredStatement(
        statement_id="interpretive_01_candidate_data_only_no_nct_fitted_",
        scope=SCOPE_INTERPRETIVE,
        text="CANDIDATE DATA ONLY - no NCT fitted. This mask does not fit a trend, does not select a donor interval, does not claim normal compaction, and does not claim overpressure. It is not proof that any interval is normally compacted, and it assigns no lithology.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_02_eligibility_is_a_necessary_not_suf",
        scope=SCOPE_INTERPRETIVE,
        text="Eligibility is a necessary, not sufficient, condition. Increment 6 does not fill missing density and does not compute vertical stress. A log that begins well below the seabed cannot support an overburden integral from surface regardless of how many of its own samples are eligible.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_03_formal_exclusion_from_every_lithol",
        scope=SCOPE_INTERPRETIVE,
        text="FORMAL EXCLUSION from every lithology-dependent, GR-normalized, screening-proxy (VSH_GR_linear_proxy_frac) and NCT-candidate calculation. The ECGR curve carries an unresolved scale/acquisition anomaly: its central tendency is roughly an order of magnitude below what an API-scaled gamma-ray log over a comparable section would show, its range extends across several hundred API, it includes values at or below zero, and it contains samples above the well's own declared seabed marker. No independent tool header, calibration record, or environmental-correction metadata is available to adjudicate the cause. The curve is therefore EXCLUDED, not corrected: applying a shift, gain, or normalization would fabricate a calibration that does not exist, and would silently propagate into every downstream screening proxy and NCT candidate interval. Boreas 1 remains available for factual raw-GR QC display and availability reporting only. The specific numeric values supporting this disposition are MEASURED INDEPENDENTLY by the integration run and reported there - they are deliberately not hardcoded in this file.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_04_formally_excluded_from_every_gr_de",
        scope=SCOPE_INTERPRETIVE,
        text="Formally excluded from every GR-derived calculation (exclusion_reason='BOREAS_ECGR_SCALE_UNRESOLVED'). The curve remains available for factual raw QC display and availability reporting only. Good coverage does not resolve an unresolved scale/acquisition anomaly, so coverage statistics do not override this classification.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_05_grd_is_a_differently_named_gr_fami",
        scope=SCOPE_INTERPRETIVE,
        text="GRD is a differently named GR-family curve and is NEVER treated as interchangeable with GR or ECGR. This well has NO approved formation tops, so every result for it is depth-tied and stratigraphically unvalidated, and any future use as an NCT donor would remain so. That limitation is recorded here, in the machine-readable use_status, not only in prose.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_06_input_admissibility_only_increment",
        scope=SCOPE_INTERPRETIVE,
        text="Input-admissibility only. Increment 6 computes no Young's modulus, Poisson ratio, bulk modulus, or shear modulus. The Vp/Vs condition is a CONFIGURED NON-NEGATIVE-POISSON-RATIO APPLICABILITY SCREEN (inclusive at Vp/Vs = sqrt(2), where nu = 0 exactly), not a test of physical possibility. Excluded ratios are diagnosed by regime: non-positive bulk modulus (Vp/Vs <= sqrt(4/3), genuinely outside the isotropic elastic model); positive bulk modulus with negative Poisson ratio (sqrt(4/3) < Vp/Vs < sqrt(2), unusual and outside this project's conservative policy, but NOT non-physical); and above the configured plausibility maximum (Vp/Vs > 4, a project credibility limit, not a Poisson-domain boundary). These are never aggregated into a single 'non-physical' count. No excluded sample is deleted from the well frame or corrected.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_07_marks_samples_technically_admissib",
        scope=SCOPE_INTERPRETIVE,
        text="Marks samples technically admissible as input to a LATER dynamic-elastic calculation. Increment 6 computes NO elastic property - no Young's modulus, no Poisson ratio, no bulk or shear modulus. It only records where the three required inputs coexist and pass the configured non-negative-Poisson-ratio applicability screen. Excluded Vp/Vs values are diagnosed BY REGIME (non-positive bulk modulus; positive bulk modulus with negative Poisson ratio; above the configured plausibility maximum) and are never aggregated under a single \"non-physical\" label.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_08_marks_samples_technically_admissib",
        scope=SCOPE_INTERPRETIVE,
        text="Marks samples technically admissible as input to a LATER vertical-stress (Sv) integration. Increment 6 neither fills missing density nor computes Sv; a sample being eligible says nothing about whether an integration over it would be defensible, since a density log that starts at ~470 m TVDSS cannot by itself support an overburden integral from surface.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_09_marks_samples_that_are_candidate_d",
        scope=SCOPE_INTERPRETIVE,
        text="Marks samples that are CANDIDATE DATA for a LATER sonic normal-compaction -trend analysis. This is a data-admissibility mask and nothing more. It does NOT fit a trend, does NOT select a donor interval, does NOT claim normal compaction, does NOT claim overpressure, and must never be read as evidence that any interval is normally compacted or is any named lithology.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_10_the_recorded_values_span_a_range_a",
        scope=SCOPE_INTERPRETIVE,
        text="The recorded values span a range and central tendency typical of conventionally API-scaled gamma-ray logs. This is a statement about the NUMERIC distribution and the scaling convention only; no depositional setting, rock type, or lithology is asserted or implied. This well has approved, survey-corrected Increment 5 formation tops, so its results can be annotated against locked stratigraphic markers.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="interpretive_11_this_well_s_gr_canonicalizes_to_th",
        scope=SCOPE_INTERPRETIVE,
        text="This well's GR canonicalizes to the same name as Poseidon 2's (GR_api), but it is a different tool run in a different well with no cross-well calibration tie. Endpoints are estimated from this well's own samples only. No approved formation tops exist, so results are explicitly depth-tied and unvalidated.",
        purpose="Persisted project-specific interpretive statement.",
        provenance="Human-authored and reviewed; enumerated from the actual persisted Increment 6 content."),
    RegisteredStatement(
        statement_id="proxy_limitations",
        scope=SCOPE_METHOD,
        text="IGR and the linear screening proxy are dimensionless quantities derived under ASSUMED endpoints. The proxy is NOT a calibrated shale volume and NOT a lithology. Clipped and unclipped indices are computed and retained together in memory; the clipped counts here quantify how far the real data fell outside the assumed endpoint bracket. Data/proxy confidence only - asserts no named lithology and no calibration.",
        purpose="States what VSH_GR_linear_proxy_frac is NOT; persisted as the `limitations` field of every proxy sensitivity row.",
        provenance="Enumerated from the actual persisted Increment 6 export; the project cannot state its own scientific boundary without it."),
    RegisteredStatement(
        statement_id="proxy_calibration_status",
        scope=SCOPE_METHOD,
        text="screening_proxy_uncalibrated_not_a_shale_volume",
        purpose="Self-labelling `calibration_status` value carrying the denial inside the field itself.",
        provenance="Enumerated from the actual persisted Increment 6 export; the project cannot state its own scientific boundary without it."),
    RegisteredStatement(
        statement_id="shale_proxy_transform_policy_key",
        scope=SCOPE_METHOD,
        text="shale_proxy_transform",
        purpose="Required configuration key naming the single permitted transform.",
        provenance="Enumerated from the actual persisted Increment 6 export; the project cannot state its own scientific boundary without it."),
    RegisteredStatement(
        statement_id="increment_title",
        scope=SCOPE_METHOD,
        text="Gamma-Ray QC, Shale-Proxy Sensitivity, Well-Frame Assembly, and Method-Eligibility Framework",
        purpose="The increment title persisted in the manifest.",
        provenance="Enumerated from the actual persisted Increment 6 export; the project cannot state its own scientific boundary without it."),
    RegisteredStatement(
        statement_id="proxy_transform_name",
        scope=SCOPE_METHOD,
        text="linear_identity_of_clipped_igr",
        purpose="The `transform_name` of GrProxyResult.",
        provenance="Enumerated from the actual persisted Increment 6 export; the project cannot state its own scientific boundary without it."),
    RegisteredStatement(
        statement_id="named_lithology_statement",
        scope=SCOPE_EXPLANATORY,
        text="NO named lithology is assigned anywhere in Increment 6. Gamma-ray response is not uniquely diagnostic of rock type, and no independent lithological evidence (core, cuttings description, image log, spectral GR, or calibrated multi-mineral solution) is available in this project. Low-GR intervals occur independently in each of the three GR-eligible wells; cross-well stratigraphic persistence is NOT established, and cannot be, because two of those wells have no approved formation tops. Those intervals therefore remain UNRESOLVED in lithology. All classifications in this increment describe DATA AND PROXY CONFIDENCE ONLY.",
        purpose="The manifest's own statement that no named lithology is assigned anywhere.",
        provenance="Human-authored and reviewed; the single explanatory field this project persists."),
)

REGISTERED_STATEMENTS = {r.statement_id: r for r in _REGISTERED_STATEMENT_LIST}


_REGISTERED_TEMPLATE_LIST: Tuple["RegisteredTemplate", ...] = (
    RegisteredTemplate(
        template_id="gr_proxy_confidence_rationale",
        scope=SCOPE_INTERPRETIVE,
        template="valid_fraction={valid_fraction}, dynamic_range_p05_p95={dynamic_range_p05_p95} API, proxy_median_spread_across_3_scenarios={proxy_median_spread}. Describes confidence in the DATA and the SCREENING PROXY only; asserts no lithology and no calibration.",
        fields={
            "valid_fraction": "decimal",
            "dynamic_range_p05_p95": "decimal",
            "proxy_median_spread": "decimal",
        },
        purpose="Per-well confidence rationale. The prose is fixed; only the three MEASURED numbers vary.",
        provenance="Enumerated from the actual persisted Increment 6 export. Substitutions are restricted to decimal literals, so the template cannot carry prose."),
)

REGISTERED_TEMPLATES = {t.template_id: t for t in _REGISTERED_TEMPLATE_LIST}


def _duplicate_registry_ids():
    """Ids must be unique across statements and templates; a duplicate would
    make authorization ambiguous."""
    ids = [r.statement_id for r in _REGISTERED_STATEMENT_LIST] + \
          [t.template_id for t in _REGISTERED_TEMPLATE_LIST]
    return sorted({i for i in ids if ids.count(i) > 1})


if _duplicate_registry_ids():  # pragma: no cover - fails at import if violated
    raise ValueError(f"duplicate registry ids: {_duplicate_registry_ids()}")


def _normalize(text: str) -> str:
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
    )


def _normalize_tokens(text: str) -> set:
    return set(_normalize(text).split())


def find_prohibited_lithology_terms(text: str) -> Tuple[str, ...]:
    """SUPPLEMENTARY DIAGNOSTIC LINTER ONLY.

    Returns any prohibited term this module happens to recognize in `text`.
    Increment 6.1.5: this function AUTHORIZES NOTHING. It is used only to
    annotate a violation with whatever rock words it can name, so a reader
    sees why a rejected string looked suspicious. Its vocabulary is a curated
    list of 28 terms and is NOT exhaustive - `chalk`, `chert` and `qxzite` are
    all absent from it - which is precisely why nothing is permitted on the
    strength of it returning empty.
"""
    if not isinstance(text, str) or not text:
        return ()
    normalized = _normalize(text)
    tokens = set(normalized.split())
    found = []
    for term in PROHIBITED_LITHOLOGY_TERMS:
        term_norm = _normalize(term)
        parts = term_norm.split()
        if len(parts) == 1:
            if parts[0] in tokens:
                found.append(term)
        elif f" {term_norm} " in f" {normalized} ":
            found.append(term)
    return tuple(found)


def _violation(context, scope, text, reason):
    """Build a violation record. `terms` is DIAGNOSTIC ONLY - it reports the
    rock words this module happens to recognize, and is frequently empty for a
    genuine violation (an unregistered statement, an unknown lithology). It is
    never the reason for the rejection."""
    return {
        "context": context,
        "scope": scope,
        "terms": sorted(set(find_prohibited_lithology_terms(text))),
        "reason": reason,
    }


def validate_no_prohibited_interpretation(scope_entries) -> Tuple[dict, ...]:
    """
    Validate that every persisted controlled field is POSITIVELY AUTHORIZED.

    `scope_entries` is an iterable of `(context, text, scope)` or
    `(context, text, scope, authorization)`. An entry with no `Authorization`
    presents no credential, and is rejected in every controlled scope - which
    is all four of them.

    Returns a tuple of violation dicts (empty when clean). Nothing is raised:
    the caller decides what a violation means, and the manifest and completion
    gate DERIVE their result from the returned list rather than assuming it.

      LABEL        the value must be a member of `APPROVED_LABELS`.
      INTERPRETIVE the text must equal a registered statement, or a registered
                   template rendered with strictly typed substitutions.
      METHOD       the text must equal the registered statement its
                   `statement_id` names - id and text validated together.
      EXPLANATORY  identical to METHOD, applied to every non-empty statement
                   whether or not any prohibited term is detected.

    There is no branch here that accepts text because a prohibited-term scan
    came back empty. An unknown lithology, and an invented word, are rejected
    for exactly the same reason as an innocent unregistered sentence: no
    authorization was presented.
    """
    violations = []
    for entry in scope_entries:
        entry = tuple(entry)
        if len(entry) == 4:
            context, text, scope, auth = entry
        elif len(entry) == 3:
            (context, text, scope), auth = entry, None
        else:
            raise ValueError(
                f"scope entry must be (context, text, scope[, authorization]); got "
                f"{len(entry)} elements: {entry!r}"
            )
        if scope not in VALID_VALIDATION_SCOPES:
            raise ValueError(
                f"{context}: unknown validation scope {scope!r}; expected one of "
                f"{VALID_VALIDATION_SCOPES}."
            )
        if not isinstance(text, str) or not text:
            # An absent optional field carries no assertion and persists no
            # claim. Every NON-EMPTY field below requires authorization.
            continue

        # ------------------------------------------------------------------
        # LABEL - typed, enumerated values only.
        # ------------------------------------------------------------------
        if scope == SCOPE_LABEL:
            field_kind = getattr(auth, "field_kind", None) if auth is not None else None
            if field_kind is None:
                violations.append(_violation(
                    context, scope, text,
                    "No field_kind presented for a persisted label. Increment 6.1.6: a "
                    "label is authorized by (field_kind, value) together, and the field "
                    "kind must be supplied by the caller - it is never parsed out of a "
                    "human-readable context string."))
                continue
            if field_kind not in APPROVED_LABELS:
                violations.append(_violation(
                    context, scope, text,
                    f"Unknown label field_kind {field_kind!r}; expected one of "
                    f"{APPROVED_LABEL_FIELD_KINDS}."))
                continue
            if approved_label(field_kind, text) is None:
                other = sorted(k for k in APPROVED_LABELS if text in APPROVED_LABELS[k])
                extra = (f" It IS approved as {other} - a value approved under one field "
                         f"kind does not authorize it under another." if other else "")
                violations.append(_violation(
                    context, scope, text,
                    f"Label value is not approved for field_kind {field_kind!r}.{extra} "
                    f"Arbitrary caller-supplied label text is rejected whether or not it "
                    f"contains a recognizable lithology term."))
            continue

        # ------------------------------------------------------------------
        # INTERPRETIVE / METHOD / EXPLANATORY - registered statement or,
        # for interpretive, a registered template with typed substitutions.
        # ------------------------------------------------------------------
        if auth is None or not isinstance(auth, Authorization):
            violations.append(_violation(
                context, scope, text,
                f"No authorization presented for a persisted {scope} field. Every "
                f"such field must cite a registered statement_id, or (interpretive "
                f"only) a registered template_id with typed substitutions. "
                f"Unregistered free text is rejected unconditionally - not because a "
                f"prohibited term was detected, but because nothing authorized it."))
            continue

        if auth.statement_id is not None and auth.template_id is not None:
            violations.append(_violation(
                context, scope, text,
                "Authorization cites BOTH a statement_id and a template_id; exactly "
                "one canonical authorization must be presented."))
            continue

        if auth.statement_id is not None:
            registered = REGISTERED_STATEMENTS.get(auth.statement_id)
            if registered is None:
                violations.append(_violation(
                    context, scope, text,
                    f"Unknown statement_id {auth.statement_id!r}: it is not a member of "
                    f"REGISTERED_STATEMENTS."))
                continue
            if registered.scope != scope:
                violations.append(_violation(
                    context, scope, text,
                    f"Statement {auth.statement_id!r} is registered for scope "
                    f"{registered.scope!r} and cannot authorize a {scope!r} field."))
                continue
            if text != registered.text:
                violations.append(_violation(
                    context, scope, text,
                    f"Text does not match registered statement {auth.statement_id!r} "
                    f"EXACTLY. Case changes, added or removed clauses, altered "
                    f"punctuation and near-misses are all rejected: the registered "
                    f"text is the canonical persisted decision."))
            continue

        if auth.template_id is not None:
            template = REGISTERED_TEMPLATES.get(auth.template_id)
            if template is None:
                violations.append(_violation(
                    context, scope, text,
                    f"Unknown template_id {auth.template_id!r}: it is not a member of "
                    f"REGISTERED_TEMPLATES."))
                continue
            if template.scope != scope:
                violations.append(_violation(
                    context, scope, text,
                    f"Template {auth.template_id!r} is registered for scope "
                    f"{template.scope!r} and cannot authorize a {scope!r} field."))
                continue
            undeclared = sorted(set(auth.fields) - set(template.fields))
            missing = sorted(set(template.fields) - set(auth.fields))
            if undeclared or missing:
                violations.append(_violation(
                    context, scope, text,
                    f"Template {auth.template_id!r} substitution mismatch - undeclared "
                    f"field(s) {undeclared}, missing field(s) {missing}. Only declared "
                    f"fields may be substituted."))
                continue
            mistyped = sorted(
                name for name, value in auth.fields.items()
                if not FIELD_TYPES[template.fields[name]](value)
            )
            if mistyped:
                violations.append(_violation(
                    context, scope, text,
                    f"Template {auth.template_id!r} substitution(s) {mistyped} do not "
                    f"satisfy their declared type. A substitution is restricted to a "
                    f"typed value so a template cannot become a channel for prose."))
                continue
            if text != template.render(auth.fields):
                violations.append(_violation(
                    context, scope, text,
                    f"Text does not match template {auth.template_id!r} rendered with "
                    f"the declared substitutions. The rendered template is the "
                    f"canonical persisted decision."))
            continue

        violations.append(_violation(
            context, scope, text,
            "Authorization presented neither a statement_id nor a template_id."))
    return tuple(violations)
