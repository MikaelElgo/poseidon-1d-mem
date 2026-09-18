"""
Increment 7 - SCHEMA-DRIVEN, FAILURE-ATOMIC OUTPUT AUTHORIZATION, generalized.

Relationship to the LOCKED Increment 6.1.7 policy
--------------------------------------------------
`p2mem.io.output_policy` is locked. Its registries (`CSV_SCHEMAS`,
`OUTPUT_FIELD_POLICY`, `OUTPUT_STATEMENTS`, `JSON_OBJECT_KEYS`, ...) are
MODULE GLOBALS, and its `validate_emitted_records` requires the COMPLETE
declared artifact set to be presented. Adding Increment 7's nine artifacts to
those globals would (a) modify a locked file and (b) make every Increment 6
export fail closed for not presenting Increment 7 artifacts.

This module therefore does what the Increment 7 brief asks - it EXTENDS the
architecture rather than reimplementing a weaker one. The engine here is the
same algorithm, lifted so that its registries arrive as an explicit
`PolicyBundle` argument instead of being read from module globals:

  * the same closed-schema-first, authorize-second ordering;
  * the same eight categories, plus ONE addition (`enumerated_code_list`,
    below), all reusing the locked category constants;
  * the same collect-from-the-ACTUAL-records rule - field discovery is
    schema-driven, never inferred from a value;
  * the same isolated-staging, re-read, re-validate, canonical-compare,
    failure-atomic publication.

`tests/test_overburden_policy.py` runs this generalized engine against the
LOCKED Increment 6 registries and requires it to reproduce the locked
engine's accept/reject decision on every occurrence of the real, packaged
Increment 6 output records. That is the evidence that the generalization is
faithful rather than merely similar.

The one added category
----------------------
`enumerated_code_list` carries a ';'-joined list of CONTROLLED ENUMERATED
CODES - the `limiting_reasons` field is the only user. Each element must be a
member of the field's declared vocabulary; the list must be sorted and free of
duplicates. This is strictly STRONGER than emitting the same information as a
`structured_diagnostic`, because every element is checked against a closed
vocabulary rather than against a grammar, so it counts as CONTROLLED.

SCOPE OF THE GUARANTEE is unchanged from the locked module:
`structured_diagnostic` and `sanitized_diagnostic` remain outside the
controlled-interpretation guarantee and are counted separately.
"""

from typing import Dict, Optional, Tuple

from p2mem.io.output_policy import (
    CATEGORIES as LOCKED_CATEGORIES,
    CONTROLLED_CATEGORIES as LOCKED_CONTROLLED_CATEGORIES,
    STRUCTURAL_CATEGORIES,
    UNGUARANTEED_CATEGORIES,
    SANITIZED_DIAGNOSTIC_CHARSET,
    SANITIZED_DIAGNOSTIC_MAX_LEN,
    CoverageReport,
    CsvArtifactSchema,
    FieldOccurrence,
    FieldPolicy as LockedFieldPolicy,
)
from p2mem.wellframe_models import (
    ApprovedLabel,
    FIELD_TYPES,
    RegisteredStatement,
    RegisteredTemplate,
    find_prohibited_lithology_terms,
)
from p2mem.overburden_models import (
    DENSITY_MASK_NAMES,
    VALID_GAP_CLASSES,
    VALID_GAP_DISPOSITIONS,
    VALID_LIMITING_REASONS,
    VALID_OVERBURDEN_STATUSES,
    VALID_SCENARIO_NAMES,
    VALID_SEABED_BASES,
)

__all__ = [
    "CATEGORY_ENUMERATED_CODE_LIST", "CATEGORIES", "CONTROLLED_CATEGORIES",
    "PolicyBundle", "FieldPolicy", "OVERBURDEN_BUNDLE",
    "OVERBURDEN_ARTIFACTS", "OVERBURDEN_CSV_SCHEMAS", "OVERBURDEN_MANIFEST_ARTIFACT",
    "OVERBURDEN_STATEMENTS", "OVERBURDEN_TEMPLATES", "OVERBURDEN_LABELS",
    "APPROVED_WELL_KEYS", "SCOPE_OUTPUT_INC7",
    "collect_string_fields", "authorize_occurrence", "validate_artifact_schema",
    "validate_emitted_records", "canonicalize_emitted_records",
    "export_authorized_outputs", "OutputAuthorizationError",
    "bundle_from_locked_increment6",
]

