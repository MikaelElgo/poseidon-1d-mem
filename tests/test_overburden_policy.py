"""
Increment 7 - output-policy engine, closed schemas, authorization, transactional
export, and the FAITHFULNESS harness against the locked Increment 6.1.7 engine.

The adversarial section deliberately mutates the records that are ACTUALLY
serialized. A schema test that validated a reconstruction of the payload would
prove nothing about what reaches disk.
"""

from __future__ import annotations

import copy
import csv
import json
import os
from pathlib import Path

import pytest

from p2mem.io import output_policy as locked
from p2mem.io.overburden_policy import (
    CATEGORY_ENUMERATED_CODE_LIST,
    OutputAuthorizationError,
    PolicyBundle,
    FieldPolicy,
    authorize_occurrence,
    bundle_from_locked_increment6,
    canonicalize_emitted_records,
    collect_string_fields,
    export_authorized_outputs,
    validate_artifact_schema,
    validate_emitted_records,
)
from p2mem.io.overburden_registry import (
    ASSURANCE_TIER_VALUE, AVAILABILITY, ELIGIBILITY, GAPS, ISSUES,
    OVERBURDEN_ARTIFACTS, OVERBURDEN_BUNDLE, OVERBURDEN_CSV_SCHEMAS,
    OVERBURDEN_MANIFEST_ARTIFACT, OVERBURDEN_STATEMENTS, PROFILE, QC, SCENARIOS,
    SENSITIVITY,
)

from helpers_inc7 import PROJECT_ROOT  # noqa: E402


# ---------------------------------------------------------------------------
# Structural guarantees of the bundle itself
# ---------------------------------------------------------------------------

def test_nine_declared_artifacts_with_one_json_manifest():
    assert len(OVERBURDEN_ARTIFACTS) == 9
    assert OVERBURDEN_MANIFEST_ARTIFACT in OVERBURDEN_ARTIFACTS
    assert sum(1 for a in OVERBURDEN_ARTIFACTS if a.endswith(".json")) == 1
    assert sum(1 for a in OVERBURDEN_ARTIFACTS if a.endswith(".csv")) == 8


def test_notebook_gate_uses_the_declared_scenario_basis_field():
    """Prevent a gate-only field-name drift from escaping notebook parity.

    ``%%writefile`` parity covers source files but not the later completion
    gate.  This test binds that gate's literal lookup to the real emitted CSV
    schema, so a typo cannot survive merely because the notebook is valid JSON.
    """
    expected = "assumed_density_basis"
    assert expected in OVERBURDEN_CSV_SCHEMAS[SCENARIOS].columns
    assert "assumption_basis" not in OVERBURDEN_CSV_SCHEMAS[SCENARIOS].columns

    path = PROJECT_ROOT / "07_Density_QC_and_Overburden_Stress_Framework.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    gate_cells = [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if (cell.get("cell_type") == "code"
            and not "".join(cell.get("source", [])).startswith("%%writefile ")
            and "INCREMENT 7.0.4 COMPLETION GATE" in
            "".join(cell.get("source", [])))
    ]
    assert len(gate_cells) == 1
    gate_source = gate_cells[0]
    assert f'row["{expected}"]' in gate_source
    assert 'row["assumption_basis"]' not in gate_source


def test_every_csv_string_field_is_classified_exactly_once():
    """The bundle constructor enforces this; assert it holds for the shipped one."""
    for artifact, schema in OVERBURDEN_CSV_SCHEMAS.items():
        classified = {f for (a, f) in OVERBURDEN_BUNDLE.field_policy if a == artifact}
        assert classified == set(schema.string_fields)


