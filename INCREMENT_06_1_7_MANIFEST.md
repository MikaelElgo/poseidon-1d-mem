# Increment 6.1.7 Manifest — Schema-Driven, Failure-Atomic Output Authorization

**Project:** Poseidon 2 — 1D Mechanical Earth Model  
**Assurance tier:** Tier C — Screening-Level / Uncalibrated Educational  
**Package version:** `p2mem` 0.6.8  
**Direct baseline:** `Poseidon_1D_MEM_Increment_06_v6.1.6.zip`  
**Verified baseline SHA-256:** `041a9da44ae8b8451d2aaf7119e94f87e2adadc0e4c044edbc565152354c7c25`  
**Scope:** corrective patch to Increment 6.1.6 only. Increment 7 has not been started.

## 1. Status and verification boundary

This package is a **pre-Colab release candidate** until the supplied notebook completes a fresh Google Colab `Run all` with the full pytest suite and all 28 completion-gate checks passing. The implementation, package structure, deterministic outputs and the 28 new regression cases were verified locally as described below, but the local runtime does not contain pytest or nbformat and cannot retrieve them from its restricted network. Therefore this record does not invent a `pytest` result or claim final Colab acceptance before it occurs.

The direct baseline hash was recomputed before editing and matched exactly. The Increment 5.1.2 locked baseline was also re-hashed as `081a9d19af7abaec6e8f37a4b43026278b19663d26085251572433bea0c68781`.

## 2. Reproduced Increment 6.1.6 defects

All findings were reproduced against the untouched, hash-verified 6.1.6 package before correction:

1. Removing the required `description` column from every endpoint row still passed because field discovery was driven by present, non-empty strings.
2. A controlled field replaced with `""`, `None`, integer `123`, or numeric-looking string `"123"` could escape either collection or the intended type contract.
3. Unknown CSV columns carrying `""`, `None`, or numeric-looking content could pass because unknown fields were noticed only when their values were collected as prose.
4. A controlled JSON statement replaced with a non-string value could escape the string collector.
5. A serializer could replace one authorized statement with a different authorized statement and still pass because only aggregate coverage counts were compared.
6. Post-serialization rejection occurred after files had already been written into the official output directory, leaving a partial rejected set behind.
7. Undeclared stale artifacts already present in the official directory were neither rejected nor removed.

The notebook had an additional concrete bypass: its custom `_nb_writer` ignored the staging target supplied by `export_authorized_outputs` for CSVs and wrote directly to `OUT_DIR`. That callback is removed. The notebook now uses the production exporter and its production serializer without an alternate write path.

## 3. Corrective architecture

`p2mem/io/output_policy.py` now declares an exact schema for each of the seven CSV artifacts and the JSON manifest. Schema validation is independent of prose authorization and checks:

- the complete eight-artifact inventory;
- exact ordered CSV columns;
- exact JSON object keys and declared list/primitive paths;
- required versus explicitly nullable values;
- strict integer, finite-number, boolean and string types (`bool` is not accepted as an integer or number);
- approved dynamic well identifiers only;
- empty and numeric-looking values in declared string fields; and
- the exact partition between schema-declared CSV string fields and authorization policies.

Content authorization then examines every schema-declared string occurrence. Empty or numeric-looking strings are not invisible. Controlled values must still resolve to a typed approved label, exact registered statement, or typed controlled template. Unknown artifacts, fields, paths, identifiers and types fail closed.

Export is staged and failure-atomic for handled process errors:

1. Validate typed pre-serialization records.
2. Build a type-aware canonical representation of every artifact, field and row.
3. Write the complete candidate set into an isolated sibling directory.
4. Reject missing, extra, non-regular or symbolic-link staged entries.
5. Re-read and validate the staged bytes under post-serialization types.
6. Require the complete canonical records, including row order, to match.
7. Publish via per-file atomic replacement only after all checks pass; restore backups if a handled mid-publication replacement fails.

This is not presented as multi-file atomicity across power loss, kernel failure, or storage-device failure.

## 4. Regression coverage

`tests/test_method_eligibility.py` adds **28 collected cases in 15 test functions** covering:

- missing required CSV columns;
- empty, null, integer and numeric-looking controlled CSV/JSON values;
- unknown CSV columns and JSON paths with non-prose values;
- unapproved dynamic well keys;
- boolean and non-finite numeric substitutions;
- authorization-policy/schema partition identity;
- successful complete typed round-trip equality;
- authorized-to-authorized writer mutation;
- unauthorized post-serialization mutation;
- post-write missing/unknown/type-mutated columns and row reordering;
- stale destination artifacts;
- typed serializer failure with no publication; and
- rollback after a simulated mid-publication replacement failure.

The 6.1.6 completion record reports 916 passing tests. With these 28 new cases, the expected Colab collection is **944**. This package does **not** claim `944 passed` until the notebook actually observes it.

## 5. Verification actually completed here

- Direct-baseline SHA-256: exact match.
- ZIP safety: 191 unique baseline entries; no absolute names, `..` traversal, or symlinks.
- Python compilation: all packaged Python modules and tests compiled successfully.
- Direct execution of every new adversarial behavior: passed, including successful round trip, schema/type rejection, authorized-to-authorized mutation rejection, unchanged destination on rejected serialization, and exact restoration after simulated mid-publication failure.
- Current eight-artifact post-serialization validation: 0 schema violations, 0 unclassified fields, 0 unauthorized controlled fields, 0 field-kind mismatches.
- Stored seven-CSV pre-serialization coverage block: independently recomputed and exactly equal to the manifest values.
- Notebook JSON structure: 75 cells (39 code, 36 markdown), 75 unique cell IDs, zero saved outputs.
- Notebook/source parity: 15 `%%writefile` cells checked byte-for-byte, 0 mismatches, 0 missing targets.
- Notebook Python syntax: all ordinary Python cells and Python `%%writefile` bodies compile.
- Completion gate: 28 distinct checks present; actual execution is pending Colab `Run all`.
- Deterministic outputs: all 7 CSVs and all 4 figures are byte-identical to 6.1.6. The JSON manifest differs only under `/lithology_validation`.
- Raw-data exclusion: no LAS, deviation, checkshot, or formation-top source file is added by this patch.
- Runtime dependencies: unchanged.

## 6. Assurance-manifest changes

`petrophysics_eligibility_manifest.json` changes only at these paths:

- `/lithology_validation/model`;
- `/lithology_validation/derivation`;
- `/lithology_validation/emitted_field_coverage/n_schema_violations` (new, value `0`);
- `/lithology_validation/emitted_field_coverage/n_string_field_occurrences`;
- `/lithology_validation/emitted_field_coverage/n_controlled_occurrences`;
- `/lithology_validation/emitted_field_coverage/n_structural_occurrences`; and
- `/lithology_validation/emitted_field_coverage/n_unguaranteed_occurrences`.

The count changes are deliberate: the new schema-driven collector counts declared empty and numeric-looking string occurrences that 6.1.6 silently omitted. No scientific value, threshold, endpoint, mask, interval, depth mapping, well disposition, figure, or real-data interpretation changes.

## 7. Package delta from Increment 6.1.6

**Changed (8):**

1. `06_GR_QC_Shale_Proxy_and_Method_Eligibility.ipynb`
2. `README.md`
3. `outputs/06_petrophysics_eligibility/petrophysics_eligibility_manifest.json`
4. `p2mem/__init__.py`
5. `p2mem/io/output_policy.py`
6. `p2mem/io/petrophysics_inventory.py`
7. `pyproject.toml`
8. `tests/test_method_eligibility.py`

**Added (2, packaged):**

1. `INCREMENT_06_1_7_MANIFEST.md`
2. `INCREMENT_06_1_7_SHA256SUMS.txt`

**Removed:** none.

The separately delivered completion record is intentionally not inside the ZIP and is not counted as a packaged delta.

## 8. Colab acceptance condition

Open the corrected notebook from this package in the existing project root and select **Runtime → Run all**. Final acceptance requires both observed facts:

1. pytest reports **944 passed, 0 failed** (or explains any different collected count rather than assuming it); and
2. the final completion cell prints **28/28 `[PASS]`** with no exception.

Until both are observed, this artifact remains a release candidate rather than a claimed completed increment.

## 9. Stop condition

Increment 6.1.7 changes output assurance and packaging behavior only. No NCT fitting, pore-pressure prediction, elastic-property calculation, rock-strength correlation, stress modelling, wellbore-stability analysis, or other Increment 7 work was implemented or started.