SCOPE_OUTPUT_INC7 = "output_increment7"

CATEGORY_ENUMERATED_CODE_LIST = "enumerated_code_list"
CATEGORIES: Tuple[str, ...] = LOCKED_CATEGORIES + (CATEGORY_ENUMERATED_CODE_LIST,)
CONTROLLED_CATEGORIES: Tuple[str, ...] = (
    LOCKED_CONTROLLED_CATEGORIES + (CATEGORY_ENUMERATED_CODE_LIST,))


class FieldPolicy(LockedFieldPolicy):
    """The declared classification of one emitted string field.

    Subclasses the locked `FieldPolicy` so that the two policies cannot drift
    apart structurally, and widens only the accepted category set.
    """

    def __init__(self, artifact, field, category, field_kind=None,
                 allowed_values=(), statement_ids=(), template_id=None,
                 allow_empty=False):
        if category == CATEGORY_ENUMERATED_CODE_LIST:
            # Bypass the locked constructor's category check for the one added
            # category, then set every attribute the locked class declares.
            if not allowed_values:
                raise ValueError(
                    f"{artifact}:{field}: an enumerated_code_list must declare its closed "
                    f"vocabulary in allowed_values")
            self.artifact = artifact
            self.field = field
            self.category = category
            self.field_kind = field_kind
            self.allowed_values = tuple(allowed_values)
            self.statement_ids = tuple(statement_ids)
            self.template_id = template_id
            self.allow_empty = bool(allow_empty)
            return
        super().__init__(artifact, field, category, field_kind=field_kind,
                         allowed_values=allowed_values, statement_ids=statement_ids,
                         template_id=template_id, allow_empty=allow_empty)


# ---------------------------------------------------------------------------
# The policy bundle: every registry the engine consults, in one object
# ---------------------------------------------------------------------------

class PolicyBundle:
    """All registries required to validate and authorize one artifact set.

    Everything the locked engine read from module globals is a field here, so
    the same code can govern Increment 6's artifacts, Increment 7's, or a
    synthetic set constructed by a test, without any of them being able to
    weaken another.
    """

    __slots__ = ("name", "field_policy", "statements", "templates", "labels",
                 "csv_schemas", "manifest_artifact", "json_object_keys",
                 "json_list_item_kinds", "json_boolean_paths", "json_integer_paths",
                 "json_number_paths", "json_nullable_paths", "approved_well_keys",
                 "artifacts", "field_types", "extra_destination_names")

    def __init__(self, name, field_policies, statements, templates, labels,
                 csv_schemas, manifest_artifact, json_object_keys,
                 json_list_item_kinds, json_boolean_paths, json_integer_paths,
                 json_number_paths, json_nullable_paths, approved_well_keys,
                 field_types, extra_destination_names=("figures",)):
        self.name = name
        self.field_policy: Dict[Tuple[str, str], FieldPolicy] = {}
        for pol in field_policies:
            key = (pol.artifact, pol.field)
            if key in self.field_policy:
                raise ValueError(f"{name}: duplicate output field policy {key}")
            self.field_policy[key] = pol
        self.statements = {s.statement_id: s for s in statements}
        self.templates = {t.template_id: t for t in templates}
        self.labels: Dict[str, Dict[str, ApprovedLabel]] = {}
        for lab in labels:
            bucket = self.labels.setdefault(lab.field_kind, {})
            if lab.value in bucket:
                raise ValueError(
                    f"{name}: duplicate label {(lab.field_kind, lab.value)}")
            bucket[lab.value] = lab
        self.csv_schemas = dict(csv_schemas)
        self.manifest_artifact = manifest_artifact
        self.json_object_keys = dict(json_object_keys)
        self.json_list_item_kinds = dict(json_list_item_kinds)
        self.json_boolean_paths = frozenset(json_boolean_paths)
        self.json_integer_paths = frozenset(json_integer_paths)
        self.json_number_paths = frozenset(json_number_paths)
        self.json_nullable_paths = frozenset(json_nullable_paths)
        self.approved_well_keys = frozenset(approved_well_keys)
        self.field_types = dict(field_types)
        self.artifacts: Tuple[str, ...] = tuple(sorted(
            tuple(self.csv_schemas) + ((manifest_artifact,) if manifest_artifact else ())))
        self.extra_destination_names = frozenset(extra_destination_names)
        self._assert_schema_policy_agreement()

    def _assert_schema_policy_agreement(self):
        """Every schema-declared CSV string field must be classified exactly once.

        The locked module performs this as an import-time assertion. Doing it
        in the constructor gives the same guarantee for every bundle, including
        one a test builds, and prevents a future schema/policy drift from
        weakening the gate silently.
        """
        by_artifact: Dict[str, set] = {}
        for (artifact, field) in self.field_policy:
            if artifact in self.csv_schemas:
                by_artifact.setdefault(artifact, set()).add(field)
        for artifact, schema in self.csv_schemas.items():
            declared = set(schema.string_fields)
            classified = by_artifact.get(artifact, set())
            if declared != classified:
                raise ValueError(
                    f"{self.name}/{artifact}: CSV schema string fields and authorization "
                    f"policy differ: schema_only={sorted(declared - classified)}, "
                    f"policy_only={sorted(classified - declared)}")

    def approved_label(self, field_kind, value):
        return self.labels.get(field_kind, {}).get(value)