def test_a_bundle_with_an_unclassified_string_column_cannot_be_built():
    schemas = dict(OVERBURDEN_CSV_SCHEMAS)
    policies = [p for p in OVERBURDEN_BUNDLE.field_policy.values()
                if not (p.artifact == ISSUES and p.field == "severity")]
    with pytest.raises(ValueError, match="differ"):
        PolicyBundle(
            name="broken", field_policies=policies,
            statements=OVERBURDEN_BUNDLE.statements.values(),
            templates=OVERBURDEN_BUNDLE.templates.values(),
            labels=[lab for b in OVERBURDEN_BUNDLE.labels.values() for lab in b.values()],
            csv_schemas=schemas,
            manifest_artifact=OVERBURDEN_MANIFEST_ARTIFACT,
            json_object_keys=OVERBURDEN_BUNDLE.json_object_keys,
            json_list_item_kinds=OVERBURDEN_BUNDLE.json_list_item_kinds,
            json_boolean_paths=OVERBURDEN_BUNDLE.json_boolean_paths,
            json_integer_paths=OVERBURDEN_BUNDLE.json_integer_paths,
            json_number_paths=OVERBURDEN_BUNDLE.json_number_paths,
            json_nullable_paths=OVERBURDEN_BUNDLE.json_nullable_paths,
            approved_well_keys=OVERBURDEN_BUNDLE.approved_well_keys,
            field_types=OVERBURDEN_BUNDLE.field_types)


def test_no_csv_schema_declares_a_duplicate_or_untyped_column():
    for artifact, schema in OVERBURDEN_CSV_SCHEMAS.items():
        assert len(set(schema.columns)) == len(schema.columns), artifact
        typed = schema.integer_fields | schema.number_fields | schema.boolean_fields
        assert typed <= set(schema.columns), artifact


def test_an_enumerated_code_list_must_declare_its_vocabulary():
    with pytest.raises(ValueError, match="closed vocabulary"):
        FieldPolicy("a.csv", "f", CATEGORY_ENUMERATED_CODE_LIST)


def test_an_unknown_category_is_still_rejected():
    with pytest.raises(ValueError, match="unknown category"):
        FieldPolicy("a.csv", "f", "free_prose")


# ---------------------------------------------------------------------------
# The added enumerated_code_list category
# ---------------------------------------------------------------------------

def _occ(artifact, field, value):
    from p2mem.io.output_policy import FieldOccurrence
    return FieldOccurrence(artifact, field, value, "row[0]." + field)


@pytest.mark.parametrize("value", [
    "none",
    "seabed_datum_unresolved",
    "internal_gap_exceeds_limit;shallow_density_column_unresolved",
])
def test_a_sorted_list_of_known_codes_authorizes(value):
    ok, auth, reason = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(ELIGIBILITY, "limiting_reasons", value))
    assert ok, reason
    assert auth[0] == "enumerated_code_list"


@pytest.mark.parametrize("value,fragment", [
    ("not_a_real_code", "closed vocabulary"),
    ("seabed_datum_unresolved;not_a_real_code", "closed vocabulary"),
    ("seabed_datum_unresolved;seabed_datum_unresolved", "repeat"),
    ("shallow_density_column_unresolved;internal_gap_exceeds_limit", "sorted"),
    ("seabed_datum_unresolved;", "empty element"),
    ("The interval is unresolved.", "closed vocabulary"),
])
def test_a_malformed_code_list_is_refused(value, fragment):
    ok, _, reason = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(ELIGIBILITY, "limiting_reasons", value))
    assert not ok
    assert fragment in reason


def test_an_enumerated_code_list_counts_as_controlled():
    from p2mem.io.overburden_policy import CONTROLLED_CATEGORIES
    assert CATEGORY_ENUMERATED_CODE_LIST in CONTROLLED_CATEGORIES


# ---------------------------------------------------------------------------
# Faithfulness to the LOCKED Increment 6.1.7 engine
# ---------------------------------------------------------------------------

