"""
p2mem.models - Minimal typed result/schema objects for the LAS-ingestion
layer (Increment 2 / 2.1).

Design rationale
-----------------
The Increment 2 specification explicitly requires "typed, documented
result objects rather than an undocumented tuple." This module collects
every such object in one place so that `p2mem/io/las.py` can focus on
parsing/resolution logic and every caller (tests, the notebook, the
inventory builder) imports structure from a single, auditable source.

All objects here are plain, frozen `dataclasses` - no third-party schema
library (e.g. pydantic) is introduced, consistent with the project's
minimal-dependency policy. Frozen dataclasses are used wherever an object
represents an immutable fact about a specific ingestion run (a parsed
header, a resolved curve, a computed statistic); this makes it impossible
to accidentally mutate a diagnostic result after it has been computed and
reported.

Nothing in this module performs I/O, unit conversion, or numerical
computation - it is data structure only.

Increment 2.1 correction
-------------------------
An independent audit of Increment 2 found that canonical curve names were
not unit-suffixed (e.g. a *velocity* array, in m/s, was stored under the
key "DTCO" - the mnemonic that conventionally means sonic *slowness* in
us/ft). This risks a downstream reader assuming the wrong physical
quantity purely from the key name. Increment 2.1 requires every raw and
canonical array to be identified by an explicit, unit-suffixed name (e.g.
"DTCO_us_per_ft" for the raw slowness, "VP_m_s" for the converted
velocity), and requires a curve contract to declare which single curve
plays the "measured depth" role explicitly, rather than that role being
inferred by searching for a canonical name spelled "DEPT". The fields
below reflect that correction; see `CurveContractEntry.semantic_role`,
`CurveContractEntry.source_curve_name`, `CurveContractEntry.raw_canonical_name`,
and the redesigned `CurveStats`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np

# Role a contract-declared curve plays. "measured_depth" is the single
# curve used as the depth index for diagnostics (see
# `las.py:_MEASURED_DEPTH_ROLE`); every other curve is a "measurement".
SEMANTIC_ROLE_MEASURED_DEPTH = "measured_depth"
SEMANTIC_ROLE_MEASUREMENT = "measurement"


# ---------------------------------------------------------------------------
# Raw LAS header structures (what was literally present in the file)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DefinitionLine:
    """
    One parsed LAS "definition line" from the Version, Well, Curve, or
    Parameter sections, in the standard LAS 2.0 four-field form:

        MNEM.UNIT    VALUE/NAME    :DESCRIPTION

    Every field is preserved exactly as read (including empty strings for
    an absent mnemonic or unit) - no field is inferred or filled in.
    """

    mnemonic: str
    unit: str
    value: str
    description: str


@dataclass(frozen=True)
class CurveHeaderEntry:
    """
    One curve as declared in a LAS file's ~Curve Information Section,
    in original file order.

    `ordinal` is the curve's zero-based position within the curve section
    (and, for an unwrapped LAS file, its corresponding zero-based column
    position in the ~Ascii data section). `description_ordinal` and
    `description_name` are parsed OUT of the free-text description when it
    follows the "<index> <NAME>" pattern seen in the Poseidon 2 / Boreas 1
    / Poseidon North 1 / Proteus 1ST2 files (e.g. "1 DCAV") - they are
    independent, file-content-derived signals used to cross-check
    `ordinal`, never a substitute for it.
    """

    ordinal: int
    raw_mnemonic: str
    raw_unit: str
    raw_api_code: str
    raw_description: str
    description_ordinal: Optional[int]
    description_name: Optional[str]


@dataclass(frozen=True)
class LasHeaderInfo:
    """
    Everything read from a LAS file's header sections (Version, Well,
    Curve, Parameter), plus file-identity metadata, WITHOUT reading or
    parsing the ~Ascii data section. This is what notebook Step 11
    ("Inspect actual LAS headers") and Step 12 ("Validate each per-file
    contract") operate on before any numeric data is touched.
    """

    source_path: str
    source_filename: str
    sha256: str
    las_version: Optional[str]
    wrap: Optional[str]
    well_name: Optional[str]
    declared_null: Optional[float]
    declared_strt: Optional[float]
    declared_stop: Optional[float]
    declared_step: Optional[float]
    version_section: Tuple[DefinitionLine, ...]
    well_section: Tuple[DefinitionLine, ...]
    parameter_section: Tuple[DefinitionLine, ...]
    curve_headers: Tuple[CurveHeaderEntry, ...]
    data_section_line_offset: int  # line index (0-based) where ~Ascii data begins


# ---------------------------------------------------------------------------
# Curve contract structures (what the config/las_curve_contracts.yml says
# a given curve in a given file SHOULD be)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CurveContractEntry:
    """
    One curve's expected identity and canonicalization rule, as declared
    in `config/las_curve_contracts.yml` for one specific source file.

    Identity fields (never fabricated - read directly from the source
    header during contract authoring):
        `source_curve_name`   - the physical curve's own short identity
                                 token (e.g. "DTCO", "GR", "DEPT"), as used
                                 in this file's own description text. This
                                 is NOT necessarily the array key - see
                                 below.
        `raw_mnemonic`, `raw_unit`, `raw_description`, `description_ordinal`,
        `description_name` - exactly what Increment 2 already captured.

    Naming fields (Increment 2.1 correction - explicit, unit-suffixed
    array keys so a key name can never be mistaken for the wrong physical
    quantity):
        `raw_canonical_name`  - the key under which this curve's raw
                                 (NULL-sentinel-preserving) values would be
                                 identified, e.g. "DTCO_us_per_ft". This
                                 documents the raw unit in the name; the
                                 numeric matrix itself is still
                                 `LasFileResult.raw_data` (see that
                                 docstring for why the matrix form is
                                 retained).
        `canonical_name`      - the key in `LasFileResult.canonical_data`
                                 holding the NULL-substituted, exactly-
                                 unit-converted (if `conversion_function`
                                 is not "identity") array, e.g. "VP_m_s".
                                 For a curve with no declared conversion,
                                 `canonical_name` still carries an explicit
                                 unit suffix (e.g. "GR_api"), never the
                                 bare source name alone.
        `canonical_unit`      - the unit of the array stored under
                                 `canonical_name`.

    `semantic_role` is `"measured_depth"` for exactly one curve per file
    (the file's depth index) and `"measurement"` for every other curve.
    The depth role is never inferred by matching a canonical name spelled
    "DEPT" - see `las.py:_MEASURED_DEPTH_ROLE` and
    `load_file_contract_config`'s validation.

    `conversion_function` is either the literal string `"identity"` (no
    numeric transform - the canonical value equals the NULL-substituted
    raw value; only the array's *name* changes when depth is renamed
    DEPT -> MD) or the name of an exact, unit-only function in
    `p2mem.units` (e.g. "us_per_ft_to_m_per_s"). It is never `None` in
    Increment 2.1 - every curve entry must say explicitly how its
    canonical array was produced.
    """

    ordinal: int
    semantic_role: str
    source_curve_name: str
    raw_mnemonic: str
    raw_unit: str
    raw_description: str
    description_ordinal: Optional[int]
    description_name: Optional[str]
    raw_canonical_name: str
    canonical_name: str
    canonical_unit: str
    required: bool
    conversion_function: str
    notes: str


@dataclass(frozen=True)
class FileContract:
    """
    The complete expected curve contract for one specific LAS source file.

    Increment 2.1 adds the file-identity fields an independent audit found
    the Increment 2 resolver did not actually check: `expected_sha256`,
    `expected_las_version`, `expected_wrap`, and `expected_data_layout`.
    These, together with `expected_well_identifier`, `expected_null_value`,
    and `expected_curve_count`, are cross-checked against the file's
    actual parsed header by `las.py:resolve_curve_contract` BEFORE any
    curve-level resolution is attempted, and any mismatch (or an absent
    value where one is required) is a blocking ERROR - never a warning,
    and never silently ignored.

    `expected_null_value` is required (not optional) in Increment 2.1: a
    contract that does not know its file's NULL sentinel cannot safely
    validate NULL-substitution, which the Increment 2 audit identified as
    a real gap (the resolver previously "passed" a file with no NULL
    value declared and a contract that also left it unset).
    """

    source_filename: str
    expected_sha256: str
    expected_well_identifier: str
    expected_las_version: str
    expected_wrap: str
    expected_null_value: float
    expected_curve_count: int
    expected_data_layout: str
    curves: Tuple[CurveContractEntry, ...]


# ---------------------------------------------------------------------------
# Resolution / diagnostic results (what happened when the contract was
# checked against the actual header, and what the data looks like)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CurveResolution:
    """
    The outcome of attempting to resolve one contract curve entry against
    the actual parsed curve headers of a specific file.

    `status` is one of:
        "RESOLVED"         - all required identifiers agreed; safe to use.
        "MISSING_OPTIONAL" - the curve was not found, but the contract
                              marks it optional, so this is not an error.
        "FAILED"           - the curve could not be safely resolved (a
                              required curve was missing, or the
                              identifiers that were found disagreed with
                              each other). This never means "a different
                              column was substituted" - resolution either
                              succeeds cleanly or is reported as failed.

    `canonical_name` identifies the contract entry that was evaluated
    (matches `CurveContractEntry.canonical_name`); `source_curve_name` is
    carried alongside it so a resolution report never needs a second
    lookup into the contract to explain what physical curve was involved.
    """

    canonical_name: str
    source_curve_name: str
    status: str
    ordinal: Optional[int]
    matched_raw_mnemonic: Optional[str]
    matched_raw_unit: Optional[str]
    matched_raw_description: Optional[str]
    conversion_applied: Optional[str]
    detail: str


@dataclass(frozen=True)
class IngestionIssue:
    """
    One fact worth reporting about an ingestion attempt: either an ERROR
    (blocks a successful load - see `load_las_file`) or a WARNING
    (recorded and surfaced, but does not by itself stop ingestion, per
    the Increment 2 specification's distinction between curves the loader
    must "detect/report" and conditions the loader must "reject").

    Increment 2.1 note: a NULL-sentinel mismatch between a file's declared
    header value and its contract's `expected_null_value` is now always
    reported as an ERROR (see code "NULL_MISMATCH"), not a WARNING - a
    wrong NULL value changes which samples get substituted to NaN, so it
    is a data-safety issue, not a cosmetic one.
    """

    severity: str  # "ERROR" or "WARNING"
    code: str
    message: str
    context: str


@dataclass(frozen=True)
class DepthDiagnostics:
    """
    Data-derived depth-index diagnostics, and their comparison against the
    file's declared STRT/STOP/STEP header values. Comparisons use a small
    floating-point tolerance (see `las.py:_DEPTH_ENDPOINT_TOLERANCE_M`),
    never exact equality, since declared header values are frequently
    rounded to a "nice" number while the data's actual first/last sample
    is not.
    """

    declared_strt: Optional[float]
    declared_stop: Optional[float]
    declared_step: Optional[float]
    data_start: float
    data_stop: float
    data_min_step: float
    data_max_step: float
    data_median_step: float
    n_samples: int
    n_duplicate_md: int
    n_non_monotonic: int
    strt_matches_declared: Optional[bool]
    stop_matches_declared: Optional[bool]
    step_matches_declared: Optional[bool]


@dataclass(frozen=True)
class CurveStats:
    """
    Descriptive (not QC-judgemental) statistics for one resolved curve,
    reported with EVERY number's unit made explicit - the Increment 2.1
    correction for an audit finding that the Increment 2 coverage output
    reported minimum/maximum values under a canonical (post-conversion-
    implying) name while the numbers themselves were still in the raw,
    pre-conversion unit.

    Two independent sets of statistics are always reported side by side:

        raw_min / raw_max        - computed directly from `raw_unit`
                                    values (the literal parsed column,
                                    e.g. from `LasFileResult.raw_data`),
                                    restricted to samples that are NOT an
                                    exact match of the file's declared
                                    NULL sentinel (a sentinel value like
                                    -999.25 is a metadata marker, not a
                                    physical measurement, so including it
                                    in a "minimum value" would misrepresent
                                    the curve's actual physical range).
        canonical_min / canonical_max - computed from the corresponding
                                    `LasFileResult.canonical_data[canonical_name]`
                                    array (NULL-substituted to NaN, and
                                    exactly unit-converted if
                                    `conversion_function != "identity"`).

    For an identity conversion (`conversion_function == "identity"`),
    `raw_min == canonical_min` and `raw_max == canonical_max` numerically,
    but `raw_unit` and `canonical_unit` are still both reported explicitly
    (they are typically equal strings, e.g. both "API") so a reader never
    has to assume they match.

    `statistics_basis` states in one sentence exactly what filtering was
    applied, so this object is self-describing without cross-referencing
    the code that produced it.
    """

    source_curve_name: str
    raw_mnemonic: str
    raw_description: str
    raw_unit: str
    canonical_name: str
    canonical_unit: str
    conversion_function: str
    n_samples: int
    valid_count: int
    null_count: int
    valid_fraction: float
    raw_min: Optional[float]
    raw_max: Optional[float]
    canonical_min: Optional[float]
    canonical_max: Optional[float]
    statistics_basis: str


@dataclass(frozen=True)
class IngestionFailure:
    """
    A typed, structured record of why one well failed to load during a
    batch (`las.py:load_wells`) - the Increment 2.1 correction for an
    audit finding that Increment 2 stored a bare caught exception per
    failed well, forcing every caller to parse exception text or
    `isinstance` checks to know what kind of failure occurred.

    `error_type` is one of:
        "file_not_found"    - the LAS file path does not exist
                               (`las.py:LasFileNotFoundError`).
        "parsing_failure"   - a structural LAS-syntax defect
                               (`las.py:LasParsingError`): a malformed
                               definition line, a data row with the wrong
                               column count, a non-numeric token, or a
                               non-finite (NaN/Inf) literal token that does
                               not correspond to the declared NULL policy.
        "contract_failure"  - the file's actual header/data could not be
                               safely reconciled with its contract
                               (`las.py:LasContractError`): a file-identity
                               mismatch (filename, SHA-256, WELL, VERS,
                               WRAP, NULL, curve count), an unresolved
                               required curve, or a data-column-count
                               mismatch.
        "conversion_failure"- an exact unit conversion could not be safely
                               applied to a curve's substituted values
                               (`las.py:LasConversionError`): typically a
                               non-null physical value that converts to a
                               non-finite (Inf/-Inf) result.

    `exception` is the original exception object, preserved so a caller
    that wants the full original detail (e.g. `.issues`/`.resolutions` on
    a `LasContractError`) still has it; `message` is `str(exception)` for
    the common case of just wanting to display or log the failure without
    re-importing every exception type.

    This is a *typed* structure, not a substitute for exceptions:
    `load_wells` still lets any exception NOT in this list (a programming
    error, not an expected ingestion-failure mode) propagate uncaught.
    """

    well_key: str
    source_path: str
    error_type: str
    message: str
    exception: BaseException


@dataclass(frozen=True)
class LasFileResult:
    """
    The complete, typed result of successfully loading and contract-
    resolving one LAS file. Returned only when no ERROR-severity issue
    was found (see `las.py:load_las_file`); `issues` may still contain
    WARNING-severity entries (e.g. a duplicate MD sample, a declared/
    data-derived STOP mismatch).

    `raw_data` holds the EXACT parsed numeric matrix, column-ordered
    exactly as the source file's curve section (shape: n_samples x
    n_curves), INCLUDING the original LAS NULL sentinel value wherever it
    appears - no substitution of any kind has been applied to it.

    Increment 2.1 correction: the Increment 2 docstring for this field
    incorrectly stated that `raw_data` had "NULL-substitution ... applied"
    to it. That was never true of the array itself (only of the separate,
    per-curve arrays computed on demand for `canonical_data` and
    `curve_stats`) and has been corrected here. Column `entry.ordinal` of
    this matrix corresponds to `contract.curves[i].raw_canonical_name` for
    the curve whose contract entry has that ordinal.

    `canonical_data` holds one NumPy array per contract-resolved curve,
    keyed by that curve's `canonical_name` (an explicit, unit-suffixed
    name, e.g. "VP_m_s", "GR_api", "MD_m" - never a bare mnemonic that
    could be mistaken for a different physical quantity or unit). Each
    array has had NULL-sentinel-to-NaN substitution applied and, if the
    contract's `conversion_function` for that curve is not `"identity"`,
    the declared exact `p2mem.units` conversion applied. The raw source
    column is never lost - it remains recoverable from `raw_data` at that
    curve's `ordinal`.
    """

    header: LasHeaderInfo
    contract: FileContract
    resolutions: Tuple[CurveResolution, ...]
    depth: DepthDiagnostics
    curve_stats: Tuple[CurveStats, ...]
    raw_data: np.ndarray
    canonical_data: Dict[str, np.ndarray] = field(default_factory=dict)
    issues: Tuple[IngestionIssue, ...] = field(default_factory=tuple)
    contract_status: str = "PASSED"