# ---------------------------------------------------------------------------
# Type predicates
# ---------------------------------------------------------------------------

def _is_integer_literal(value):
    if isinstance(value, bool) or not isinstance(value, str) or not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return bool(body) and body.isdigit()


OVERBURDEN_FIELD_TYPES = dict(FIELD_TYPES)
OVERBURDEN_FIELD_TYPES["integer"] = _is_integer_literal


def _is_number_with_optional_unit(token, field_types):
    if not isinstance(token, str) or not token:
        return False
    i = len(token)
    while i > 0 and token[i - 1].isalpha():
        i -= 1
    return field_types["decimal"](token[:i]) and token[i:].isalpha() or (
        i == len(token) and field_types["decimal"](token))


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

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


def _validate_csv_schema(bundle, artifact, payload, serialization_stage="auto"):
    """Validate keys, order, requiredness and types without inspecting prose."""
    schema = bundle.csv_schemas[artifact]
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


def _expected_json_primitive_kind(bundle, path):
    if path in bundle.json_boolean_paths:
        return "boolean"
    if path in bundle.json_integer_paths:
        return "integer"
    if path in bundle.json_number_paths:
        return "number"
    if (bundle.manifest_artifact, path) in bundle.field_policy:
        return "string"
    return None


def _validate_json_schema(bundle, artifact, payload, well_keys=()):
    """Validate the complete manifest tree, including empty/non-string leaves."""
    out = []
    supplied_wells = frozenset(well_keys)
    unknown_wells = supplied_wells - bundle.approved_well_keys
    if unknown_wells:
        out.append(_schema_violation(
            artifact, "/wells", "/wells",
            f"well_keys contains unapproved identifier(s): {sorted(unknown_wells)}"))

    def walk(node, path):
        norm = _normalize_json_path(path, well_keys)
        if isinstance(node, dict):
            expected = bundle.json_object_keys.get(norm, "__missing__")
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
            expected_kind = bundle.json_list_item_kinds.get(norm)
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
                        type(value) in (int, float)
                        and __import__("math").isfinite(value)):
                    out.append(_schema_violation(
                        artifact, norm, f"{path}[{i}]", "list item must be a finite number"))
                else:
                    walk(value, f"{path}[{i}]")
            return
        kind = _expected_json_primitive_kind(bundle, norm)
        if kind is None:
            out.append(_schema_violation(
                artifact, norm, path, "primitive path is not declared"))
            return
        if node is None:
            if norm not in bundle.json_nullable_paths:
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