def _locked_increment6_payloads():
    out_dir = PROJECT_ROOT / "outputs" / "06_petrophysics_eligibility"
    payloads = {}
    for name in locked.OUTPUT_ARTIFACTS:
        path = out_dir / name
        if not path.exists():
            return None
        if name.endswith(".json"):
            payloads[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            with open(path, newline="", encoding="utf-8") as fh:
                payloads[name] = list(csv.DictReader(fh))
    return payloads


def test_generalized_engine_reproduces_the_locked_engine_on_real_increment6_records():
    """The faithfulness harness.

    Runs the Increment 7 engine over the LOCKED Increment 6 registries and the
    REAL packaged Increment 6 artifacts, and requires the same decision on
    every single occurrence. This is what makes "generalized, not
    reimplemented" a checkable claim rather than a comment.
    """
    payloads = _locked_increment6_payloads()
    if payloads is None:
        pytest.skip("packaged Increment 6 outputs are not present in this tree")
    wells = set(locked.APPROVED_WELL_KEYS)
    bundle = bundle_from_locked_increment6()

    mine = validate_emitted_records(
        bundle, payloads, well_keys=wells, serialization_stage="post")
    theirs = locked.validate_emitted_records(
        payloads, well_keys=wells, serialization_stage="post")

    for attr in ("n_string_field_occurrences", "n_controlled_occurrences",
                 "n_structural_occurrences", "n_unguaranteed_occurrences",
                 "n_unclassified_fields", "n_unauthorized_controlled_fields",
                 "n_field_kind_mismatches", "n_schema_violations",
                 "distinct_statements_used", "distinct_templates_used",
                 "distinct_labels_used"):
        assert getattr(mine, attr) == getattr(theirs, attr), attr
    assert mine.ok is theirs.ok is True
    assert mine.n_string_field_occurrences > 0
    assert (canonicalize_emitted_records(bundle, payloads, serialization_stage="post")
            == locked.canonicalize_emitted_records(payloads, serialization_stage="post"))


def test_generalized_engine_reproduces_the_locked_engines_rejections():
    """The same faithfulness claim, for the cases that must FAIL."""
    payloads = _locked_increment6_payloads()
    if payloads is None:
        pytest.skip("packaged Increment 6 outputs are not present in this tree")
    wells = set(locked.APPROVED_WELL_KEYS)
    bundle = bundle_from_locked_increment6()

    mutations = []
    p = copy.deepcopy(payloads)
    p["gr_endpoint_scenarios.csv"][0]["description"] = "An unauthorized sentence."
    mutations.append(p)
    p = copy.deepcopy(payloads)
    for row in p["gr_endpoint_scenarios.csv"]:
        row.pop("description")
    mutations.append(p)
    p = copy.deepcopy(payloads)
    for row in p["gr_endpoint_scenarios.csv"]:
        row["rogue_column"] = "x"
    mutations.append(p)
    p = copy.deepcopy(payloads)
    p.pop("gr_endpoint_scenarios.csv")
    mutations.append(p)

    for payload in mutations:
        mine = validate_emitted_records(
            bundle, payload, well_keys=wells, serialization_stage="post")
        theirs = locked.validate_emitted_records(
            payload, well_keys=wells, serialization_stage="post")
        assert mine.ok is False and theirs.ok is False
        assert len(mine.violations) == len(theirs.violations)


# ---------------------------------------------------------------------------
# Increment 7 payloads: adversarial schema and transaction probes
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def payloads_and_wells(tmp_path_factory):
    """The REAL Increment 7 payloads, built from synthetic well frames.

    Synthetic frames are used deliberately: these probes are about the export
    path, and must run in a tree that carries no approved project data.
    """
    import numpy as np
    from p2mem.density_qc import load_overburden_config
    from p2mem.io.overburden_workflow import build_overburden_payloads, run_overburden_workflow
    from synthetic_inc7 import make_frame

    config = load_overburden_config(str(PROJECT_ROOT / "config" / "overburden_stress.yml"))
    frames = {}
    for i, key in enumerate(sorted(OVERBURDEN_BUNDLE.approved_well_keys)):
        md = np.arange(1000.0 + 10.0 * i, 1201.0 + 10.0 * i, 10.0)
        rho = np.full(md.size, 2000.0 + 50.0 * i)
        if i == 1:
            rho[5:7] = np.nan          # a bridgeable short gap
        frames[key] = make_frame(well_key=key, md=md, density=rho)
    marker_table = tmp_path_factory.mktemp("marker_table") / "markers.csv"
    marker_table.write_text(
        "well_key,canonical_marker_name,MDRT_reconciled_m,TVD_survey_m,"
        "TVDSS_survey_corrected_m\n", encoding="utf-8")
    run = run_overburden_workflow(
        frames, config, marker_table_path=str(marker_table))
    return build_overburden_payloads(run), set(frames)


def test_the_real_payload_set_validates_clean(payloads_and_wells):
    payloads, wells = payloads_and_wells
    report = validate_emitted_records(
        OVERBURDEN_BUNDLE, payloads, well_keys=wells, serialization_stage="pre")
    assert report.ok, report.violations[:2]
    assert report.n_schema_violations == 0
    assert report.n_unclassified_fields == 0
    assert report.n_unauthorized_controlled_fields == 0
    assert report.n_string_field_occurrences > 0
    assert set(report.artifacts_inspected) == set(OVERBURDEN_ARTIFACTS)


def test_export_writes_every_declared_artifact(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    before, after = export_authorized_outputs(
        OVERBURDEN_BUNDLE, tmp_path / "out", payloads, well_keys=wells)
    assert before.ok and after.ok
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == list(
        OVERBURDEN_ARTIFACTS)


def test_default_json_serializer_emits_explicit_utf8_lf_bytes(
        tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    actual = (out / OVERBURDEN_MANIFEST_ARTIFACT).read_bytes()
    expected = (json.dumps(
        payloads[OVERBURDEN_MANIFEST_ARTIFACT], indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert actual == expected
    assert actual.endswith(b"\n")
    assert b"\r\n" not in actual


def test_default_json_serializer_does_not_use_platform_text_newlines(
        tmp_path, payloads_and_wells, monkeypatch):
    payloads, wells = payloads_and_wells

    def forbidden_write_text(*args, **kwargs):
        raise AssertionError("default JSON serialization must use explicit bytes")

    monkeypatch.setattr(Path, "write_text", forbidden_write_text)
    before, after = export_authorized_outputs(
        OVERBURDEN_BUNDLE, tmp_path / "out", payloads, well_keys=wells)
    assert before.ok and after.ok


def test_export_round_trip_is_canonically_identical(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    written = {}
    for name in OVERBURDEN_ARTIFACTS:
        path = out / name
        if name.endswith(".json"):
            written[name] = json.loads(path.read_text(encoding="utf-8"))
        else:
            with open(path, newline="", encoding="utf-8") as fh:
                written[name] = list(csv.DictReader(fh))
    assert (canonicalize_emitted_records(OVERBURDEN_BUNDLE, payloads,
                                         serialization_stage="pre")
            == canonicalize_emitted_records(OVERBURDEN_BUNDLE, written,
                                            serialization_stage="post"))


def _mutations(payloads):
    out = []

    def add(fn):
        p = copy.deepcopy(payloads)
        fn(p)
        out.append(p)

    # An unauthorized sentence in a registered-statement column.
    add(lambda p: p[ELIGIBILITY][0].__setitem__(
        "limitations", "Everything is fine here."))
    # A near-miss on a registered statement: one character changed.
    add(lambda p: p[ELIGIBILITY][0].__setitem__(
        "limitations", OVERBURDEN_STATEMENTS["eligibility_limitations"].text + " "))
    # A status value that is not an approved label.
    add(lambda p: p[ELIGIBILITY][0].__setitem__("overburden_status", "looks_fine"))
    # A limiting-reason list that is not sorted.
    add(lambda p: p[ELIGIBILITY][0].__setitem__(
        "limiting_reasons", "terminal_density_column_unresolved;seabed_datum_unresolved"))
    # A deleted column.
    add(lambda p: [row.pop("limitations") for row in p[ELIGIBILITY]])
    # An added column.
    add(lambda p: [row.__setitem__("rogue", "x") for row in p[ELIGIBILITY]])
    # A renamed column.
    add(lambda p: [row.__setitem__("well_key_renamed", row.pop("well_key"))
                   for row in p[ELIGIBILITY]])
    # Reordered columns: order is contractual for a CSV.
    add(lambda p: p.__setitem__(
        ELIGIBILITY, [dict(reversed(list(row.items()))) for row in p[ELIGIBILITY]]))
    # Wrong types where a number is declared.
    for bad in ("2000", None, True):
        add(lambda p, b=bad: p[ELIGIBILITY][0].__setitem__("gravity_m_s2", b))
    # A non-finite number.
    add(lambda p: p[ELIGIBILITY][0].__setitem__("gravity_m_s2", float("nan")))
    # A float where an integer count is declared.
    add(lambda p: p[ELIGIBILITY][0].__setitem__("n_eligible_samples", 3.0))
    # A string where a boolean is declared.
    add(lambda p: p[ELIGIBILITY][0].__setitem__("seabed_resolved", "True"))
    # An unknown well identifier.
    add(lambda p: p[ELIGIBILITY][0].__setitem__("well_key", "Rogue_Well_9"))
    # An unknown artifact in the payload set.
    add(lambda p: p.__setitem__("rogue_artifact.csv", []))
    # A missing declared artifact.
    add(lambda p: p.pop(SCENARIOS))
    # An unknown key inside the manifest.
    add(lambda p: p[OVERBURDEN_MANIFEST_ARTIFACT].__setitem__("rogue_key", 1))
    # A missing key inside the manifest.
    add(lambda p: p[OVERBURDEN_MANIFEST_ARTIFACT].pop("gravity_m_s2"))
    # A manifest well entry for a well that was never evaluated.
    add(lambda p: p[OVERBURDEN_MANIFEST_ARTIFACT]["wells"].__setitem__(
        "Rogue_Well_9", {}))
    return out


def test_every_adversarial_mutation_fails_closed_and_writes_nothing(
        tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    for i, mutated in enumerate(_mutations(payloads)):
        target = tmp_path / f"case_{i}"
        with pytest.raises(OutputAuthorizationError):
            export_authorized_outputs(
                OVERBURDEN_BUNDLE, target, mutated, well_keys=wells)
        assert not target.exists() or not list(target.iterdir())


def test_a_rejected_export_leaves_prior_official_outputs_untouched(
        tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    before = {p.name: p.read_bytes() for p in out.iterdir()}

    bad = copy.deepcopy(payloads)
    bad[ELIGIBILITY][0]["limitations"] = "Unauthorized replacement text."
    with pytest.raises(OutputAuthorizationError):
        export_authorized_outputs(OVERBURDEN_BUNDLE, out, bad, well_keys=wells)
    after = {p.name: p.read_bytes() for p in out.iterdir()}
    assert after == before


def test_a_stale_undeclared_artifact_in_the_destination_is_refused(
        tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale_result.csv").write_text("stale\n", encoding="utf-8")
    with pytest.raises(OutputAuthorizationError, match="stale"):
        export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    assert (out / "stale_result.csv").read_text(encoding="utf-8") == "stale\n"


def test_a_figures_directory_is_not_treated_as_stale(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    (out / "figures").mkdir(parents=True)
    export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    assert (out / "figures").is_dir()


def test_a_serializer_that_mutates_an_authorized_value_is_caught(
        tmp_path, payloads_and_wells):
    """The post-serialization comparison, probed with an AUTHORIZED substitute.

    The replacement value is itself a registered statement, so it passes
    authorization. Only the canonical record comparison can catch it.
    """
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    export_authorized_outputs(OVERBURDEN_BUNDLE, out, payloads, well_keys=wells)
    baseline = {p.name: p.read_bytes() for p in out.iterdir()}

    replacement = OVERBURDEN_STATEMENTS["qc_limitations"].text

    def mutating_writer(target, payload):
        value = copy.deepcopy(payload)
        if target.name == ELIGIBILITY:
            value[0]["limitations"] = replacement
        if target.suffix == ".json":
            target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        else:
            schema = OVERBURDEN_CSV_SCHEMAS[target.name]
            with open(target, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(schema.columns))
                w.writeheader()
                w.writerows(value)

    with pytest.raises(OutputAuthorizationError):
        export_authorized_outputs(
            OVERBURDEN_BUNDLE, out, payloads, well_keys=wells, writer=mutating_writer)
    assert {p.name: p.read_bytes() for p in out.iterdir()} == baseline


def test_a_serializer_that_reorders_rows_is_caught(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells

    def reordering_writer(target, payload):
        value = copy.deepcopy(payload)
        if target.name == ELIGIBILITY:
            value = list(reversed(value))
        if target.suffix == ".json":
            target.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        else:
            schema = OVERBURDEN_CSV_SCHEMAS[target.name]
            with open(target, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(schema.columns))
                w.writeheader()
                w.writerows(value)

    out = tmp_path / "out"
    with pytest.raises(OutputAuthorizationError, match="canonical record mismatch"):
        export_authorized_outputs(
            OVERBURDEN_BUNDLE, out, payloads, well_keys=wells, writer=reordering_writer)
    assert not out.exists() or not list(out.iterdir())


def test_a_failing_serializer_leaves_no_residue(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    out = tmp_path / "out"
    out.mkdir()
    sentinel = out / ELIGIBILITY
    sentinel.write_bytes(b"approved baseline bytes\n")

    def failing_writer(_target, _payload):
        raise RuntimeError("simulated serializer failure")

    with pytest.raises(OutputAuthorizationError, match="serializer failed"):
        export_authorized_outputs(
            OVERBURDEN_BUNDLE, out, payloads, well_keys=wells, writer=failing_writer)
    assert sentinel.read_bytes() == b"approved baseline bytes\n"
    assert {p.name for p in out.iterdir()} == {ELIGIBILITY}
    # No staging or backup residue anywhere beside the destination.
    assert not [p for p in out.parent.iterdir()
                if p.name.startswith(".") and p.is_dir()]


def test_a_writer_that_omits_an_artifact_is_caught(tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells

    def skipping_writer(target, payload):
        if target.name == SCENARIOS:
            return
        if target.suffix == ".json":
            target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")
        else:
            schema = OVERBURDEN_CSV_SCHEMAS[target.name]
            with open(target, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(schema.columns))
                w.writeheader()
                w.writerows(payload)

    out = tmp_path / "out"
    with pytest.raises(OutputAuthorizationError, match="wrong artifact inventory"):
        export_authorized_outputs(
            OVERBURDEN_BUNDLE, out, payloads, well_keys=wells, writer=skipping_writer)


def test_export_is_byte_deterministic_across_two_destinations(
        tmp_path, payloads_and_wells):
    payloads, wells = payloads_and_wells
    a, b = tmp_path / "a", tmp_path / "b"
    export_authorized_outputs(OVERBURDEN_BUNDLE, a, payloads, well_keys=wells)
    export_authorized_outputs(OVERBURDEN_BUNDLE, b, payloads, well_keys=wells)
    for name in OVERBURDEN_ARTIFACTS:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_no_absolute_path_leaks_into_any_emitted_artifact(payloads_and_wells):
    payloads, _ = payloads_and_wells
    blob = json.dumps(payloads, sort_keys=True, default=str)
    assert ":\\" not in blob
    assert "/home/" not in blob
    assert "/content/" not in blob
    assert str(PROJECT_ROOT) not in blob


def test_the_serialization_stage_is_pinned_not_auto(payloads_and_wells):
    """`auto` must never be relied on in the export gate.

    Probed behaviourally: a payload whose every numeric value happens to be a
    string would be mis-detected as post-serialization by `auto`, and the
    explicit `pre` stage must reject it.
    """
    payloads, wells = payloads_and_wells
    schema = OVERBURDEN_CSV_SCHEMAS[ELIGIBILITY]
    typed = schema.integer_fields | schema.number_fields | schema.boolean_fields
    stringified = copy.deepcopy(payloads)
    for row in stringified[ELIGIBILITY]:
        for field in typed:
            row[field] = "" if row[field] is None else str(row[field])

    # `auto` inspects the values and concludes this artifact is already
    # serialized, so it accepts it. That is exactly why a production gate may
    # not run on `auto`: post-serialization bytes would sail through a check
    # that is supposed to be validating typed, pre-serialization records.
    auto = validate_emitted_records(
        OVERBURDEN_BUNDLE, stringified, well_keys=wells, serialization_stage="auto")
    pinned = validate_emitted_records(
        OVERBURDEN_BUNDLE, stringified, well_keys=wells, serialization_stage="pre")
    assert auto.n_schema_violations == 0
    assert pinned.n_schema_violations >= len(typed)
    assert pinned.n_schema_violations > auto.n_schema_violations
    with pytest.raises(OutputAuthorizationError):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            export_authorized_outputs(
                OVERBURDEN_BUNDLE, os.path.join(td, "out"), stringified,
                well_keys=wells)


# ---------------------------------------------------------------------------
# Collection and schema helpers
# ---------------------------------------------------------------------------

def test_collection_is_schema_driven_not_value_driven(payloads_and_wells):
    """A numeric-looking string in a prose column is still prose."""
    payloads, wells = payloads_and_wells
    mutated = copy.deepcopy(payloads)
    mutated[ELIGIBILITY][0]["limitations"] = "12345"
    occurrences = collect_string_fields(
        OVERBURDEN_BUNDLE, ELIGIBILITY, mutated[ELIGIBILITY], wells)
    assert any(o.field == "limitations" and o.value == "12345" for o in occurrences)
    ok, _, _ = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(ELIGIBILITY, "limitations", "12345"))
    assert not ok


def test_an_empty_string_in_a_required_column_is_refused():
    ok, _, reason = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(ELIGIBILITY, "limitations", ""))
    assert not ok and "empty string" in reason


def test_an_undeclared_artifact_has_no_schema():
    violations = validate_artifact_schema(OVERBURDEN_BUNDLE, "nope.csv", [])
    assert violations and "no declared schema" in violations[0]["reason"]


def test_the_scenario_template_refuses_a_prose_substitution():
    tpl = OVERBURDEN_BUNDLE.templates["scenario_basis"]
    good = {"assumed_density_kg_m3": "1500.0000",
            "unresolved_thickness_m": "500.0000",
            "assumed_fraction_pct": "62.50",
            "conditioned_fraction_pct": "2.50",
            "measured_fraction_pct": "35.00"}
    ok, auth, _ = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(SCENARIOS, "scenario_basis", tpl.render(good)))
    assert ok and auth[0] == "template"
    bad = dict(good, assumed_fraction_pct="most of it")
    ok, _, reason = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(SCENARIOS, "scenario_basis", tpl.render(bad)))
    assert not ok and "declared type" in reason


def test_the_mnemonic_template_accepts_only_an_integer_ordinal():
    tpl = OVERBURDEN_BUNDLE.templates["empty_mnemonic_ordinal"]
    ok, _, _ = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(AVAILABILITY, "raw_mnemonic",
                                tpl.render({"ordinal": "6"})))
    assert ok
    ok, _, _ = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(AVAILABILITY, "raw_mnemonic",
                                tpl.render({"ordinal": "six"})))
    assert not ok


def test_every_registered_statement_is_actually_reachable_from_a_field():
    """No dead prose in the registry: each statement is declared on a field."""
    declared = set()
    for policy in OVERBURDEN_BUNDLE.field_policy.values():
        declared.update(policy.statement_ids)
    assert declared == set(OVERBURDEN_STATEMENTS)


def test_every_approved_label_belongs_to_a_declared_field_kind():
    kinds = {p.field_kind for p in OVERBURDEN_BUNDLE.field_policy.values()
             if p.category == "typed_label"}
    assert set(OVERBURDEN_BUNDLE.labels) == kinds


def test_a_label_approved_under_one_field_kind_authorizes_nothing_under_another():
    ok, _, reason = authorize_occurrence(
        OVERBURDEN_BUNDLE, _occ(ELIGIBILITY, "overburden_status",
                                "bridged_linear_in_tvd"))
    assert not ok
    assert "approved only as" in reason


def test_the_assurance_tier_matches_the_locked_package_declaration():
    import p2mem
    assert ASSURANCE_TIER_VALUE == p2mem.ASSURANCE_TIER