def validate_artifact_schema(bundle, artifact, payload, well_keys=(),
                             serialization_stage="auto"):
    if artifact in bundle.csv_schemas:
        return _validate_csv_schema(bundle, artifact, payload, serialization_stage)
    if artifact == bundle.manifest_artifact:
        return _validate_json_schema(bundle, artifact, payload, well_keys)
    return [_schema_violation(
        artifact, None, None, "artifact has no declared schema")]


# ---------------------------------------------------------------------------
# Collection: the ACTUAL string fields of the ACTUAL records
# ---------------------------------------------------------------------------

def collect_string_fields(bundle, artifact, payload, well_keys=()):
    """Collect every schema-declared string occurrence, including ``""``.

    Field discovery is schema-driven. Numeric-looking text in a declared prose
    field is therefore still prose and must authorize; unknown or missing keys
    are handled independently by `validate_artifact_schema`.
    """
    out = []
    if artifact in bundle.csv_schemas and isinstance(payload, list):
        schema = bundle.csv_schemas[artifact]
        for i, row in enumerate(payload):
            if not isinstance(row, dict):
                continue
            for column in schema.columns:
                value = row.get(column)
                if column in schema.string_fields and isinstance(value, str):
                    out.append(FieldOccurrence(
                        artifact, column, value, f"row[{i}].{column}"))
        return out
    if artifact == bundle.manifest_artifact and isinstance(payload, dict):
        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{path}/{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")
            elif isinstance(node, str):
                norm = _normalize_json_path(path, well_keys)
                if _expected_json_primitive_kind(bundle, norm) == "string":
                    out.append(FieldOccurrence(artifact, norm, node, path))
        walk(payload, "")
    return out


# ---------------------------------------------------------------------------
# Authorization of one occurrence
# ---------------------------------------------------------------------------

_FORBIDDEN_IN_DIAGNOSTIC = ("\n", "\r", "\t", "\\", "://")


def _authorize_structured(value, field_types):
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
                    and _is_number_with_optional_unit(lo, field_types)
                    and _is_number_with_optional_unit(hi, field_types)):
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


def _authorize_code_list(value, policy):
    """Authorize a ';'-joined list of controlled enumerated codes."""
    items = value.split(";")
    if any(not item for item in items):
        return False, "an enumerated code list may not contain an empty element"
    unknown = [i for i in items if i not in policy.allowed_values]
    if unknown:
        return False, (
            f"code(s) {unknown} are not in the closed vocabulary declared for "
            f"{policy.artifact}:{policy.field!r}")
    if len(set(items)) != len(items):
        return False, "an enumerated code list may not repeat a code"
    if items != sorted(items):
        return False, (
            "an enumerated code list must be sorted, so that the same evidence always "
            "produces the same bytes")
    return True, None


def _parse_template(template, text):
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


def authorize_occurrence(bundle, occ):
    """Authorize ONE emitted occurrence against ONE bundle.

    Returns `(ok, authorization, reason)`. `authorization` is the credential
    that travels with the value until serialization, so the emitted bytes can
    be re-checked against what was authorized.
    """
    policy = bundle.field_policy.get((occ.artifact, occ.field))
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
        lab = bundle.approved_label(policy.field_kind, occ.value)
        if lab is None:
            other = sorted(k for k in bundle.labels if occ.value in bundle.labels[k])
            extra = f" (it is approved only as {other})" if other else ""
            return False, None, (
                f"value is not approved for field_kind {policy.field_kind!r}{extra}")
        return True, ("typed_label", policy.field_kind, occ.value), None
    if cat == CATEGORY_ENUMERATED_CODE_LIST:
        ok, why = _authorize_code_list(occ.value, policy)
        return ((True, ("enumerated_code_list", tuple(occ.value.split(";"))), None)
                if ok else (False, None, why))
    if cat == "registered_statement":
        for sid in policy.statement_ids:
            st = bundle.statements.get(sid)
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
            st = bundle.statements.get(sid)
            if st is not None and st.text == occ.value:
                return True, ("statement", sid), None
        tpl = bundle.templates.get(policy.template_id)
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
                     if not bundle.field_types[tpl.fields[n]](v))
        if bad:
            return False, None, (
                f"template {tpl.template_id!r} substitution(s) {bad} do not satisfy their "
                f"declared type, so the template cannot carry prose")
        return True, ("template", tpl.template_id, values), None
    if cat == "structured_diagnostic":
        if occ.value in policy.allowed_values:
            return True, ("structured_sentinel", occ.value), None
        if not _authorize_structured(occ.value, bundle.field_types):
            return False, None, (
                "value does not satisfy the declared machine-diagnostic grammar "
                "(name=integer / name(number<number) / CODE:token, joined by ';')")
        return True, ("structured_diagnostic", None), None
    if cat == "sanitized_diagnostic":
        ok, why = _authorize_sanitized(occ.value)
        return (True, ("sanitized_diagnostic", None), None) if ok else (False, None, why)
    return False, None, f"unhandled category {cat!r}"  # pragma: no cover


# ---------------------------------------------------------------------------
# Whole-set validation
# ---------------------------------------------------------------------------

def validate_emitted_records(bundle, payloads, well_keys=(), expected_artifacts=None,
                             serialization_stage="auto"):
    """Validate schema, then authorize every declared string occurrence.

    `payloads` maps artifact filename -> payload. Every declared artifact must
    be present; exact keys/order, requiredness and types are checked
    independently of values. Only after that closed schema pass are string
    values authorized.
    """
    violations, authorizations = [], []
    counts = dict(controlled=0, structural=0, unguaranteed=0,
                  unclassified=0, unauthorized=0, kind_mismatch=0, schema=0)
    stmts, tpls, labels = set(), set(), set()
    declared = set(bundle.artifacts if expected_artifacts is None else expected_artifacts)
    for name in sorted(set(payloads) - declared):
        violations.append(_schema_violation(
            name, None, None, "artifact has no declared output schema"))
        counts["unclassified"] += 1
        counts["schema"] += 1
    for name in sorted(declared - set(payloads)):
        violations.append(_schema_violation(
            name, None, None, "declared artifact was not presented for validation"))
        counts["unclassified"] += 1
        counts["schema"] += 1
    total = 0
    for artifact in sorted(set(payloads) & declared):
        schema_bad = validate_artifact_schema(
            bundle, artifact, payloads[artifact], well_keys,
            serialization_stage=serialization_stage)
        violations.extend(schema_bad)
        counts["schema"] += len(schema_bad)
        for occ in collect_string_fields(bundle, artifact, payloads[artifact], well_keys):
            total += 1
            ok, auth, reason = authorize_occurrence(bundle, occ)
            policy = bundle.field_policy.get((artifact, occ.field))
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
# The export gate
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
        return ("number", decimal.Decimal(str(value)).normalize().as_tuple())
    if kind == "boolean":
        return ("boolean", value if stage == "pre" else value == "True")
    raise AssertionError(kind)  # pragma: no cover


def canonicalize_emitted_records(bundle, payloads, serialization_stage="auto"):
    """Return a complete, schema-aware semantic representation.

    CSV values are restored to their declared semantic types so that harmless
    serialization representation differences neither mask nor manufacture a
    mutation. Row order and every declared field value remain part of the
    comparison.
    """
    import json as _json
    canonical = []
    for artifact in sorted(payloads):
        payload = payloads[artifact]
        if artifact in bundle.csv_schemas:
            schema = bundle.csv_schemas[artifact]
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


def export_authorized_outputs(bundle, out_dir, payloads, well_keys=(), writer=None):
    """Schema-driven, transactional two-stage export.

    STAGE 1 validates exact artifact/field schemas, requiredness, types and
    content authorization at the PRE-serialization stage. STAGE 2 writes only
    into a temporary sibling directory, re-reads the bytes, re-validates them
    at the POST-serialization stage, and compares every canonical record and
    value. The official destination is touched only after both stages pass.

    Returns `(report_before, report_after)`. Raises `OutputAuthorizationError`
    on any validation or serializer failure, leaving the destination
    unchanged. Publication uses per-file atomic replacement with rollback:
    failure-atomic for handled process errors, not a claim of multi-file
    atomicity across power loss or operating-system failure.
    """
    import csv as _csv
    import json as _json
    import os as _os
    import pathlib as _pathlib
    import shutil as _shutil
    import tempfile as _tempfile

    out_dir = _pathlib.Path(out_dir)
    before = validate_emitted_records(
        bundle, payloads, well_keys=well_keys, serialization_stage="pre")
    if not before.ok:
        raise OutputAuthorizationError(
            f"refusing to write: {len(before.violations)} schema/authorization "
            f"output field(s); first: "
            f"{before.violations[0] if before.violations else None}")
    canonical_before = canonicalize_emitted_records(
        bundle, payloads, serialization_stage="pre")

    allowed_destination_names = set(bundle.artifacts) | set(bundle.extra_destination_names)
    if out_dir.exists():
        if not out_dir.is_dir():
            raise OutputAuthorizationError(
                "output destination exists and is not a directory")
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
                    # Encode explicitly so the published bytes are identical on
                    # Windows and Linux/Colab. Path.write_text() uses platform
                    # newline translation and previously emitted CRLF on Windows
                    # but LF on the delivery platform.
                    target.write_bytes(
                        (_json.dumps(payload, indent=2, sort_keys=True) + "\n")
                        .encode("utf-8"))
                else:
                    schema = bundle.csv_schemas[name]
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
            bundle, reread, well_keys=well_keys, serialization_stage="post")
        if not after.ok:
            raise OutputAuthorizationError(
                f"post-serialization re-check failed: {len(after.violations)} field(s) "
                f"changed or became unauthorized after authorization; first: "
                f"{after.violations[0] if after.violations else None}")
        canonical_after = canonicalize_emitted_records(
            bundle, reread, serialization_stage="post")
        if canonical_after != canonical_before:
            mismatch = next((i for i, pair in enumerate(zip(
                canonical_before, canonical_after)) if pair[0] != pair[1]), None)
            raise OutputAuthorizationError(
                f"post-serialization canonical record mismatch at artifact index "
                f"{mismatch}; an authorized value, field, row order or type changed")

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


# ---------------------------------------------------------------------------
# Faithfulness harness: the LOCKED Increment 6 registries, as a bundle
# ---------------------------------------------------------------------------

def bundle_from_locked_increment6():
    """Build a `PolicyBundle` from the LOCKED Increment 6.1.7 registries.

    Used by `tests/test_overburden_policy.py` to demonstrate that this
    generalized engine reproduces the locked engine's decision on every
    occurrence of the real, packaged Increment 6 records. It reads the locked
    module; it never writes to it.
    """
    from p2mem.io import output_policy as locked
    from p2mem.wellframe_models import APPROVED_LABELS

    labels = [lab for bucket in APPROVED_LABELS.values() for lab in bucket.values()]
    return PolicyBundle(
        name="locked_increment6",
        field_policies=tuple(locked.OUTPUT_FIELD_POLICY.values()),
        statements=tuple(locked.OUTPUT_STATEMENTS.values()),
        templates=tuple(locked.OUTPUT_TEMPLATES.values()),
        labels=tuple(labels),
        csv_schemas=locked.CSV_SCHEMAS,
        manifest_artifact=locked.MANIFEST_ARTIFACT,
        json_object_keys=locked.JSON_OBJECT_KEYS,
        json_list_item_kinds=locked.JSON_LIST_ITEM_KINDS,
        json_boolean_paths=locked.JSON_BOOLEAN_PATHS,
        json_integer_paths=locked.JSON_INTEGER_PATHS,
        json_number_paths=locked.JSON_NUMBER_PATHS,
        json_nullable_paths=locked.JSON_NULLABLE_PATHS,
        approved_well_keys=locked.APPROVED_WELL_KEYS,
        field_types=locked.OUTPUT_FIELD_TYPES,
    )
